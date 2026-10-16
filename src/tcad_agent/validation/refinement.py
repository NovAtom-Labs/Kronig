"""Portable mesh refinement and canonical response comparison."""

import math
from itertools import pairwise

import numpy as np

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.units import QuantityValue
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.physics import _position_profiles


def refined_spec(spec: ExperimentSpec) -> ExperimentSpec:
    def half(value):
        return QuantityValue.model_validate(f"{value.to('m') / 2:.17g} m") if value else None

    regions = []
    for region in spec.regions:
        base = region.mesh_spacing or QuantityValue.model_validate(
            f"{(region.x1.to('m') - region.x0.to('m')) / 50:.17g} m"
        )
        regions.append(
            region.model_copy(
                update={
                    "mesh_spacing": half(base),
                    "minimum_mesh_spacing": half(region.minimum_mesh_spacing),
                    "maximum_mesh_spacing": half(region.maximum_mesh_spacing),
                }
            )
        )
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


def mesh_comparison(
    coarse: CanonicalResult, fine: CanonicalResult, relative_tolerance: float = 0.03,
    *, current_absolute_tolerance: float = 1e-6, equilibrium: bool = False,
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
        if (left.validity and not all(left.validity)) or (
            right.validity and not all(right.validity)
        ):
            return {**record, "reason": f"Invalid refinement samples: {name}."}
        position = any(coarse.axes[a].kind == "position" for a in left.axes)
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
                starts = (
                    [0]
                    + [i for i in range(1, len(coords)) if coords[i] <= coords[i - 1]]
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
            for group, ((old, _), (new, _)) in enumerate(zip(profiles, fine_profiles, strict=True)):
                for (a, b), (c, d) in zip(old_segments, new_segments, strict=True):
                    # Edge centers differ with mesh spacing; compare only common support.
                    lo, hi = max(x[a], y[c]), min(x[b - 1], y[d - 1])
                    grid = np.unique([z for z in (*x[a:b], *y[c:d]) if lo <= z <= hi])
                    if not len(grid):
                        return {**record, "reason": f"No common profile support: {name}."}
                    pairs.append(
                        (
                            np.interp(grid, x[a:b], old[a:b]),
                            np.interp(grid, y[c:d], new[c:d]),
                            group,
                        )
                    )
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
        floor = {"A/m^2": 1e-6, "C/m^2": 1e-10, "F/m^2": 1e-10, "V": 1e-6}.get(left.unit, 1e-30)
        if left.unit == "m^-3/s" and equilibrium:
            # q * integral(delta R dx) is a current-density perturbation. Bound
            # equilibrium-zero rates by the existing continuity resolution.
            # This is mixed absolute/relative resolution, not a claim of
            # relative accuracy for small physical non-equilibrium rates.
            try:
                lengths = [d["x1_m"] - d["x0_m"]
                           for d in coarse.metadata.get("region_domains", [])]
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
        ratio = max((e / s for e, s in groups.values()), default=math.inf)
        record["metrics"].append(
            {
                "dataset": name,
                "relative_linf": ratio,
                "tolerance": relative_tolerance,
                "unit": left.unit,
                "absolute_floor": floor,
                **({"absolute_floor_basis": "continuity current tolerance / (q * domain length)"}
                   if left.unit == "m^-3/s" and equilibrium and lengths else {}),
                "stable": ratio <= relative_tolerance,
            }
        )
    missing = set(coarse.datasets) - set(fine.datasets)
    if missing:
        return {**record, "reason": f"Refinement lost datasets: {sorted(missing)}."}
    if not record["metrics"]:
        return {**record, "reason": "No comparable canonical evidence."}
    record["status"] = "passed" if all(m["stable"] for m in record["metrics"]) else "failed"
    return record


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
    ratios = [m["relative_linf"] for m in record.get("metrics", [])]
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
        ),
        evidence_paths=("result.metadata.mesh_verification", "verification/mesh/provenance.json"),
    )
