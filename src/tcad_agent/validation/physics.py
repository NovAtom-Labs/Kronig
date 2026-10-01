"""Generic physical relations over canonical datasets."""

from __future__ import annotations

import statistics

from tcad_agent.results.datasets import AxisKind, Dataset
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.datasets import axes_compatible
from tcad_agent.validation.models import ValidationCheck


def _position_profiles(
    result: CanonicalResult,
    dataset: Dataset,
) -> tuple[
    tuple[float, ...],
    tuple[str, tuple[float, ...]] | None,
    tuple[tuple[tuple[float, ...], tuple[bool, ...]], ...],
]:
    position_indices = [
        index
        for index, axis_id in enumerate(dataset.axes)
        if result.axes[axis_id].kind is AxisKind.POSITION
    ]
    if len(position_indices) != 1 or len(dataset.axes) not in {1, 2}:
        raise ValueError("field dataset must have one position axis and at most one study axis")
    position_index = position_indices[0]
    positions = result.axes[dataset.axes[position_index]].values
    validity = dataset.validity or (True,) * len(dataset.values)
    if len(dataset.axes) == 1:
        return positions, None, ((dataset.values, validity),)
    other_index = 1 - position_index
    other_axis = result.axes[dataset.axes[other_index]]
    profiles: list[tuple[tuple[float, ...], tuple[bool, ...]]] = []
    if position_index == 1:
        width = dataset.shape[1]
        for index in range(dataset.shape[0]):
            start = index * width
            profiles.append(
                (
                    dataset.values[start : start + width],
                    validity[start : start + width],
                )
            )
    else:
        width = dataset.shape[1]
        for index in range(width):
            profiles.append(
                (
                    tuple(
                        dataset.values[offset * width + index]
                        for offset in range(dataset.shape[0])
                    ),
                    tuple(
                        validity[offset * width + index]
                        for offset in range(dataset.shape[0])
                    ),
                )
            )
    return positions, (str(other_axis.kind), other_axis.values), tuple(profiles)


def physics_checks(
    result: CanonicalResult,
    *,
    field_rtol: float = 1e-6,
    field_atol_v_per_m: float = 1e-3,
) -> tuple[ValidationCheck, ...]:
    potential = result.datasets.get("potential")
    electric = result.datasets.get("electric_field")
    if potential is None or electric is None:
        return (
            ValidationCheck(
                id="electric-field-potential-gradient",
                level="physical",
                status="not_applicable",
                message="Potential and electric field datasets were not both requested.",
                evidence_paths=("result.datasets.potential", "result.datasets.electric_field"),
            ),
        )
    if potential.source == "legacy-field-migration" or electric.source == "legacy-field-migration":
        return (
            ValidationCheck(
                id="electric-field-potential-gradient",
                level="physical",
                status="not_applicable",
                message="Legacy fields lack reviewed centering provenance for this relation.",
                evidence_origin="configured",
                evidence_paths=("result.datasets",),
            ),
        )
    if potential.unit != "V" or electric.unit != "V/m":
        return (_failed_field_check("incompatible canonical units"),)
    try:
        x_potential, potential_study_axis, potential_profiles = _position_profiles(
            result, potential
        )
        _x_electric, electric_study_axis, electric_profiles = _position_profiles(
            result, electric
        )
    except ValueError as exc:
        return (_failed_field_check(str(exc)),)
    if (
        potential_study_axis != electric_study_axis
        or len(potential_profiles) != len(electric_profiles)
    ):
        return (_failed_field_check("potential and field study axes do not match"),)
    gradients: list[float] = []
    measured_fields: list[float] = []
    for (potential_values, potential_valid), (field_values, field_valid) in zip(
        potential_profiles, electric_profiles, strict=True
    ):
        if not all((*potential_valid, *field_valid)):
            continue
        profile_gradients: list[float] = []
        for left_x, right_x, left_v, right_v in zip(
            x_potential[:-1],
            x_potential[1:],
            potential_values[:-1],
            potential_values[1:],
            strict=True,
        ):
            delta = right_x - left_x
            if delta != 0:
                profile_gradients.append(-(right_v - left_v) / delta)
        if len(profile_gradients) != len(field_values):
            return (_failed_field_check("node-edge topology mismatch"),)
        gradients.extend(profile_gradients)
        measured_fields.extend(field_values)
    if not gradients:
        return (_failed_field_check("no converged field profile is available"),)
    if len(gradients) != len(measured_fields):
        return (_failed_field_check("node-edge topology mismatch"),)
    maximum_error = max(
        (
            abs(expected - measured)
            for expected, measured in zip(gradients, measured_fields, strict=True)
        ),
        default=0.0,
    )
    scale = max((abs(value) for value in (*gradients, *measured_fields)), default=0.0)
    limit = field_atol_v_per_m + field_rtol * scale
    return (
        ValidationCheck(
            id="electric-field-potential-gradient",
            level="physical",
            status="passed" if maximum_error <= limit else "failed",
            measured_value=maximum_error,
            limit=limit,
            message="Electric field must equal the negative spatial gradient of potential.",
            evidence_origin="derived",
            evidence_paths=("result.datasets.potential", "result.datasets.electric_field"),
        ),
    )


