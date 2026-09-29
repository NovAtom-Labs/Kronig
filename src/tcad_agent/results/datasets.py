"""Axis-aware canonical scientific dataset contracts."""

from __future__ import annotations

import math
from enum import StrEnum
from functools import reduce
from operator import mul
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class AxisKind(StrEnum):
    POSITION = "position"
    BIAS = "bias"
    FREQUENCY = "frequency"
    TIME = "time"
    TEMPERATURE = "temperature"
    PARAMETER = "parameter"
    INDEX = "index"


class DatasetCentering(StrEnum):
    SCALAR = "scalar"
    NODE = "node"
    EDGE = "edge"
    CONTACT = "contact"
    OPERATING_POINT = "operating_point"


class ScientificAxis(_ResultModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-z][a-z0-9_.-]*$")
    kind: AxisKind
    label: str = Field(min_length=1, max_length=240)
    unit: str = Field(min_length=1, max_length=100)
    values: tuple[float, ...] = Field(min_length=1, max_length=2_000_000)

    @field_validator("values")
    @classmethod
    def require_finite_values(cls, values: tuple[float, ...]) -> tuple[float, ...]:
        if not all(math.isfinite(value) for value in values):
            raise ValueError("axis values must be finite")
        return values


class Dataset(_ResultModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-z][a-z0-9_.-]*$")
    label: str = Field(min_length=1, max_length=240)
    unit: str = Field(min_length=1, max_length=100)
    axes: tuple[str, ...] = Field(default=(), max_length=4)
    shape: tuple[int, ...] = Field(default=(), max_length=4)
    centering: DatasetCentering = DatasetCentering.NODE
    values: tuple[float, ...] = Field(min_length=1, max_length=4_000_000)
    imaginary_values: tuple[float, ...] | None = Field(
        default=None, min_length=1, max_length=4_000_000
    )
    source: str = Field(default="simulator", min_length=1, max_length=240)

    @field_validator("shape")
    @classmethod
    def require_positive_shape(cls, shape: tuple[int, ...]) -> tuple[int, ...]:
        if any(size <= 0 for size in shape):
            raise ValueError("dataset shape dimensions must be positive")
        return shape

    @model_validator(mode="after")
    def validate_storage(self) -> Self:
        if len(self.axes) != len(self.shape):
            raise ValueError("dataset axes and shape must have equal rank")
        expected = reduce(mul, self.shape, 1)
        if expected != len(self.values):
            raise ValueError("dataset shape does not match the value count")
        if self.imaginary_values is not None and len(self.imaginary_values) != expected:
            raise ValueError("imaginary values must match the dataset shape")
        if not all(math.isfinite(value) for value in self.values):
            raise ValueError("dataset real values must be finite")
        if self.imaginary_values is not None and not all(
            math.isfinite(value) for value in self.imaginary_values
        ):
            raise ValueError("dataset imaginary values must be finite")
        if not self.axes and self.centering is not DatasetCentering.SCALAR:
            raise ValueError("rank-zero datasets must use scalar centering")
        return self
