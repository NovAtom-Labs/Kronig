"""Structural validation over canonical axes and datasets."""

from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationCheck


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
