"""Simulator-neutral one-dimensional spatial profile contracts."""

from __future__ import annotations

from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tcad_agent.domain.units import QuantityValue


class _DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ProfileSpecies(StrEnum):
    DONOR = "donor"
    ACCEPTOR = "acceptor"


def _concentration(value: QuantityValue) -> QuantityValue:
    value.require("1 / m**3", "inverse-volume concentration")
    if value.to("1 / m**3") < 0:
        raise ValueError("concentration must be nonnegative")
    return value


def _length(value: QuantityValue) -> QuantityValue:
    return value.require("m", "length")


def _charge_density(value: QuantityValue) -> QuantityValue:
    return value.require("C / m**3", "charge per volume")


class ConstantProfile(_DomainModel):
    kind: Literal["constant"]
    region: str
    species: ProfileSpecies
    value: QuantityValue

    _validate_value = field_validator("value")(_concentration)


class FixedChargeProfile(_DomainModel):
    kind: Literal["fixed_charge"]
    region: str
    density: QuantityValue

    _validate_density = field_validator("density")(_charge_density)


class LinearProfile(_DomainModel):
    kind: Literal["linear"]
    region: str
    species: ProfileSpecies
    start_value: QuantityValue
    end_value: QuantityValue

    _validate_values = field_validator("start_value", "end_value")(_concentration)


class GaussianProfile(_DomainModel):
    kind: Literal["gaussian"]
    region: str
    species: ProfileSpecies
    peak: QuantityValue
    center: QuantityValue
    standard_deviation: QuantityValue

    _validate_peak = field_validator("peak")(_concentration)
    _validate_lengths = field_validator("center", "standard_deviation")(_length)

    @model_validator(mode="after")
    def require_positive_width(self) -> Self:
        if self.standard_deviation.to("m") <= 0:
            raise ValueError("Gaussian standard deviation must be positive")
        return self


class ErrorFunctionProfile(_DomainModel):
    kind: Literal["error_function"]
    region: str
    species: ProfileSpecies
    surface_value: QuantityValue
    junction_position: QuantityValue
    characteristic_length: QuantityValue
    orientation: Literal["increasing_x", "decreasing_x"]

    _validate_surface = field_validator("surface_value")(_concentration)
    _validate_lengths = field_validator(
        "junction_position", "characteristic_length"
    )(_length)

    @model_validator(mode="after")
    def require_positive_length(self) -> Self:
        if self.characteristic_length.to("m") <= 0:
            raise ValueError("error-function characteristic length must be positive")
        return self


class TabulatedProfile(_DomainModel):
    kind: Literal["tabulated"]
    region: str
    species: ProfileSpecies
    positions: tuple[QuantityValue, ...] = Field(min_length=2, max_length=10000)
    values: tuple[QuantityValue, ...] = Field(min_length=2, max_length=10000)
    interpolation: Literal["linear", "nearest"] = "linear"

    _validate_positions = field_validator("positions")(
        lambda values: tuple(_length(value) for value in values)
    )
    _validate_values = field_validator("values")(
        lambda values: tuple(_concentration(value) for value in values)
    )

    @model_validator(mode="after")
    def validate_points(self) -> Self:
        if len(self.positions) != len(self.values):
            raise ValueError("tabulated positions and values must have equal length")
        coordinates = [position.to("m") for position in self.positions]
        if any(right <= left for left, right in pairwise(coordinates)):
            raise ValueError("tabulated positions must be strictly increasing")
        return self


class PiecewiseConstantProfile(_DomainModel):
    kind: Literal["piecewise_constant"]
    region: str
    species: ProfileSpecies
    boundaries: tuple[QuantityValue, ...] = Field(min_length=2, max_length=10001)
    values: tuple[QuantityValue, ...] = Field(min_length=1, max_length=10000)

    _validate_boundaries = field_validator("boundaries")(
        lambda values: tuple(_length(value) for value in values)
    )
    _validate_values = field_validator("values")(
        lambda values: tuple(_concentration(value) for value in values)
    )

    @model_validator(mode="after")
    def validate_intervals(self) -> Self:
        if len(self.boundaries) != len(self.values) + 1:
            raise ValueError("piecewise-constant profile requires one value per interval")
        coordinates = [boundary.to("m") for boundary in self.boundaries]
        if any(right <= left for left, right in pairwise(coordinates)):
            raise ValueError("piecewise-constant boundaries must be strictly increasing")
        return self


Profile1D = Annotated[
    ConstantProfile
    | FixedChargeProfile
    | LinearProfile
    | GaussianProfile
    | ErrorFunctionProfile
    | TabulatedProfile
    | PiecewiseConstantProfile,
    Field(discriminator="kind"),
]


def _temperature(value: QuantityValue) -> QuantityValue:
    value.require("K", "temperature")
    if value.to("K") <= 0:
        raise ValueError("temperature must be positive")
    return value


class ConstantTemperatureProfile(_DomainModel):
    kind: Literal["constant"]
    region: str
    value: QuantityValue

    _validate_value = field_validator("value")(_temperature)


class LinearTemperatureProfile(_DomainModel):
    kind: Literal["linear"]
    region: str
    start_value: QuantityValue
    end_value: QuantityValue

    _validate_values = field_validator("start_value", "end_value")(_temperature)


class TabulatedTemperatureProfile(_DomainModel):
    kind: Literal["tabulated"]
    region: str
    positions: tuple[QuantityValue, ...] = Field(min_length=2, max_length=10000)
    values: tuple[QuantityValue, ...] = Field(min_length=2, max_length=10000)
    interpolation: Literal["linear"] = "linear"

    _validate_positions = field_validator("positions")(
        lambda values: tuple(_length(value) for value in values)
    )
    _validate_values = field_validator("values")(
        lambda values: tuple(_temperature(value) for value in values)
    )

    @model_validator(mode="after")
    def validate_points(self) -> Self:
        if len(self.positions) != len(self.values):
            raise ValueError("temperature positions and values must have equal length")
        coordinates = [position.to("m") for position in self.positions]
        if any(right <= left for left, right in pairwise(coordinates)):
            raise ValueError("temperature positions must be strictly increasing")
        return self


TemperatureProfile1D = Annotated[
    ConstantTemperatureProfile
    | LinearTemperatureProfile
    | TabulatedTemperatureProfile,
    Field(discriminator="kind"),
]