def poisson_residual_checks(
    result: CanonicalResult,
    *,
    relative_tolerance: float = 5e-2,
    absolute_tolerance_c_per_m3: float = 1e-3,
) -> tuple[ValidationCheck, ...]:
    """Check div(D) = rho on compatible canonical one-dimensional fields."""

    flux = result.datasets.get("electrostatic_flux")
    charge = result.datasets.get("charge_density")
    identifier = "poisson-residual-consistency"
    paths = (
        "result.datasets.electrostatic_flux",
        "result.datasets.charge_density",
    )
    if flux is None or charge is None:
        return (
            ValidationCheck(
                id=identifier,
                level="physical",
                status="not_applicable",
                message="Electrostatic flux and charge density were not both requested.",
                evidence_paths=paths,
            ),
        )
    if flux.unit != "C/m^2" or charge.unit != "C/m^3":
        return (_failed_poisson_check("incompatible canonical units", paths),)
    try:
        flux_positions, flux_study, flux_profiles = _position_profiles(result, flux)
        node_positions, charge_study, charge_profiles = _position_profiles(result, charge)
    except ValueError as exc:
        return (_failed_poisson_check(str(exc), paths),)
    if flux_study != charge_study or len(flux_profiles) != len(charge_profiles):
        return (_failed_poisson_check("flux and charge study axes do not match", paths),)
    errors: list[float] = []
    scales: list[float] = []
    for (flux_values, flux_valid), (charge_values, charge_valid) in zip(
        flux_profiles, charge_profiles, strict=True
    ):
        segment_start = 0
        segment_bounds: list[tuple[int, int]] = []
        for index in range(1, len(node_positions)):
            if node_positions[index] <= node_positions[index - 1]:
                segment_bounds.append((segment_start, index))
                segment_start = index
        segment_bounds.append((segment_start, len(node_positions)))
        for start, stop in segment_bounds:
            segment_positions = node_positions[start:stop]
            if len(segment_positions) < 3:
                continue
            edge_indices = tuple(
                index
                for index, position in enumerate(flux_positions)
                if segment_positions[0] < position < segment_positions[-1]
            )
            if len(edge_indices) + 1 != len(segment_positions):
                return (_failed_poisson_check("node-edge topology mismatch", paths),)
            for local_index in range(1, len(segment_positions) - 1):
                left_edge = edge_indices[local_index - 1]
                right_edge = edge_indices[local_index]
                charge_index = start + local_index
                if not (
                    flux_valid[left_edge]
                    and flux_valid[right_edge]
                    and charge_valid[charge_index]
                ):
                    continue
                control_width = (
                    segment_positions[local_index + 1]
                    - segment_positions[local_index - 1]
                ) / 2
                if control_width <= 0:
                    return (
                        _failed_poisson_check(
                            "position coordinates are not increasing", paths
                        ),
                    )
                divergence = (
                    flux_values[right_edge] - flux_values[left_edge]
                ) / control_width
                density = charge_values[charge_index]
                errors.append(abs(divergence - density))
                scales.append(max(abs(divergence), abs(density)))
    if not errors:
        return (_failed_poisson_check("no valid interior control volume is available", paths),)
    maximum_error = max(errors)
    limit = absolute_tolerance_c_per_m3 + relative_tolerance * max(scales)
    return (
        ValidationCheck(
            id=identifier,
            level="physical",
            status="passed" if maximum_error <= limit else "failed",
            measured_value=maximum_error,
            limit=limit,
            message="The divergence of electric displacement flux must equal charge density.",
            evidence_origin="derived",
            evidence_paths=paths,
        ),
    )


