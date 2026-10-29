"""Portable mesh refinement and canonical response comparison."""

import math
from itertools import pairwise

import numpy as np

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.units import QuantityValue
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.physics import _position_profiles

_STEP_DENSITY_INTEGRALS = {"C/m^3": "C/m^2", "V/m": "V"}
_STEP_PROFILES = {
    "net_doping": "m^-2",
    "donor_concentration": "m^-2",
    "acceptor_concentration": "m^-2",
}


def _running_integral(grid: np.ndarray, values: np.ndarray) -> np.ndarray:
    steps = 0.5 * (values[1:] + values[:-1]) * np.diff(grid)
    return np.concatenate(([0.0], np.cumsum(steps)))


def refined_spec(spec: ExperimentSpec) -> ExperimentSpec:
    def half(value):
        return QuantityValue.model_validate(f"{value.to('m') / 2:.17g} m") if value else None

    regions = []
    for region in spec.regions:
        update = {
            "minimum_mesh_spacing": half(region.minimum_mesh_spacing),
            "maximum_mesh_spacing": half(region.maximum_mesh_spacing),
        }
        if region.mesh_spacing is not None:
            update["mesh_spacing"] = half(region.mesh_spacing)
        elif region.minimum_mesh_spacing is None and region.maximum_mesh_spacing is None:
            # Only when nothing was specified does refinement halve the adapter's default.
            update["mesh_spacing"] = half(
                QuantityValue.model_validate(
                    f"{(region.x1.to('m') - region.x0.to('m')) / 50:.17g} m"
                )
            )
        # With only graded bounds given, halving those alone keeps minimum <= maximum.
        regions.append(region.model_copy(update=update))
    return spec.model_copy(
        update={
            "regions": tuple(regions),
            "interfaces": tuple(
                i.model_copy(update={"mesh_spacing": half(i.mesh_spacing)}) for i in spec.interfaces
            ),
            "mesh_anchors": tuple(
                a.model_copy(update={"spacing": half(a.spacing)}) for a in spec.mesh_anchors
            ),
            "solver": spec.solver.model_copy(
                update={"mesh_refinement_level": spec.solver.mesh_refinement_level + 1}
            ),
        }
    )


_BY_PRODUCTS = frozenset({"terminal_charge", "capacitance"})


def _quantity_family(name: str) -> str:
    """The researcher-facing quantity a canonical dataset carries ("absolute_terminal_current__drain")."""
    base = name.split("__")[0].removeprefix("absolute_")
    return "terminal_current" if base == "terminal_current_density" else base


def _judged(name: str, requested: frozenset[str] | None) -> bool:
    """Whether the mesh verdict rests on this dataset.

    The verdict is about what the researcher asked for. Datasets the solver derives on the way
    (terminal charge and capacitance beside a requested current) are still compared and
    reported, but as information: they are not verified and do not decide the check.
    """
    if requested is None:
        return True
    family = _quantity_family(name)
    # Only the solver's by-products are ever set aside; any other dataset is judged, so a
    # requested quantity under an unfamiliar name can never slip out of the verdict.
    return family not in _BY_PRODUCTS or family in {_quantity_family(item) for item in requested}


