"""Backend-neutral renderer catalog derived only from canonical dataset metadata."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from tcad_agent.domain.models import StrictModel
from tcad_agent.results.datasets import AxisKind, Dataset
from tcad_agent.results.models import CanonicalResult


class ResultViewKind(StrEnum):
    SCALAR = "scalar"
    CURVE = "curve"
    PROFILE_FAMILY = "profile_family"
    HEATMAP = "heatmap"
    COMPLEX_RESPONSE = "complex_response"
    TABLE = "table"


class DatasetCatalogEntry(StrictModel):
    id: str
    label: str
    unit: str
    view: ResultViewKind
    axis_ids: tuple[str, ...]
    shape: tuple[int, ...]
    centering: str
    complex_values: bool
    valid_count: int = Field(ge=0)
    sample_count: int = Field(ge=1)
    source: str


def _view_for(dataset: Dataset, result: CanonicalResult) -> ResultViewKind:
    rank = len(dataset.axes)
    if rank == 0:
        return ResultViewKind.SCALAR
    if rank == 1 and dataset.imaginary_values is not None:
        return ResultViewKind.COMPLEX_RESPONSE
    if rank == 1:
        return ResultViewKind.CURVE
    if rank == 2:
        kinds = {result.axes[axis_id].kind for axis_id in dataset.axes}
        if AxisKind.POSITION in kinds:
            return ResultViewKind.PROFILE_FAMILY
        return ResultViewKind.HEATMAP
    return ResultViewKind.TABLE


def build_dataset_catalog(result: CanonicalResult) -> tuple[DatasetCatalogEntry, ...]:
    """Classify canonical datasets without inspecting device names or backend syntax."""

    entries = []
    for dataset in sorted(result.datasets.values(), key=lambda item: item.id):
        sample_count = len(dataset.values)
        entries.append(
            DatasetCatalogEntry(
                id=dataset.id,
                label=dataset.label,
                unit=dataset.unit,
                view=_view_for(dataset, result),
                axis_ids=dataset.axes,
                shape=dataset.shape,
                centering=dataset.centering.value,
                complex_values=dataset.imaginary_values is not None,
                valid_count=(
                    sum(dataset.validity) if dataset.validity is not None else sample_count
                ),
                sample_count=sample_count,
                source=dataset.source,
            )
        )
    return tuple(entries)
