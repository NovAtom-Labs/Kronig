"""Bounded, backend-neutral queries over immutable canonical result datasets."""

from __future__ import annotations

from pydantic import Field

from tcad_agent.domain.models import StrictModel
from tcad_agent.results.datasets import ScientificAxis
from tcad_agent.results.downsampling import extrema_preserving_indices
from tcad_agent.results.models import CanonicalResult


class DatasetQueryError(ValueError):
    """A requested dataset view is ambiguous or outside bounded query support."""


class DatasetQueryResult(StrictModel):
    id: str
    label: str
    unit: str
    axes: tuple[ScientificAxis, ...]
    shape: tuple[int, ...]
    values: tuple[float, ...]
    imaginary_values: tuple[float, ...] | None = None
    validity: tuple[bool, ...] | None = None
    selection: dict[str, float] = Field(default_factory=dict)
    source: str


def _selected[T](values: tuple[T, ...] | None, indices: tuple[int, ...]) -> tuple[T, ...] | None:
    if values is None:
        return None
    return tuple(values[index] for index in indices)


def _bounded_indices(
    values: tuple[float, ...],
    validity: tuple[bool, ...] | None,
    max_points: int,
) -> tuple[int, ...]:
    if len(values) <= max_points:
        return tuple(range(len(values)))
    return extrema_preserving_indices(
        values,
        max_points=max_points,
        validity=validity,
    )


def query_dataset(
    result: CanonicalResult,
    dataset_id: str,
    *,
    max_points: int,
    slice_axis: str | None = None,
    slice_index: int | None = None,
) -> DatasetQueryResult:
    if not 4 <= max_points <= 50_000:
        raise DatasetQueryError("max_points must be between 4 and 50000")
    dataset = result.datasets.get(dataset_id)
    if dataset is None:
        raise DatasetQueryError(f"canonical dataset does not exist: {dataset_id}")
    rank = len(dataset.axes)
    selection: dict[str, float] = {}
    if rank == 0:
        axes: tuple[ScientificAxis, ...] = ()
        values = dataset.values
        imaginary = dataset.imaginary_values
        validity = dataset.validity
    elif rank == 1:
        if slice_axis is not None or slice_index is not None:
            raise DatasetQueryError("rank-one datasets do not accept a slice")
        axis = result.axes[dataset.axes[0]]
        indices = _bounded_indices(dataset.values, dataset.validity, max_points)
        axes = (
            axis.model_copy(
                update={"values": tuple(axis.values[index] for index in indices)}
            ),
        )
        values = tuple(dataset.values[index] for index in indices)
        imaginary = _selected(dataset.imaginary_values, indices)
        validity = _selected(dataset.validity, indices)
    elif rank == 2:
        if slice_axis is None or slice_index is None:
            raise DatasetQueryError("rank-two datasets require one explicit slice")
        if slice_axis not in dataset.axes:
            raise DatasetQueryError("slice axis is not part of the dataset")
        selected_dimension = dataset.axes.index(slice_axis)
        selected_axis = result.axes[slice_axis]
        if not 0 <= slice_index < dataset.shape[selected_dimension]:
            raise DatasetQueryError("slice index is outside the selected axis")
        remaining_dimension = 1 - selected_dimension
        remaining_axis = result.axes[dataset.axes[remaining_dimension]]
        rows, columns = dataset.shape
        offsets = (
            tuple(slice_index * columns + column for column in range(columns))
            if selected_dimension == 0
            else tuple(row * columns + slice_index for row in range(rows))
        )
        sliced_values = tuple(dataset.values[index] for index in offsets)
        sliced_validity = _selected(dataset.validity, offsets)
        indices = _bounded_indices(sliced_values, sliced_validity, max_points)
        axes = (
            remaining_axis.model_copy(
                update={
                    "values": tuple(
                        remaining_axis.values[index] for index in indices
                    )
                }
            ),
        )
        values = tuple(sliced_values[index] for index in indices)
        sliced_imaginary = _selected(dataset.imaginary_values, offsets)
        imaginary = _selected(sliced_imaginary, indices)
        validity = _selected(sliced_validity, indices)
        selection[slice_axis] = selected_axis.values[slice_index]
    else:
        raise DatasetQueryError(
            "datasets above rank two require a future multi-axis selection contract"
        )
    return DatasetQueryResult(
        id=dataset.id,
        label=dataset.label,
        unit=dataset.unit,
        axes=axes,
        shape=(len(values),) if axes else (),
        values=values,
        imaginary_values=imaginary,
        validity=validity,
        selection=selection,
        source=dataset.source,
    )