def mesh_comparison(
    coarse: CanonicalResult,
    fine: CanonicalResult,
    relative_tolerance: float = 0.03,
    *,
    current_absolute_tolerance: float = 1e-6,
    equilibrium: bool = False,
    requested: frozenset[str] | None = None,
) -> dict:
    record = {
        "status": "failed",
        "relative_tolerance": relative_tolerance,
        "metrics": [],
        "method": "half-spacing; per-profile relative Linf over common region domains",
        "limitation": "One refinement comparison is an error indicator, not a proof of "
        "asymptotic convergence or experimental calibration.",
    }
    if fine.status != "completed" or coarse.status != "completed":
        return {**record, "reason": "Both executions must complete."}
    if not fine.operating_points or any(p.state != "converged" for p in fine.operating_points):
        return {**record, "reason": "All refined operating points must converge."}
    if tuple(p.coordinates for p in coarse.operating_points) != tuple(
        p.coordinates for p in fine.operating_points
    ):
        return {**record, "reason": "Refinement changed operating-point coordinates."}
    names = set(coarse.datasets) & set(fine.datasets)
    for name in sorted(names):
        left, right = coarse.datasets[name], fine.datasets[name]
        if name.startswith("validation_") or name.startswith("effective_density_"):
            continue
        if left.unit != right.unit or left.centering != right.centering:
            return {**record, "reason": f"Refinement changed dataset semantics: {name}."}
        if (left.imaginary_values is None) != (right.imaginary_values is None):
            return {**record, "reason": f"Refinement changed complex-response semantics: {name}."}
        position = any(coarse.axes[a].kind == "position" for a in left.axes)
        # A space-charge density is a step across a junction, so its pointwise difference is set
        # by one cell however fine the mesh. Its running integral (the field) is the converging
        # quantity.
        # Doping is the other quantity that steps at a junction: its vertex values cannot place
        # an abrupt step better than one cell, so its integral is compared too.
        integrated = position and (left.unit in _STEP_DENSITY_INTEGRALS or name in _STEP_PROFILES)
        unit = (
            _STEP_PROFILES.get(name, _STEP_DENSITY_INTEGRALS.get(left.unit, left.unit))
            if integrated
            else left.unit
        )
        partial = bool(left.validity and not all(left.validity)) or bool(
            right.validity and not all(right.validity)
        )
        # Samples a profile lacks where its quantity does not exist (carriers in an oxide) are
        # structural. They are compared on the samples valid in both meshes, but only when every
        # operating point converged; a failed solve or a non-profile dataset stays a failure.
        if partial and (
            not position or any(p.state != "converged" for p in coarse.operating_points)
        ):
            return {**record, "reason": f"Invalid refinement samples: {name}."}
        if not position:
            if (
                left.shape != right.shape
                or len(left.axes) != len(right.axes)
                or any(
                    coarse.axes[a].values != fine.axes[b].values
                    or coarse.axes[a].kind != fine.axes[b].kind
                    or coarse.axes[a].unit != fine.axes[b].unit
                    for a, b in zip(left.axes, right.axes, strict=True)
                )
            ):
                return {**record, "reason": f"Refinement changed response axes: {name}."}
            pairs = [(left.values, right.values, 0)]
            if left.imaginary_values is not None:
                pairs.append((left.imaginary_values, right.imaginary_values, 1))
        else:
            x, study, profiles = _position_profiles(coarse, left)
            y, other, fine_profiles = _position_profiles(fine, right)
            if study != other or len(profiles) != len(fine_profiles):
                return {
                    **record,
                    "reason": f"Refinement changed profile study coordinates: {name}.",
                }

            def segments(coords, centering, domains):
                if centering == "edge" and domains:
                    parts = []
                    for domain in domains:
                        indices = [
                            i for i, x in enumerate(coords) if domain["x0_m"] <= x <= domain["x1_m"]
                        ]
                        if indices:
                            parts.append((indices[0], indices[-1] + 1))
                    if sum(b - a for a, b in parts) != len(coords):
                        raise ValueError("Region domains do not partition the field coordinates")
                    return tuple(parts)
                # A region interface is a repeated coordinate; exported copies can differ by
                # rounding, so coincidence is judged against the extent, not exact equality.
                # A running integral is one continuous accumulation across interfaces.
                if integrated:
                    return ((0, len(coords)),)
                coincident = 1e-6 * (max(coords) - min(coords))
                starts = (
                    [0]
                    + [i for i in range(1, len(coords)) if coords[i] - coords[i - 1] <= coincident]
                    + [len(coords)]
                )
                return tuple(pairwise(starts))

            domains = coarse.metadata.get("region_domains", [])
            if domains != fine.metadata.get("region_domains", []):
                return {**record, "reason": f"Refinement changed physical region domains: {name}."}
            try:
                old_segments = segments(x, left.centering, domains)
                new_segments = segments(y, right.centering, domains)
            except ValueError as exc:
                return {**record, "reason": str(exc)}
            if len(old_segments) != len(new_segments):
                return {**record, "reason": f"Refinement changed region topology: {name}."}
            pairs = []
            imaginary_profiles = None
            if left.imaginary_values is not None:
                _, _, old_imaginary = _position_profiles(
                    coarse, left.model_copy(update={"values": left.imaginary_values})
                )
                _, _, new_imaginary = _position_profiles(
                    fine, right.model_copy(update={"values": right.imaginary_values})
                )
                imaginary_profiles = (old_imaginary, new_imaginary)
            for group, ((old, old_ok), (new, new_ok)) in enumerate(
                zip(profiles, fine_profiles, strict=True)
            ):
                for (a, b), (c, d) in zip(old_segments, new_segments, strict=True):
                    # Edge centers differ with mesh spacing; compare only common support, and
                    # only samples that exist in each mesh.
                    xs_old = np.asarray(x[a:b])[np.asarray(old_ok[a:b], dtype=bool)]
                    xs_new = np.asarray(y[c:d])[np.asarray(new_ok[c:d], dtype=bool)]
                    if not len(xs_old) or not len(xs_new):
                        continue
                    ys_old = np.asarray(old[a:b])[np.asarray(old_ok[a:b], dtype=bool)]
                    ys_new = np.asarray(new[c:d])[np.asarray(new_ok[c:d], dtype=bool)]
                    # A vertex on a contact or region interface holds a boundary-condition or
                    # shared value, and the first cell next to it can carry a sharp layer, so
                    # interpolating across it measures the cell size, not convergence. Compare
                    # the interior; step quantities are compared by integral instead.
                    if (
                        not integrated
                        and left.centering != "edge"
                        and min(len(xs_old), len(xs_new)) >= 4
                    ):
                        xs_old, ys_old = xs_old[1:-1], ys_old[1:-1]
                        xs_new, ys_new = xs_new[1:-1], ys_new[1:-1]
                    lo, hi = max(xs_old[0], xs_new[0]), min(xs_old[-1], xs_new[-1])
                    grid = np.unique([z for z in (*xs_old, *xs_new) if lo <= z <= hi])
                    if not len(grid):
                        return {**record, "reason": f"No common profile support: {name}."}
                    old_on_grid = np.interp(grid, xs_old, ys_old)
                    new_on_grid = np.interp(grid, xs_new, ys_new)
                    if integrated:
                        old_on_grid = _running_integral(grid, old_on_grid)
                        new_on_grid = _running_integral(grid, new_on_grid)
                    pairs.append((old_on_grid, new_on_grid, group))
                    if imaginary_profiles is not None:
                        old_imag = imaginary_profiles[0][group][0]
                        new_imag = imaginary_profiles[1][group][0]
                        pairs.append(
                            (
                                np.interp(grid, x[a:b], old_imag[a:b]),
                                np.interp(grid, y[c:d], new_imag[c:d]),
                                group + len(profiles),
                            )
                        )
        # Currents below the validation current tolerance and energies below the potential
        # resolution are numerical noise, not a response to compare.
        floor = {
            "A/m^2": current_absolute_tolerance,
            "C/m^2": 1e-10,
            "F/m^2": 1e-10,
            "V": 1e-6,
            "eV": 1e-6,
        }.get(unit, 1e-30)
        if unit == "A" and name.startswith("absolute_terminal_current__"):
            # The same current in amperes is the density times the contact area, so its noise
            # floor is the density floor times that area; otherwise a leakage far below the
            # current tolerance would be compared relatively in one form and ignored in the other.
            density = coarse.datasets.get(
                name.replace("absolute_terminal_current__", "terminal_current_density__", 1)
            )
            if density is not None:
                peak_density = float(np.max(np.abs(np.asarray(density.values, dtype=float))))
                peak_current = float(np.max(np.abs(np.asarray(left.values, dtype=float))))
                if peak_density > 0:
                    floor = current_absolute_tolerance * peak_current / peak_density
        if left.unit == "m^-3/s" and equilibrium:
            # q * integral(delta R dx) is a current-density perturbation. Bound
            # equilibrium-zero rates by the existing continuity resolution.
            # This is mixed absolute/relative resolution, not a claim of
            # relative accuracy for small physical non-equilibrium rates.
            try:
                lengths = [d["x1_m"] - d["x0_m"] for d in coarse.metadata.get("region_domains", [])]
            except (KeyError, TypeError):
                lengths = []
            if lengths and all(math.isfinite(length) and length > 0 for length in lengths):
                floor = max(floor, current_absolute_tolerance / (1.602176634e-19 * sum(lengths)))
        groups = {}
        for a, b, group in pairs:
            old_error, old_scale = groups.get(group, (0.0, floor))
            groups[group] = (
                max(old_error, float(np.max(np.abs(np.array(a) - np.array(b))))),
                max(old_scale, float(np.max(np.abs(a))), float(np.max(np.abs(b)))),
            )
        if unit in {"A/m^2", "A"}:
            # Two currents that both sit below the current tolerance agree on the only thing a
            # reading that small asserts (zero within noise: equilibrium, or an insulated gate with
            # no dc path); their difference is not a response to compare.
            groups = {g: (0.0 if s <= floor else e, s) for g, (e, s) in groups.items()}
        ratio = max((e / s for e, s in groups.values()), default=math.inf)
        record["metrics"].append(
            {
                "dataset": name,
                "relative_linf": ratio,
                "tolerance": relative_tolerance,
                "unit": unit,
                "absolute_floor": floor,
                **({"compared_as": "running integral over position"} if integrated else {}),
                **(
                    {"absolute_floor_basis": "continuity current tolerance / (q * domain length)"}
                    if left.unit == "m^-3/s" and equilibrium and lengths
                    else {}
                ),
                "stable": ratio <= relative_tolerance,
                **({"informational": True} if not _judged(name, requested) else {}),
            }
        )
    missing = set(coarse.datasets) - set(fine.datasets)
    if missing:
        return {**record, "reason": f"Refinement lost datasets: {sorted(missing)}."}
    if not record["metrics"]:
        return {**record, "reason": "No comparable canonical evidence."}
    judged = [m for m in record["metrics"] if not m.get("informational")] or record["metrics"]
    record["status"] = "passed" if all(m["stable"] for m in judged) else "failed"
    return record


