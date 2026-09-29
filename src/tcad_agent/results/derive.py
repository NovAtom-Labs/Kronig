"""Generic derivations computed only from canonical datasets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import OperatingPoint


@dataclass(frozen=True)
class ScalarDerivation:
    operation: str
    value: float
    unit: str
    source_dataset: str
    coordinate: float | None = None
    coordinate_unit: str | None = None


ScalarFunction = Callable[[Dataset, Mapping[str, ScientificAxis]], ScalarDerivation]
DatasetFunction = Callable[[Dataset, Mapping[str, ScientificAxis]], Dataset]


class DerivationRegistry:
    def __init__(
        self,
        *,
        scalars: Mapping[str, ScalarFunction],
        datasets: Mapping[str, DatasetFunction],
    ) -> None:
        self._scalars = dict(scalars)
        self._datasets = dict(datasets)

    @classmethod
    def default(cls) -> DerivationRegistry:
        return cls(
            scalars={
                "minimum": lambda dataset, axes: _extremum(dataset, "minimum"),
                "maximum": lambda dataset, axes: _extremum(dataset, "maximum"),
                "endpoint_difference": _endpoint_difference,
                "integral": _integral,
                "average": _average,
                "peak_magnitude": _peak_magnitude,
                "built_in_potential": _built_in_potential,
            },
            datasets={"gradient": _gradient, "derivative": _gradient},
        )

    def scalar(
        self,
        operation: str,
        dataset: Dataset,
        axes: Mapping[str, ScientificAxis],
    ) -> ScalarDerivation:
        try:
            derive = self._scalars[operation]
        except KeyError as exc:
            raise KeyError(f"unknown scalar derivation: {operation}") from exc
        return derive(dataset, axes)

    def dataset(
        self,
        operation: str,
        dataset: Dataset,
        axes: Mapping[str, ScientificAxis],
    ) -> Dataset:
        try:
            derive = self._datasets[operation]
        except KeyError as exc:
            raise KeyError(f"unknown dataset derivation: {operation}") from exc
        return derive(dataset, axes)

    @staticmethod
    def current_balance(point: OperatingPoint) -> ScalarDerivation:
        return ScalarDerivation(
            operation="current_balance",
            value=sum(point.terminal_currents_a_per_m2.values()),
            unit="A/m^2",
            source_dataset=f"operating_point:{point.index}",
        )


def _require_rank_one(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScientificAxis:
    if len(dataset.axes) != 1:
        raise ValueError("derivation requires a rank-one dataset")
    try:
        return axes[dataset.axes[0]]
    except KeyError as exc:
        raise ValueError("derivation axis is unavailable") from exc


def _extremum(dataset: Dataset, operation: str) -> ScalarDerivation:
    value = min(dataset.values) if operation == "minimum" else max(dataset.values)
    return ScalarDerivation(operation, value, dataset.unit, dataset.id)


def _endpoint_difference(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    _require_rank_one(dataset, axes)
    return ScalarDerivation(
        "endpoint_difference",
        dataset.values[-1] - dataset.values[0],
        dataset.unit,
        dataset.id,
    )


def _integral(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    axis = _require_rank_one(dataset, axes)
    value = sum(
        (right_x - left_x) * (left_y + right_y) / 2
        for left_x, right_x, left_y, right_y in zip(
            axis.values[:-1],
            axis.values[1:],
            dataset.values[:-1],
            dataset.values[1:],
            strict=True,
        )
    )
    return ScalarDerivation("integral", value, f"{dataset.unit}*{axis.unit}", dataset.id)


def _average(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    del axes
    return ScalarDerivation(
        "average",
        sum(dataset.values) / len(dataset.values),
        dataset.unit,
        dataset.id,
    )


def _peak_magnitude(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    axis = _require_rank_one(dataset, axes)
    index = max(range(len(dataset.values)), key=lambda item: abs(dataset.values[item]))
    return ScalarDerivation(
        "peak_magnitude",
        abs(dataset.values[index]),
        dataset.unit,
        dataset.id,
        coordinate=axis.values[index],
        coordinate_unit=axis.unit,
    )


def _built_in_potential(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    _require_rank_one(dataset, axes)
    if dataset.unit != "V":
        raise ValueError("built-in potential requires a canonical voltage dataset")
    return ScalarDerivation(
        "built_in_potential",
        max(dataset.values) - min(dataset.values),
        "V",
        dataset.id,
    )


def _gradient(dataset: Dataset, axes: Mapping[str, ScientificAxis]) -> Dataset:
    axis = _require_rank_one(dataset, axes)
    if len(axis.values) != len(dataset.values):
        raise ValueError("axis length does not match dataset values")
    if len(dataset.values) < 2:
        raise ValueError("derivative requires at least two points")
    result: list[float] = []
    for index, value in enumerate(dataset.values):
        del value
        if index == 0:
            left = 0
            right = 1
        elif index == len(dataset.values) - 1:
            left = index - 1
            right = index
        else:
            left = index - 1
            right = index + 1
        delta = axis.values[right] - axis.values[left]
        if delta == 0:
            raise ValueError("derivative axis contains repeated coordinates")
        result.append((dataset.values[right] - dataset.values[left]) / delta)
    return Dataset(
        id=f"{dataset.id}__gradient",
        label=f"Gradient of {dataset.label}",
        unit=f"{dataset.unit}/{axis.unit}",
        axes=dataset.axes,
        shape=dataset.shape,
        centering=dataset.centering,
        values=tuple(result),
        source=f"derived:gradient:{dataset.id}",
    )
