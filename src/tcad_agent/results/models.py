"""Canonical result schema consumed by validation and reporting."""

from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from tcad_agent.domain.models import StrictModel
from tcad_agent.results.datasets import Dataset, ScientificAxis


class BiasPoint(StrictModel):
    bias_v: float
    converged: bool
    terminal_currents_a_per_m2: dict[str, float]


class FieldSeries(StrictModel):
    positions_m: tuple[float, ...]
    values: tuple[float, ...]
    unit: str

    @model_validator(mode="after")
    def require_matching_lengths(self) -> Self:
        if len(self.positions_m) != len(self.values):
            raise ValueError("field positions and values must have equal length")
        return self


class OperatingPoint(StrictModel):
    index: int = Field(ge=0)
    state: Literal["converged", "failed", "skipped"]
    coordinates: dict[str, float] = Field(default_factory=dict)
    terminal_currents_a_per_m2: dict[str, float] = Field(default_factory=dict)
    terminal_charges_c_per_m2: dict[str, float] = Field(default_factory=dict)
    attempts: int = Field(default=1, ge=0)
    message: str | None = None


class CanonicalResult(StrictModel):
    schema_version: Literal["1.0", "2.0"] = "2.0"
    backend: Literal["devsim", "sentaurus"]
    simulator_version: str | None = None
    status: Literal["completed", "execution_failed", "timed_out", "malformed_result"]
    terminals: tuple[str, ...] = ()
    bias_points: tuple[BiasPoint, ...] = ()
    fields: dict[str, FieldSeries] = Field(default_factory=dict)
    axes: dict[str, ScientificAxis] = Field(default_factory=dict)
    datasets: dict[str, Dataset] = Field(default_factory=dict)
    operating_points: tuple[OperatingPoint, ...] = ()
    native_result_path: Path | None = None
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("datasets"):
            return value
        fields = value.get("fields")
        if not isinstance(fields, dict) or not fields:
            return value
        migrated = dict(value)
        axes: dict[str, dict[str, object]] = {}
        datasets: dict[str, dict[str, object]] = {}
        for name, raw_field in fields.items():
            if isinstance(raw_field, FieldSeries):
                positions = raw_field.positions_m
                values = raw_field.values
                unit = raw_field.unit
            elif isinstance(raw_field, dict):
                positions = tuple(raw_field.get("positions_m", ()))
                values = tuple(raw_field.get("values", ()))
                unit = str(raw_field.get("unit", "1"))
            else:
                continue
            axis_id = f"position__{name}"
            axes[axis_id] = {
                "id": axis_id,
                "kind": "position",
                "label": "Position",
                "unit": "m",
                "values": positions,
            }
            datasets[name] = {
                "id": name,
                "label": name.replace("_", " ").title(),
                "unit": unit,
                "axes": (axis_id,),
                "shape": (len(values),),
                "centering": "node",
                "values": values,
                "source": "legacy-field-migration",
            }
        migrated["axes"] = axes
        migrated["datasets"] = datasets
        return migrated

    @model_validator(mode="after")
    def validate_dataset_axes(self) -> Self:
        for key, axis in self.axes.items():
            if key != axis.id:
                raise ValueError("axis dictionary key must match axis id")
        for key, dataset in self.datasets.items():
            if key != dataset.id:
                raise ValueError("dataset dictionary key must match dataset id")
            unknown = set(dataset.axes) - set(self.axes)
            if unknown:
                raise ValueError(f"dataset references unknown axes: {sorted(unknown)}")
            for axis_id, size in zip(dataset.axes, dataset.shape, strict=True):
                if len(self.axes[axis_id].values) != size:
                    raise ValueError("dataset shape does not match referenced axis lengths")
        return self