def convergence_summary(history: list[dict], safety_factor: float = 1.25) -> dict:
    """Observed order and a fine-grid convergence index per response, from the halvings so far.

    With errors e_prev and e_last from two successive halvings (ratio 2) the apparent order is
    p = log2(e_prev / e_last); Roache's index bounds the error of the finest solution as
    GCI = Fs * e_last / (2**p - 1). It is an error band, not a corrected value, and needs two
    comparisons (three meshes) to exist. Orders are clamped to [0.5, 2], the range a
    first/second-order scheme can honestly show, so noise cannot claim superconvergence.
    """
    series: dict[str, list[float]] = {}
    informational: set[str] = set()
    for comparison in history:
        for metric in comparison.get("metrics", []):
            series.setdefault(metric["dataset"], []).append(float(metric["relative_linf"]))
            if metric.get("informational"):
                informational.add(metric["dataset"])
    datasets = {}
    for name, errors in series.items():
        entry: dict = {"errors": errors, "observed_order": None, "gci_fine": None}
        if len(errors) >= 2 and 0 < errors[-1] < errors[-2]:
            order = min(2.0, max(0.5, math.log2(errors[-2] / errors[-1])))
            entry["observed_order"] = order
            entry["gci_fine"] = safety_factor * errors[-1] / (2**order - 1)
        datasets[name] = entry
    decisive = {n: e for n, e in datasets.items() if n not in informational} or datasets
    bands = [e["gci_fine"] for e in decisive.values() if e["gci_fine"] is not None]
    return {
        "method": "Roache grid convergence index over successive half-spacing solves",
        "safety_factor": safety_factor,
        "datasets": datasets,
        "worst_gci": max(bands) if bands else None,
    }


