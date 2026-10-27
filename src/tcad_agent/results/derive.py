"""Generic derivations computed only from canonical datasets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math
from itertools import pairwise

from tcad_agent.results.datasets import AxisKind, Dataset, ScientificAxis
from tcad_agent.results.models import OperatingPoint


def finite_difference(
    coordinates: tuple[float, ...], values: tuple[float, ...]
) -> tuple[float, ...] | None:
    """Local derivative on a strictly monotonic coordinate, or None if undefined.

    Two points give only one secant, not a local curve, so at least three are required.
    """
    deltas = tuple(right - left for left, right in pairwise(coordinates))
    if (
        len(coordinates) < 3
        or any(delta == 0 for delta in deltas)
        or not (all(delta > 0 for delta in deltas) or all(delta < 0 for delta in deltas))
    ):
        return None
    derivatives: list[float] = []
    for index in range(len(values)):
        if index == 0:
            left, right = 0, 1
        elif index == len(values) - 1:
            left, right = index - 1, index
        else:
            left, right = index - 1, index + 1
        run = coordinates[right] - coordinates[left]
        derivatives.append((values[right] - values[left]) / run)
    return tuple(derivatives)


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
                "maximum_transconductance": _maximum_transconductance,
                "threshold_voltage": _threshold_voltage,
                "subthreshold_swing": _subthreshold_swing,
                "on_off_ratio": _on_off_ratio,
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

    @staticmethod
    def resistance(
        voltage: Dataset,
        current: Dataset,
        axes: Mapping[str, ScientificAxis],
    ) -> Dataset:
        """Return pointwise static resistance while preserving undefined zero-current points."""

        voltage_axis = _require_rank_one(voltage, axes)
        current_axis = _require_rank_one(current, axes)
        if voltage.unit != "V":
            raise ValueError("resistance requires a canonical voltage dataset in V")
        if current.unit not in {"A", "A/m^2"}:
            raise ValueError("resistance requires a canonical current dataset in A or A/m^2")
        if voltage.axes != current.axes or voltage.shape != current.shape:
            raise ValueError("resistance requires voltage and current on identical axes")
        if voltage_axis != current_axis or voltage_axis.kind is not AxisKind.BIAS:
            raise ValueError("resistance requires a canonical bias axis")

        voltage_validity = voltage.validity or (True,) * len(voltage.values)
        current_validity = current.validity or (True,) * len(current.values)
        values: list[float] = []
        validity: list[bool] = []
        for potential, flow, potential_valid, flow_valid in zip(
            voltage.values,
            current.values,
            voltage_validity,
            current_validity,
            strict=True,
        ):
            valid = potential_valid and flow_valid and flow != 0.0
            values.append(potential / flow if valid else 0.0)
            validity.append(valid)
        return Dataset(
            id=f"resistance__{current.id}",
            label=f"Static resistance from {current.label}",
            unit="ohm" if current.unit == "A" else "ohm*m^2",
            axes=voltage.axes,
            shape=voltage.shape,
            centering=current.centering,
            values=tuple(values),
            validity=tuple(validity),
            source=f"derived:ratio:{voltage.id}/{current.id}",
            metadata={
                "zero_current_policy": "invalid",
                "definition": "pointwise_voltage_over_current",
            },
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


def _transfer_curve(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> tuple[ScientificAxis, tuple[float, ...], tuple[float, ...]]:
    """Magnitude of a current against a monotonic sweep, with its local slope."""
    axis = _require_rank_one(dataset, axes)
    magnitude = tuple(abs(value) for value in dataset.values)
    slope = finite_difference(tuple(axis.values), magnitude)
    if slope is None:
        raise ValueError("a transfer-curve metric needs a monotonic sweep of at least 3 points")
    return axis, magnitude, slope


def _maximum_transconductance(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    axis, _, slope = _transfer_curve(dataset, axes)
    index = max(range(len(slope)), key=lambda item: abs(slope[item]))
    return ScalarDerivation(
        "maximum_transconductance",
        abs(slope[index]),
        f"{dataset.unit}/{axis.unit}",
        dataset.id,
        coordinate=axis.values[index],
        coordinate_unit=axis.unit,
    )


def _threshold_voltage(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    """Linear extrapolation at the point of maximum transconductance, to zero current.

    The drain-bias correction (subtracting half the drain voltage) is not applied, so the
    value is the extrapolated gate voltage of that curve at its own drain bias.
    """
    axis, magnitude, slope = _transfer_curve(dataset, axes)
    index = max(range(len(slope)), key=lambda item: abs(slope[item]))
    if slope[index] <= 0 or magnitude[index] <= 0:
        raise ValueError("no rising current to extrapolate a threshold from")
    return ScalarDerivation(
        "threshold_voltage",
        axis.values[index] - magnitude[index] / slope[index],
        axis.unit,
        dataset.id,
        coordinate=axis.values[index],
        coordinate_unit=axis.unit,
    )


def _subthreshold_swing(
    dataset: Dataset, axes: Mapping[str, ScientificAxis]
) -> ScalarDerivation:
    """Steepest sweep per decade of current among points below a tenth of the maximum."""
    axis, magnitude, _ = _transfer_curve(dataset, axes)
    ceiling = 0.1 * max(magnitude)
    best = None
    for index in range(len(magnitude) - 1):
        low, high = magnitude[index], magnitude[index + 1]
        if min(low, high) <= 0 or max(low, high) > ceiling or low == high:
            continue
        decades = abs(math.log10(high) - math.log10(low))
        swing = abs(axis.values[index + 1] - axis.values[index]) / decades
        if best is None or swing < best[0]:
            best = (swing, index)
    if best is None:
        raise ValueError("fewer than two subthreshold points are resolved")
    swing, index = best
    return ScalarDerivation(
        "subthreshold_swing",
        swing * 1000.0,
        "mV/dec",
        dataset.id,
        coordinate=0.5 * (axis.values[index] + axis.values[index + 1]),
        coordinate_unit=axis.unit,
    )


def _on_off_ratio(dataset: Dataset, axes: Mapping[str, ScientificAxis]) -> ScalarDerivation:
    _require_rank_one(dataset, axes)
    magnitude = [abs(value) for value in dataset.values if value != 0]
    if len(magnitude) < 2:
        raise ValueError("on/off ratio needs a non-zero off current")
    return ScalarDerivation("on_off_ratio", max(magnitude) / min(magnitude), "1", dataset.id)


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
