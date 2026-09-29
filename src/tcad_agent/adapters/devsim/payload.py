"""Validated, non-executable data transferred to the DEVSIM runtime."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _PayloadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class RegionPayload(_PayloadModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    material: Literal["silicon", "silicon_dioxide"]
    x0_cm: float
    x1_cm: float
    mesh_spacing_cm: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_extent(self) -> Self:
        if self.x1_cm <= self.x0_cm:
            raise ValueError("region extent must be positive")
        return self


class InterfacePayload(_PayloadModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    left_region: str
    right_region: str
    fixed_charge_cm2: float | None = None


class _ProfilePayload(_PayloadModel):
    region: str
    species: Literal["donor", "acceptor"]


class ConstantProfilePayload(_ProfilePayload):
    kind: Literal["constant"]
    value_cm3: float = Field(ge=0)


class LinearProfilePayload(_ProfilePayload):
    kind: Literal["linear"]
    start_value_cm3: float = Field(ge=0)
    end_value_cm3: float = Field(ge=0)


class GaussianProfilePayload(_ProfilePayload):
    kind: Literal["gaussian"]
    peak_cm3: float = Field(ge=0)
    center_cm: float
    standard_deviation_cm: float = Field(gt=0)


class ErrorFunctionProfilePayload(_ProfilePayload):
    kind: Literal["error_function"]
    surface_value_cm3: float = Field(ge=0)
    junction_position_cm: float
    characteristic_length_cm: float = Field(gt=0)
    orientation: Literal["increasing_x", "decreasing_x"]


class TabulatedProfilePayload(_ProfilePayload):
    kind: Literal["tabulated"]
    positions_cm: tuple[float, ...] = Field(min_length=2, max_length=10000)
    values_cm3: tuple[float, ...] = Field(min_length=2, max_length=10000)
    interpolation: Literal["linear", "nearest"] = "linear"

    @model_validator(mode="after")
    def validate_table(self) -> Self:
        if len(self.positions_cm) != len(self.values_cm3):
            raise ValueError("tabulated profile coordinates and values must match")
        if any(
            right <= left
            for left, right in zip(
                self.positions_cm, self.positions_cm[1:], strict=False
            )
        ):
            raise ValueError("tabulated profile coordinates must increase")
        return self


ProfilePayload = Annotated[
    ConstantProfilePayload
    | LinearProfilePayload
    | GaussianProfilePayload
    | ErrorFunctionProfilePayload
    | TabulatedProfilePayload,
    Field(discriminator="kind"),
]


class ContactPayload(_PayloadModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    location: Literal["x_min", "x_max"]
    kind: Literal["ohmic", "ideal_gate", "metal_work_function"]
    work_function_ev: float | None = None

    @model_validator(mode="after")
    def validate_work_function(self) -> Self:
        if self.kind == "metal_work_function" and self.work_function_ev is None:
            raise ValueError("metal work-function contact requires a work function")
        return self


class PhysicsPayload(_PayloadModel):
    equations: tuple[
        Literal["poisson", "electron_continuity", "hole_continuity"], ...
    ]
    models: tuple[
        Literal["boltzmann", "constant_mobility", "srh"], ...
    ] = ()
    temperature_k: float = Field(gt=0)


class EquilibriumPayload(_PayloadModel):
    kind: Literal["equilibrium"]


class DCPayload(_PayloadModel):
    kind: Literal["dc", "dc_points"]
    contact: str
    biases_v: tuple[float, ...] = Field(min_length=1, max_length=10000)
    strategy: Literal["fixed", "adaptive"] = "fixed"
    minimum_step_v: float | None = Field(default=None, gt=0)
    maximum_retries: int = Field(default=6, ge=0, le=32)


class ACPayload(_PayloadModel):
    kind: Literal["ac", "frequency"]
    contact: str
    frequencies_hz: tuple[float, ...] = Field(min_length=1, max_length=10000)
    amplitude_v: float = Field(gt=0)


class TransientPayload(_PayloadModel):
    kind: Literal["transient"]
    start_s: float
    stop_s: float
    initial_step_s: float = Field(gt=0)
    maximum_step_s: float = Field(gt=0)
    maximum_steps: int = Field(ge=1, le=10000)


class ParameterPayload(_PayloadModel):
    kind: Literal["temperature", "parameter"]
    parameter_path: str
    values_si: tuple[float, ...] = Field(min_length=1, max_length=10000)
    unit: str


StudyPayload = Annotated[
    EquilibriumPayload | DCPayload | ACPayload | TransientPayload | ParameterPayload,
    Field(discriminator="kind"),
]


class DevsimPayload(_PayloadModel):
    schema_version: Literal["2.0"] = "2.0"
    experiment_name: str = Field(min_length=1, max_length=500)
    regions: tuple[RegionPayload, ...] = Field(min_length=1, max_length=32)
    interfaces: tuple[InterfacePayload, ...] = Field(default=(), max_length=31)
    profiles: tuple[ProfilePayload, ...] = Field(default=(), max_length=256)
    contacts: tuple[ContactPayload, ...] = Field(min_length=1, max_length=2)
    physics: PhysicsPayload
    study: StudyPayload
    observables: tuple[str, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        regions = {region.id for region in self.regions}
        if any(profile.region not in regions for profile in self.profiles):
            raise ValueError("profile references an unknown region")
        contacts = {contact.id for contact in self.contacts}
        study_contact = getattr(self.study, "contact", None)
        if study_contact is not None and study_contact not in contacts:
            raise ValueError("study references an unknown contact")
        return self
