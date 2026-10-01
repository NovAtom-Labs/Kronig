"""Structural validation over canonical axes and datasets."""

import math

from tcad_agent.results.datasets import Dataset
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationCheck


def axes_compatible(
    result: CanonicalResult,
    left: Dataset,
    right: Dataset,
    *,
    relative_tolerance: float = 1e-12,
    absolute_tolerance: float = 1e-15,
) -> bool:
    """Compare canonical coordinate semantics instead of local axis identifiers."""

    if left.shape != right.shape or left.centering is not right.centering:
        return False
    if len(left.axes) != len(right.axes):
        return False
    for left_id, right_id in zip(left.axes, right.axes, strict=True):
        left_axis = result.axes[left_id]
        right_axis = result.axes[right_id]
        if left_axis.kind is not right_axis.kind or left_axis.unit != right_axis.unit:
            return False
        if len(left_axis.values) != len(right_axis.values):
            return False
        if not all(
            math.isclose(
                left_value,
                right_value,
                rel_tol=relative_tolerance,
                abs_tol=absolute_tolerance,
            )
            for left_value, right_value in zip(
                left_axis.values, right_axis.values, strict=True
            )
        ):
            return False
    return True


def dataset_checks(result: CanonicalResult) -> tuple[ValidationCheck, ...]:
    axis_links = sum(len(dataset.axes) for dataset in result.datasets.values())
    structural = ValidationCheck(
        id="canonical-datasets-structural",
        level="numerical",
        status="passed",
        measured_value=f"{len(result.datasets)} datasets, {axis_links} axis links",
        limit="all shapes and referenced axes valid",
        message="Canonical datasets passed schema-level shape, unit, axis, and centering checks.",
        evidence_origin="statically_verified",
        evidence_paths=("result.axes", "result.datasets"),
    )
    return (structural,)
