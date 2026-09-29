"""Validated, non-executable data transferred to the DEVSIM runtime."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _PayloadModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class RegionPayload(_PayloadModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    material: Literal["silicon", "silicon_dioxide", "generic_dielectric"]
    x0_cm: float
    x1_cm: float
    mesh_spacing_cm: float = Field(gt=0)
    relative_permittivity: float | None = Field(default=None, gt=0)
    minimum_mesh_spacing_cm: float | None = Field(default=None, gt=0)
    maximum_mesh_spacing_cm: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_extent(self) -> Self:
        if self.x1_cm <= self.x0_cm:
            raise ValueError("region extent must be positive")
        if self.material == "generic_dielectric" and self.relative_permittivity is None:
            raise ValueError("generic_dielectric requires relative_permittivity")
        return self


class InterfacePayload(_PayloadModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    left_region: str
    right_region: str
    fixed_charge_cm2: float | None = None
    mesh_spacing_cm: float | None = Field(default=None, gt=0)


class MeshAnchorPayload(_PayloadModel):
    position_cm: float
    spacing_cm: float = Field(gt=0)
    source: str = Field(default="user", min_length=1, max_length=160)


class _ProfilePayload(_PayloadModel):
    region: str
    species: Literal["donor", "acceptor"]


class ConstantProfilePayload(_ProfilePayload):
    kind: Literal["constant"]
    value_cm3: float = Field(ge=0)


class FixedChargeProfilePayload(_PayloadModel):
    kind: Literal["fixed_charge"]
    region: str
    density_c_cm3: float


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


class PiecewiseConstantProfilePayload(_ProfilePayload):
    kind: Literal["piecewise_constant"]
    boundaries_cm: tuple[float, ...] = Field(min_length=2, max_length=10001)
    values_cm3: tuple[float, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def validate_intervals(self) -> Self:
        if len(self.boundaries_cm) != len(self.values_cm3) + 1:
            raise ValueError("piecewise profile requires one value per interval")
        if any(
            right <= left
            for left, right in zip(
                self.boundaries_cm, self.boundaries_cm[1:], strict=False
            )
        ):
            raise ValueError("piecewise boundaries must increase")
        return self


ProfilePayload = Annotated[
    ConstantProfilePayload
    | FixedChargeProfilePayload
    | LinearProfilePayload
    | GaussianProfilePayload
    | ErrorFunctionProfilePayload
    | TabulatedProfilePayload
    | PiecewiseConstantProfilePayload,
    Field(discriminator="kind"),
]


class ContactPayload(_PayloadModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    backend_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    location: Literal["x_min", "x_max"]
    kind: Literal["ohmic", "ideal_gate", "metal_work_function", "insulating"]
    work_function_ev: float | None = None
    voltage_offset_v: float = 0.0
    area_m2: float | None = Field(default=None, gt=0)

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
        Literal[
            "boltzmann",
            "constant_mobility",
            "high_field_saturation",
            "klaassen_mobility",
            "srh",
            "auger",
            "slotboom_bgn",
        ],
        ...,
    ] = ()
    temperature_k: float = Field(gt=0)
    parameter_set_id: str = Field(
        default="novatom.silicon.baseline.2026-09-29.v1",
        min_length=1,
        max_length=160,
    )
    parameter_sources: dict[str, dict[str, str]] = Field(default_factory=dict)
    electron_affinity_ev: float = Field(default=4.05, gt=0)
    band_gap_ev: float = Field(default=1.124, gt=0)
    effective_density_conduction_cm3: float = Field(default=2.8e19, gt=0)
    effective_density_valence_cm3: float = Field(default=1.04e19, gt=0)
    electron_lifetime_s: float = Field(default=1.0e-8, gt=0)
    hole_lifetime_s: float = Field(default=1.0e-8, gt=0)
    auger_electron_cm6_s: float = Field(default=2.8e-31, ge=0)
    auger_hole_cm6_s: float = Field(default=9.9e-32, ge=0)
    bgn_reference_energy_ev: float = Field(default=9.0e-3, gt=0)
    bgn_reference_density_cm3: float = Field(default=1.0e17, gt=0)


class SignConventionPayload(_PayloadModel):
    electric_field: Literal["negative_potential_gradient"]
    conventional_current: Literal["positive_x"]
    terminal_current: Literal["positive_into_device"]
    terminal_charge: Literal["outward_displacement_flux"]


class SolverPayload(_PayloadModel):
    maximum_iterations: int = Field(default=80, ge=1, le=1000)
    relative_error: float = Field(default=1e-6, gt=0, le=1)
    electrostatic_absolute_error: float = Field(default=1.0, gt=0)
    carrier_absolute_error: float = Field(default=1e10, gt=0)
    transient_initial_relative_error: float = Field(default=1e-8, gt=0, le=1)
    transient_step_relative_error: float = Field(default=1e-4, gt=0, le=1)


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
    contact: str
    waveform: Literal["step", "ramp", "pulse"]
    initial_voltage_v: float
    final_voltage_v: float
    start_s: float
    stop_s: float
    initial_step_s: float = Field(gt=0)
    minimum_step_s: float = Field(gt=0)
    maximum_step_s: float = Field(gt=0)
    maximum_steps: int = Field(ge=1, le=10000)
    maximum_retries: int = Field(ge=0, le=32)
    pulse_delay_s: float | None = Field(default=None, ge=0)
    rise_time_s: float | None = Field(default=None, ge=0)
    pulse_width_s: float | None = Field(default=None, gt=0)
    fall_time_s: float | None = Field(default=None, ge=0)


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
    mesh_anchors: tuple[MeshAnchorPayload, ...] = Field(default=(), max_length=10000)
    profiles: tuple[ProfilePayload, ...] = Field(default=(), max_length=256)
    contacts: tuple[ContactPayload, ...] = Field(min_length=1, max_length=2)
    physics: PhysicsPayload
    sign_convention: SignConventionPayload = Field(
        default_factory=lambda: SignConventionPayload(
            electric_field="negative_potential_gradient",
            conventional_current="positive_x",
            terminal_current="positive_into_device",
            terminal_charge="outward_displacement_flux",
        )
    )
    solver: SolverPayload = Field(default_factory=SolverPayload)
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