def _convergence_sentence(record: dict) -> str:
    worst = (record.get("convergence") or {}).get("worst_gci")
    if worst is None:
        return ""
    return (
        f" Fine-mesh grid convergence index (Roache, safety factor 1.25) over "
        f"{len(record.get('comparisons', []))} halvings: {worst:.2%}."
    )


def mesh_stability_check(result: CanonicalResult):
    from tcad_agent.validation.models import ValidationCheck

    record = result.metadata.get("mesh_verification")
    if not isinstance(record, dict):
        return ValidationCheck(
            id="mesh-refinement-stability",
            level="numerical",
            status="not_applicable",
            message="No independent mesh-refinement solve was recorded; "
            "spatial discretization error is unverified.",
            evidence_paths=("result.metadata.mesh_verification",),
        )
    all_metrics = record.get("metrics", [])
    judged = [m for m in all_metrics if not m.get("informational")] or all_metrics
    ratios = [m["relative_linf"] for m in judged]
    unverified = sorted({m["dataset"] for m in all_metrics if m.get("informational")})
    note = (
        f" Not requested, compared for information only and not verified: "
        f"{', '.join(unverified)}."
        if unverified and record.get("status") == "passed"
        else ""
    )
    return ValidationCheck(
        id="mesh-refinement-stability",
        level="numerical",
        status="passed" if record.get("status") == "passed" else "failed",
        measured_value=max(ratios) if ratios else record.get("reason", "comparison unavailable"),
        limit=record.get("relative_tolerance", 0.03),
        unit="1",
        message=record.get(
            "reason",
            "Independent half-spacing solve must preserve the approved response within "
            "the recorded mesh-comparison criteria. One comparison is not asymptotic "
            "convergence or experimental calibration.",
        )
        + _convergence_sentence(record)
        + note,
        evidence_paths=("result.metadata.mesh_verification", "verification/mesh/provenance.json"),
    )
