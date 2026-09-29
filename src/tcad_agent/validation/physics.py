"""Generic physical relations over canonical datasets."""

from __future__ import annotations

from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationCheck


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
    x_potential = result.axes[potential.axes[0]].values
    gradients: list[float] = []
    for left_x, right_x, left_v, right_v in zip(
        x_potential[:-1],
        x_potential[1:],
        potential.values[:-1],
        potential.values[1:],
        strict=True,
    ):
        delta = right_x - left_x
        if delta != 0:
            gradients.append(-(right_v - left_v) / delta)
    if len(gradients) != len(electric.values):
        return (_failed_field_check("node-edge topology mismatch"),)
    maximum_error = max(
        (
            abs(expected - measured)
            for expected, measured in zip(gradients, electric.values, strict=True)
        ),
        default=0.0,
    )
    scale = max((abs(value) for value in (*gradients, *electric.values)), default=0.0)
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