def _failed_poisson_check(
    reason: str, paths: tuple[str, str]
) -> ValidationCheck:
    return ValidationCheck(
        id="poisson-residual-consistency",
        level="physical",
        status="failed",
        measured_value=reason,
        limit="compatible node and edge datasets",
        message="The canonical Poisson residual could not be evaluated consistently.",
        evidence_paths=paths,
    )


def sweep_continuity_checks(
    result: CanonicalResult,
    *,
    maximum_slope_outlier_ratio: float = 1000.0,
) -> tuple[ValidationCheck, ...]:
    """Detect isolated numerical outliers without assuming monotonic device response."""

    candidates = [
        dataset
        for dataset in result.datasets.values()
        if len(dataset.axes) == 1
        and result.axes[dataset.axes[0]].kind is AxisKind.BIAS
        and len(dataset.values) >= 5
        and dataset.centering.value in {"contact", "operating_point"}
    ]
    if not candidates:
        return (
            ValidationCheck(
                id="sweep-continuity",
                level="numerical",
                status="not_applicable",
                message="No eligible canonical bias sweep contains at least five points.",
                evidence_paths=("result.datasets",),
            ),
        )
    worst_ratio = 0.0
    worst_dataset = ""
    for dataset in candidates:
        axis = result.axes[dataset.axes[0]]
        validity = dataset.validity or (True,) * len(dataset.values)
        slopes: list[float] = []
        for left, right in zip(
            range(len(dataset.values) - 1),
            range(1, len(dataset.values)),
            strict=True,
        ):
            if not (validity[left] and validity[right]):
                continue
            step = axis.values[right] - axis.values[left]
            if step == 0:
                continue
            slopes.append(abs((dataset.values[right] - dataset.values[left]) / step))
        positive = sorted(value for value in slopes if value > 0)
        if len(positive) < 3:
            continue
        baseline_count = max(1, len(positive) // 2)
        baseline = statistics.median(positive[:baseline_count])
        ratio = max(positive) / baseline
        if ratio > worst_ratio:
            worst_ratio = ratio
            worst_dataset = dataset.id
    if not worst_dataset:
        return (
            ValidationCheck(
                id="sweep-continuity",
                level="numerical",
                status="not_applicable",
                message="Eligible sweeps contain too few valid nonzero secant slopes.",
                evidence_paths=("result.datasets",),
            ),
        )
    return (
        ValidationCheck(
            id="sweep-continuity",
            level="numerical",
            status="passed" if worst_ratio <= maximum_slope_outlier_ratio else "failed",
            measured_value=worst_ratio,
            limit=maximum_slope_outlier_ratio,
            message=(
                "No isolated bias-sweep secant slope may exceed the reviewed robust "
                f"outlier ratio; worst dataset: {worst_dataset}."
            ),
            evidence_origin="derived",
            evidence_paths=(f"result.datasets.{worst_dataset}",),
        ),
    )


def capacitance_consistency_checks(
    result: CanonicalResult,
    *,
    relative_tolerance: float = 5e-2,
    absolute_tolerance_f_per_m2: float = 1e-12,
) -> tuple[ValidationCheck, ...]:
    """Compare low-frequency AC and quasi-static capacitance when paired evidence exists."""

    identifier = "ac-quasistatic-capacitance-consistency"
    comparisons: list[tuple[str, float, float]] = []
    for name, ac in result.datasets.items():
        if not name.startswith("ac_capacitance__"):
            continue
        terminal = name.removeprefix("ac_capacitance__")
        quasistatic = result.datasets.get(f"capacitance__{terminal}")
        operating_point = ac.metadata.get("dc_operating_point_v")
        if quasistatic is None or operating_point is None:
            continue
        if ac.unit != "F/m^2" or quasistatic.unit != ac.unit:
            continue
        if len(ac.axes) != 1 or len(quasistatic.axes) != 1:
            continue
        frequency_axis = result.axes[ac.axes[0]]
        bias_axis = result.axes[quasistatic.axes[0]]
        if (
            frequency_axis.kind is not AxisKind.FREQUENCY
            or bias_axis.kind is not AxisKind.BIAS
        ):
            continue
        frequency_index = min(
            range(len(frequency_axis.values)), key=frequency_axis.values.__getitem__
        )
        target_bias = float(operating_point)
        bias_index = min(
            range(len(bias_axis.values)),
            key=lambda index: abs(bias_axis.values[index] - target_bias),
        )
        comparisons.append(
            (terminal, ac.values[frequency_index], quasistatic.values[bias_index])
        )
    if not comparisons:
        return (
            ValidationCheck(
                id=identifier,
                level="physical",
                status="not_applicable",
                message=(
                    "A paired low-frequency AC and quasi-static capacitance result at "
                    "a recorded DC operating point is unavailable."
                ),
                evidence_paths=("result.datasets",),
            ),
        )
    relative_errors = [
        abs(ac_value - qs_value) / max(abs(ac_value), abs(qs_value), absolute_tolerance_f_per_m2)
        for _terminal, ac_value, qs_value in comparisons
    ]
    worst_index = max(range(len(relative_errors)), key=relative_errors.__getitem__)
    terminal, _ac_value, _qs_value = comparisons[worst_index]
    worst_error = relative_errors[worst_index]
    return (
        ValidationCheck(
            id=identifier,
            level="physical",
            status="passed" if worst_error <= relative_tolerance else "failed",
            measured_value=worst_error,
            limit=relative_tolerance,
            message=(
                "Low-frequency AC capacitance must agree with the paired "
                f"quasi-static derivative; worst terminal: {terminal}."
            ),
            evidence_origin="derived",
            evidence_paths=(
                f"result.datasets.ac_capacitance__{terminal}",
                f"result.datasets.capacitance__{terminal}",
            ),
        ),
    )
def _failed_field_check(reason: str) -> ValidationCheck:
    return ValidationCheck(
        id="electric-field-potential-gradient",
        level="physical",
        status="failed",
        measured_value=reason,
        limit="compatible node and edge datasets",
        message="Electric field could not be reconciled with the potential gradient.",
        evidence_paths=("result.datasets.potential", "result.datasets.electric_field"),
    )


def band_checks(result: CanonicalResult) -> tuple[ValidationCheck, ...]:
    conduction = result.datasets.get("conduction_band")
    valence = result.datasets.get("valence_band")
    if conduction is None or valence is None:
        return (
            ValidationCheck(
                id="band-ordering",
                level="physical",
                status="not_applicable",
                message="Both canonical band-energy fields are required.",
                evidence_paths=(
                    "result.datasets.conduction_band",
                    "result.datasets.valence_band",
                ),
            ),
        )
    compatible = (
        conduction.unit == "eV"
        and valence.unit == "eV"
        and axes_compatible(result, conduction, valence)
    )
    if not compatible:
        return (
            ValidationCheck(
                id="band-ordering",
                level="physical",
                status="failed",
                measured_value="incompatible canonical band datasets",
                limit="matching eV datasets",
                message="Conduction and valence bands must share axes, shape, and units.",
                evidence_paths=(
                    "result.datasets.conduction_band",
                    "result.datasets.valence_band",
                ),
            ),
        )
    conduction_validity = conduction.validity or (True,) * len(conduction.values)
    valence_validity = valence.validity or (True,) * len(valence.values)
    gaps = tuple(
        ec - ev
        for ec, ev, ec_valid, ev_valid in zip(
            conduction.values,
            valence.values,
            conduction_validity,
            valence_validity,
            strict=True,
        )
        if ec_valid and ev_valid
    )
    minimum_gap = min(gaps, default=float("-inf"))
    return (
        ValidationCheck(
            id="band-ordering",
            level="physical",
            status="passed" if gaps and minimum_gap > 0 else "failed",
            measured_value=minimum_gap,
            limit="> 0 eV",
            message="Conduction-band energy must exceed valence-band energy.",
            evidence_origin="derived",
            evidence_paths=(
                "result.datasets.conduction_band",
                "result.datasets.valence_band",
            ),
        ),
    )


def recombination_checks(
    result: CanonicalResult,
    *,
    relative_tolerance: float = 1e-8,
    absolute_tolerance: float = 1e-12,
) -> tuple[ValidationCheck, ...]:
    """Verify canonical recombination decomposition and generation sign."""

    srh = result.datasets.get("srh_recombination_rate")
    auger = result.datasets.get("auger_recombination_rate")
    total = result.datasets.get("total_recombination_rate")
    electron_generation = result.datasets.get("electron_generation_rate")
    hole_generation = result.datasets.get("hole_generation_rate")

    component_check = _rate_identity_check(
        "recombination-component-balance",
        "Total recombination must equal the sum of SRH and Auger rates.",
        total,
        srh,
        auger,
        signs=(1.0, 1.0),
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
        result=result,
    )
    generation_check = _rate_identity_check(
        "generation-recombination-sign",
        "Electron and hole net generation must equal negative total recombination.",
        total,
        electron_generation,
        hole_generation,
        signs=(-1.0, -1.0),
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
        result=result,
    )
    return component_check, generation_check


def _rate_identity_check(
    identifier: str,
    message: str,
    reference: Dataset | None,
    first: Dataset | None,
    second: Dataset | None,
    *,
    signs: tuple[float, float],
    relative_tolerance: float,
    absolute_tolerance: float,
    result: CanonicalResult,
) -> ValidationCheck:
    if reference is None or first is None or second is None:
        return ValidationCheck(
            id=identifier,
            level="physical",
            status="not_applicable",
            message="Required canonical rate datasets were not all requested.",
            evidence_paths=("result.datasets",),
        )
    compatible = (
        reference.unit == first.unit == second.unit
        and axes_compatible(result, reference, first)
        and axes_compatible(result, reference, second)
    )
    if not compatible:
        return ValidationCheck(
            id=identifier,
            level="physical",
            status="failed",
            measured_value="incompatible rate datasets",
            limit="matching axes, shape, and units",
            message=message,
            evidence_paths=("result.datasets",),
        )
    errors: list[float] = []
    scales: list[float] = []
    for reference_value, first_value, second_value in zip(
        reference.values, first.values, second.values, strict=True
    ):
        errors.extend(
            (
                abs(first_value - signs[0] * reference_value),
                abs(second_value - signs[1] * reference_value),
            )
        )
        scales.extend((abs(reference_value), abs(first_value), abs(second_value)))
    if identifier == "recombination-component-balance":
        errors = [
            abs(reference_value - first_value - second_value)
            for reference_value, first_value, second_value in zip(
                reference.values, first.values, second.values, strict=True
            )
        ]
    maximum_error = max(errors, default=0.0)
    limit = absolute_tolerance + relative_tolerance * max(scales, default=0.0)
    return ValidationCheck(
        id=identifier,
        level="physical",
        status="passed" if maximum_error <= limit else "failed",
        measured_value=maximum_error,
        limit=limit,
        message=message,
        evidence_origin="derived",
        evidence_paths=("result.datasets",),
    )
