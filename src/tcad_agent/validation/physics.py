"""Generic physical relations over canonical datasets."""

from __future__ import annotations

from tcad_agent.results.datasets import AxisKind, Dataset
from tcad_agent.results.models import CanonicalResult
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
        and conduction.axes == valence.axes
        and conduction.shape == valence.shape
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
        and reference.axes == first.axes == second.axes
        and reference.shape == first.shape == second.shape
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
