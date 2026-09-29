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
