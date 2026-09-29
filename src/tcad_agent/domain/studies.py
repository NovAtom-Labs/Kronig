"""Bounded, simulator-neutral one-dimensional study schedules."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tcad_agent.domain.units import QuantityValue


class _StudyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class EquilibriumStudy(_StudyModel):
    kind: Literal["equilibrium"]


class DCStudy(_StudyModel):
    kind: Literal["dc"]
    contact: str
    start: QuantityValue
    stop: QuantityValue
    step: QuantityValue
    strategy: Literal["fixed", "adaptive"] = "fixed"
    minimum_step: QuantityValue | None = None
    maximum_retries: int = Field(default=6, ge=0, le=32)

    @field_validator("start", "stop", "step", "minimum_step")
    @classmethod
    def require_voltage(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("V", "voltage")
        return value

    @model_validator(mode="after")
    def require_bounded_sweep(self) -> Self:
        span = abs(self.stop.to("V") - self.start.to("V"))
        step = self.step.to("V")
        if step <= 0:
            raise ValueError("DC step must be positive")
        if span / step + 1 > 10_000:
            raise ValueError("DC sweep exceeds 10000 points")
        if self.strategy == "adaptive":
            if self.minimum_step is None:
                raise ValueError("adaptive DC sweep requires minimum_step")
            minimum = self.minimum_step.to("V")
            if minimum <= 0 or minimum > step:
                raise ValueError("minimum_step must be positive and no greater than step")
        elif self.minimum_step is not None:
            raise ValueError("fixed DC sweep cannot define minimum_step")
        return self


class DCPointsStudy(_StudyModel):
    kind: Literal["dc_points"]
    contact: str
    values: tuple[QuantityValue, ...] = Field(min_length=1, max_length=10000)
    strategy: Literal["fixed", "adaptive"] = "fixed"
    minimum_step: QuantityValue | None = None
    maximum_retries: int = Field(default=6, ge=0, le=32)

    @field_validator("values")
    @classmethod
    def require_voltages(
        cls, values: tuple[QuantityValue, ...]
    ) -> tuple[QuantityValue, ...]:
        return tuple(value.require("V", "voltage") for value in values)

    @field_validator("minimum_step")
    @classmethod
    def require_voltage_step(
        cls, value: QuantityValue | None
    ) -> QuantityValue | None:
        return value.require("V", "voltage") if value is not None else None

    @model_validator(mode="after")
    def require_bounded_recovery(self) -> Self:
        if self.strategy == "adaptive":
            if self.minimum_step is None or self.minimum_step.to("V") <= 0:
                raise ValueError("adaptive DC points require a positive minimum_step")
        elif self.minimum_step is not None:
            raise ValueError("fixed DC points cannot define minimum_step")
        return self


class ACStudy(_StudyModel):
    kind: Literal["ac"]
    contact: str
    frequency: QuantityValue
    amplitude: QuantityValue

    @field_validator("frequency")
    @classmethod
    def require_frequency(cls, value: QuantityValue) -> QuantityValue:
        value.require("Hz", "frequency")
        if value.to("Hz") <= 0:
            raise ValueError("frequency must be positive")
        return value

    @field_validator("amplitude")
    @classmethod
    def require_amplitude(cls, value: QuantityValue) -> QuantityValue:
        value.require("V", "voltage")
        if value.to("V") <= 0:
            raise ValueError("AC amplitude must be positive")
        return value


class FrequencyStudy(_StudyModel):
    kind: Literal["frequency"]
    contact: str
    start: QuantityValue
    stop: QuantityValue
    points: int = Field(ge=2, le=10000)
    spacing: Literal["linear", "log"] = "log"
    amplitude: QuantityValue

    @field_validator("start", "stop")
    @classmethod
    def require_frequency(cls, value: QuantityValue) -> QuantityValue:
        return value.require("Hz", "frequency")

    @field_validator("amplitude")
    @classmethod
    def require_amplitude(cls, value: QuantityValue) -> QuantityValue:
        return value.require("V", "voltage")

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        start = self.start.to("Hz")
        stop = self.stop.to("Hz")
        if start <= 0 or stop <= start:
            raise ValueError("frequency range must be positive and increasing")
        if self.amplitude.to("V") <= 0:
            raise ValueError("AC amplitude must be positive")
        return self


class TransientStudy(_StudyModel):
    kind: Literal["transient"]
    contact: str
    waveform: Literal["step", "ramp", "pulse"]
    initial_voltage: QuantityValue
    final_voltage: QuantityValue
    start: QuantityValue
    stop: QuantityValue
    initial_step: QuantityValue
    minimum_step: QuantityValue | None = None
    maximum_step: QuantityValue
    maximum_steps: int = Field(default=10000, ge=1, le=10000)
    maximum_retries: int = Field(default=6, ge=0, le=32)
    pulse_delay: QuantityValue | None = None
    rise_time: QuantityValue | None = None
    pulse_width: QuantityValue | None = None
    fall_time: QuantityValue | None = None

    @field_validator(
        "start",
        "stop",
        "initial_step",
        "minimum_step",
        "maximum_step",
        "pulse_delay",
        "rise_time",
        "pulse_width",
        "fall_time",
    )
    @classmethod
    def require_time(cls, value: QuantityValue | None) -> QuantityValue | None:
        return value.require("s", "time") if value is not None else None

    @field_validator("initial_voltage", "final_voltage")
    @classmethod
    def require_voltage(cls, value: QuantityValue) -> QuantityValue:
        return value.require("V", "voltage")

    @model_validator(mode="after")
    def validate_schedule(self) -> Self:
        if self.stop.to("s") <= self.start.to("s"):
            raise ValueError("transient stop must be greater than start")
        if self.initial_step.to("s") <= 0:
            raise ValueError("transient initial step must be positive")
        if self.maximum_step.to("s") < self.initial_step.to("s"):
            raise ValueError("maximum transient step cannot be smaller than initial step")
        if self.minimum_step is not None:
            if self.minimum_step.to("s") <= 0:
                raise ValueError("minimum transient step must be positive")
            if self.minimum_step.to("s") > self.initial_step.to("s"):
                raise ValueError("minimum transient step cannot exceed initial step")
        pulse_fields = (
            self.pulse_delay,
            self.rise_time,
            self.pulse_width,
            self.fall_time,
        )
        if self.waveform == "pulse":
            names = ("pulse_delay", "rise_time", "pulse_width", "fall_time")
            missing = [
                name
                for name, value in zip(names, pulse_fields, strict=True)
                if value is None
            ]
            if missing:
                raise ValueError(f"pulse waveform requires {', '.join(missing)}")
            delay, rise, width, fall = (value.to("s") for value in pulse_fields if value)
            if delay < 0 or rise < 0 or width <= 0 or fall < 0:
                raise ValueError("pulse timing must be nonnegative and pulse_width positive")
            if delay + rise + width + fall > self.stop.to("s") - self.start.to("s"):
                raise ValueError("pulse timing must fit inside the transient interval")
        elif any(value is not None for value in pulse_fields):
            raise ValueError("pulse timing fields require waveform='pulse'")
        return self


class TemperatureStudy(_StudyModel):
    kind: Literal["temperature"]
    values: tuple[QuantityValue, ...] = Field(min_length=1, max_length=10000)

    @field_validator("values")
    @classmethod
    def validate_temperatures(
        cls, values: tuple[QuantityValue, ...]
    ) -> tuple[QuantityValue, ...]:
        for value in values:
            value.require("K", "temperature")
            if value.to("K") <= 0:
                raise ValueError("temperature must be positive")
        return values


class ParameterStudy(_StudyModel):
    kind: Literal["parameter"]
    parameter_path: str = Field(
        min_length=1, max_length=240, pattern=r"^[a-z][a-z0-9_.-]*$"
    )
    values: tuple[QuantityValue, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def require_compatible_values(self) -> Self:
        dimensionality = self.values[0].dimensionality
        if any(value.dimensionality != dimensionality for value in self.values[1:]):
            raise ValueError("parameter study values must have compatible dimensions")
        return self


Study1D = Annotated[
    EquilibriumStudy
    | DCStudy
    | DCPointsStudy
    | ACStudy
    | FrequencyStudy
    | TransientStudy
    | TemperatureStudy
    | ParameterStudy,
    Field(discriminator="kind"),
]


def expand_study_points(study: Study1D) -> tuple[QuantityValue, ...]:
    if isinstance(study, DCPointsStudy):
        return study.values
    if isinstance(study, DCStudy):
        start = study.start.to("V")
        stop = study.stop.to("V")
        magnitude = study.step.to("V")
        direction = 1.0 if stop >= start else -1.0
        count = math.floor(abs(stop - start) / magnitude + 1e-12) + 1
        values = [start + direction * magnitude * index for index in range(count)]
        if not math.isclose(values[-1], stop, rel_tol=1e-12, abs_tol=1e-15):
            values.append(stop)
        return tuple(QuantityValue.model_validate(f"{value:.15g} V") for value in values)
    if isinstance(study, FrequencyStudy):
        start = study.start.to("Hz")
        stop = study.stop.to("Hz")
        if study.spacing == "linear":
            values = [
                start + (stop - start) * index / (study.points - 1)
                for index in range(study.points)
            ]
        else:
            log_start = math.log10(start)
            log_stop = math.log10(stop)
            values = [
                10 ** (log_start + (log_stop - log_start) * index / (study.points - 1))
                for index in range(study.points)
            ]
        return tuple(QuantityValue.model_validate(f"{value:.15g} Hz") for value in values)
    if isinstance(study, TemperatureStudy | ParameterStudy):
        return study.values
    return ()
