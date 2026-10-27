"""Pydantic contracts for simulator-neutral TCAD experiments."""

from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tcad_agent.domain import geometry2d
from tcad_agent.domain.interfaces import Interface1D
from tcad_agent.domain.presentation import normalize_display_units
from tcad_agent.domain.profiles import (
    BoxProfile,
    ConstantProfile,
    PiecewiseConstantProfile,
    PiecewiseConstantTemperatureProfile,
    Profile1D,
    ProfileSpecies,
    TabulatedProfile,
    TabulatedTemperatureProfile,
    TemperatureProfile1D,
)
from tcad_agent.domain.studies import (
    DCPointsStudy,
    DCStudy,
    EquilibriumStudy,
    Study1D,
    expand_study_points,
)
from tcad_agent.domain.units import QuantityValue

__all__ = [
    "ConstantProfile",
    "Contact",
    "ContactKind",
    "ContactLocation",
    "DCStudy",
    "Equation",
    "EquilibriumStudy",
    "ExperimentSpec",
    "MeshAnchor1D",
    "Observable",
    "PhysicsParameters",
    "PhysicsSelection",
    "ProfileCut",
    "ProfileSpecies",
    "Region1D",
    "Region2D",
    "SignConvention",
    "SolverControls",
    "StrictModel",
]


class StrictModel(BaseModel):
    """Immutable model that rejects unrecognized researcher intent."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ContactLocation(StrEnum):
    X_MIN = "x_min"
    X_MAX = "x_max"
    # Lateral sides, used only by two-dimensional structures.
    Y_MIN = "y_min"
    Y_MAX = "y_max"


class ContactKind(StrEnum):
    OHMIC = "ohmic"
    IDEAL_GATE = "ideal_gate"
    METAL_WORK_FUNCTION = "metal_work_function"
    INSULATING = "insulating"


class Equation(StrEnum):
    POISSON = "poisson"
    ELECTRON_CONTINUITY = "electron_continuity"
    HOLE_CONTINUITY = "hole_continuity"


class Observable(StrEnum):
    TERMINAL_CURRENT = "terminal_current"
    TERMINAL_CURRENT_DENSITY = "terminal_current_density"
    ABSOLUTE_TERMINAL_CURRENT = "absolute_terminal_current"
    TERMINAL_CHARGE = "terminal_charge"
    POTENTIAL = "potential"
    ELECTRIC_FIELD = "electric_field"
    ELECTRON_DENSITY = "electron_density"
    HOLE_DENSITY = "hole_density"
    CHARGE_DENSITY = "charge_density"
    CONDUCTION_BAND = "conduction_band"
    VALENCE_BAND = "valence_band"
    FERMI_LEVEL = "fermi_level"
    INTRINSIC_ENERGY = "intrinsic_energy"
    ELECTRON_AFFINITY = "electron_affinity"
    BAND_GAP = "band_gap"
    BAND_GAP_NARROWING = "band_gap_narrowing"
    EFFECTIVE_INTRINSIC_CARRIER_CONCENTRATION = "effective_intrinsic_carrier_concentration"
    ELECTRON_QUASI_FERMI_LEVEL = "electron_quasi_fermi_level"
    HOLE_QUASI_FERMI_LEVEL = "hole_quasi_fermi_level"
    ELECTRON_CURRENT_DENSITY = "electron_current_density"
    HOLE_CURRENT_DENSITY = "hole_current_density"
    ELECTRON_DRIFT_CURRENT_DENSITY = "electron_drift_current_density"
    ELECTRON_DIFFUSION_CURRENT_DENSITY = "electron_diffusion_current_density"
    HOLE_DRIFT_CURRENT_DENSITY = "hole_drift_current_density"
    HOLE_DIFFUSION_CURRENT_DENSITY = "hole_diffusion_current_density"
    CURRENT_DECOMPOSITION_RESIDUAL = "current_decomposition_residual"
    ELECTRON_MOBILITY = "electron_mobility"
    HOLE_MOBILITY = "hole_mobility"
    RECOMBINATION_RATE = "recombination_rate"
    SRH_RECOMBINATION_RATE = "srh_recombination_rate"
    AUGER_RECOMBINATION_RATE = "auger_recombination_rate"
    TOTAL_RECOMBINATION_RATE = "total_recombination_rate"
    ELECTRON_GENERATION_RATE = "electron_generation_rate"
    HOLE_GENERATION_RATE = "hole_generation_rate"
    NET_DOPING = "net_doping"
    DONOR_CONCENTRATION = "donor_concentration"
    ACCEPTOR_CONCENTRATION = "acceptor_concentration"
    ELECTROSTATIC_FLUX = "electrostatic_flux"
    TOTAL_CURRENT_DENSITY = "total_current_density"
    TERMINAL_ELECTRON_CURRENT = "terminal_electron_current"
    TERMINAL_HOLE_CURRENT = "terminal_hole_current"
    INTERFACE_CHARGE_DENSITY = "interface_charge_density"
    SURFACE_RECOMBINATION_RATE = "surface_recombination_rate"
    INTERFACE_TRAP_OCCUPANCY = "interface_trap_occupancy"
    FIXED_CHARGE_DENSITY = "fixed_charge_density"
    LATTICE_TEMPERATURE = "lattice_temperature"


class MeshAnchor1D(StrictModel):
    position: QuantityValue
    spacing: QuantityValue

    @field_validator("position", "spacing")
    @classmethod
    def require_length(cls, value: QuantityValue) -> QuantityValue:
        return value.require("m", "length")

    @model_validator(mode="after")
    def require_positive_spacing(self) -> Self:
        if self.spacing.to("m") <= 0:
            raise ValueError("mesh anchor spacing must be positive")
        return self


class Region1D(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    material: str = Field(min_length=1)
    x0: QuantityValue
    x1: QuantityValue
    mesh_spacing: QuantityValue | None = None
    minimum_mesh_spacing: QuantityValue | None = None
    maximum_mesh_spacing: QuantityValue | None = None
    relative_permittivity: float | None = Field(default=None, gt=0)

    @field_validator(
        "x0",
        "x1",
        "mesh_spacing",
        "minimum_mesh_spacing",
        "maximum_mesh_spacing",
    )
    @classmethod
    def require_length(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("m", "length")
        return value

    @model_validator(mode="after")
    def require_positive_extent(self) -> Self:
        if self.x1.to("m") <= self.x0.to("m"):
            raise ValueError("region x1 must be greater than x0")
        if self.mesh_spacing is not None and self.mesh_spacing.to("m") <= 0:
            raise ValueError("mesh spacing must be positive")
        minimum = (
            self.minimum_mesh_spacing.to("m") if self.minimum_mesh_spacing is not None else None
        )
        maximum = (
            self.maximum_mesh_spacing.to("m") if self.maximum_mesh_spacing is not None else None
        )
        if minimum is not None and minimum <= 0:
            raise ValueError("minimum mesh spacing must be positive")
        if maximum is not None and maximum <= 0:
            raise ValueError("maximum mesh spacing must be positive")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum mesh spacing cannot exceed maximum spacing")
        if self.mesh_spacing is not None:
            target = self.mesh_spacing.to("m")
            if minimum is not None and target < minimum:
                raise ValueError("mesh spacing is below the configured minimum")
            if maximum is not None and target > maximum:
                raise ValueError("mesh spacing exceeds the configured maximum")
        if self.material == "generic_dielectric" and self.relative_permittivity is None:
            raise ValueError("generic_dielectric requires relative_permittivity")
        if self.material != "generic_dielectric" and self.relative_permittivity is not None:
            raise ValueError(
                "relative_permittivity is researcher-specified only for generic_dielectric"
            )
        return self


class Region2D(Region1D):
    """A rectangular region of a two-dimensional structure.

    ``x0``/``x1`` are the extent along the stack (depth) axis and ``y0``/``y1`` the lateral
    extent. A one-dimensional stack is the slice of such a structure at fixed ``y``.
    """

    y0: QuantityValue
    y1: QuantityValue

    @field_validator("y0", "y1")
    @classmethod
    def require_lateral_length(cls, value: QuantityValue) -> QuantityValue:
        return value.require("m", "length")

    @model_validator(mode="after")
    def require_positive_lateral_extent(self) -> Self:
        if self.y1.to("m") <= self.y0.to("m"):
            raise ValueError("region y1 must be greater than y0")
        return self


class ProfileCut(StrictModel):
    """A line along the lateral axis at fixed depth ``at`` where profiles are extracted."""

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    at: QuantityValue

    @field_validator("at")
    @classmethod
    def require_depth_length(cls, value: QuantityValue) -> QuantityValue:
        return value.require("m", "length")


class SignConvention(StrictModel):
    """Explicit electrical signs preserved with every approved experiment."""

    electric_field: Literal["negative_potential_gradient"] = "negative_potential_gradient"
    conventional_current: Literal["positive_x"] = "positive_x"
    terminal_current: Literal["positive_into_device"] = "positive_into_device"
    terminal_charge: Literal["outward_displacement_flux"] = "outward_displacement_flux"


class SolverControls(StrictModel):
    """Bounded numerical controls whose defaults are platform reviewed."""

    precision: Literal["backend_default", "standard", "extended"] = "backend_default"
    maximum_iterations: int = Field(default=80, ge=1, le=1000)
    relative_error: float = Field(default=1e-6, gt=0, le=1)
    electrostatic_absolute_error: float = Field(default=1.0, gt=0)
    carrier_absolute_error: float = Field(default=1e10, gt=0)
    transient_initial_relative_error: float = Field(default=1e-8, gt=0, le=1)
    transient_step_relative_error: float = Field(default=1e-4, gt=0, le=1)
    mesh_refinement_level: int = Field(default=0, ge=0, le=12)


class Contact(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    location: ContactLocation
    kind: ContactKind
    # Two-dimensional structures only: the region whose side carries the contact and,
    # optionally, the (start, end) coordinates along that side. Default is the whole side.
    region: str | None = None
    span: tuple[QuantityValue, QuantityValue] | None = None
    work_function: QuantityValue | None = None
    electron_richardson_constant: QuantityValue | None = None
    hole_richardson_constant: QuantityValue | None = None
    voltage_offset: QuantityValue = Field(
        default_factory=lambda: QuantityValue.model_validate("0 V")
    )
    area: QuantityValue | None = None

    @field_validator("work_function")
    @classmethod
    def require_energy(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("eV", "energy")
        return value

    @field_validator("electron_richardson_constant", "hole_richardson_constant")
    @classmethod
    def require_richardson_constant(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("A/cm^2/K^2", "Richardson constant")
            if value.to("A/cm^2/K^2") <= 0:
                raise ValueError("Richardson constant must be positive")
        return value

    @field_validator("voltage_offset")
    @classmethod
    def require_voltage(cls, value: QuantityValue) -> QuantityValue:
        return value.require("V", "voltage")

    @field_validator("span")
    @classmethod
    def require_ordered_span(
        cls, value: tuple[QuantityValue, QuantityValue] | None
    ) -> tuple[QuantityValue, QuantityValue] | None:
        if value is not None:
            for coordinate in value:
                coordinate.require("m", "length")
            if value[1].to("m") <= value[0].to("m"):
                raise ValueError("contact span must end after it starts")
        return value

    @field_validator("area")
    @classmethod
    def require_positive_area(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("m^2", "area")
            if value.to("m^2") <= 0:
                raise ValueError("contact area must be positive")
        return value

    @model_validator(mode="after")
    def require_kind_specific_fields(self) -> Self:
        if self.kind is ContactKind.METAL_WORK_FUNCTION and self.work_function is None:
            raise ValueError("metal work-function contact requires work_function")
        if self.kind is ContactKind.OHMIC and self.work_function is not None:
            raise ValueError("ohmic contact cannot define work_function")
        richardson_values = (
            self.electron_richardson_constant,
            self.hole_richardson_constant,
        )
        if self.kind is not ContactKind.METAL_WORK_FUNCTION and any(
            value is not None for value in richardson_values
        ):
            raise ValueError("Richardson constants require a metal work-function contact")
        if self.kind is ContactKind.INSULATING:
            if self.work_function is not None:
                raise ValueError("insulating boundary cannot define work_function")
            if self.voltage_offset.to("V") != 0:
                raise ValueError("insulating boundary cannot define a voltage offset")
            if self.area is not None:
                raise ValueError("insulating boundary cannot define a contact area")
        return self


class PhysicsParameters(StrictModel):
    """Portable overrides for reviewed physics-model parameters."""

    electron_lifetime: QuantityValue | None = None
    hole_lifetime: QuantityValue | None = None
    auger_electron_coefficient: QuantityValue | None = None
    auger_hole_coefficient: QuantityValue | None = None
    bgn_reference_energy: QuantityValue | None = None
    bgn_reference_density: QuantityValue | None = None

    @field_validator("electron_lifetime", "hole_lifetime")
    @classmethod
    def require_lifetime(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("s", "time")
            if value.to("s") <= 0:
                raise ValueError("carrier lifetime must be positive")
        return value

    @field_validator("auger_electron_coefficient", "auger_hole_coefficient")
    @classmethod
    def require_auger_coefficient(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("cm^6/s", "volume-squared per time")
            if value.to("cm^6/s") < 0:
                raise ValueError("Auger coefficient cannot be negative")
        return value

    @field_validator("bgn_reference_energy")
    @classmethod
    def require_bgn_energy(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("eV", "energy")
            if value.to("eV") <= 0:
                raise ValueError("band-gap-narrowing reference energy must be positive")
        return value

    @field_validator("bgn_reference_density")
    @classmethod
    def require_bgn_density(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("cm^-3", "inverse-volume concentration")
            if value.to("cm^-3") <= 0:
                raise ValueError("band-gap-narrowing reference density must be positive")
        return value


class PhysicsSelection(StrictModel):
    equations: tuple[Equation, ...]
    models: tuple[str, ...] = ()
    parameters: PhysicsParameters = Field(default_factory=PhysicsParameters)
    temperature: QuantityValue = Field(
        default_factory=lambda: QuantityValue.model_validate("300 K")
    )
    temperature_profiles: tuple[TemperatureProfile1D, ...] = ()

    @field_validator("temperature")
    @classmethod
    def require_temperature(cls, value: QuantityValue) -> QuantityValue:
        value.require("K", "temperature")
        if value.to("K") <= 0:
            raise ValueError("temperature must be positive")
        return value

    @model_validator(mode="after")
    def require_poisson_and_unique_equations(self) -> Self:
        if Equation.POISSON not in self.equations:
            raise ValueError("poisson equation is required")
        if len(set(self.equations)) != len(self.equations):
            raise ValueError("physics equations must be unique")
        auger_values = (
            self.parameters.auger_electron_coefficient,
            self.parameters.auger_hole_coefficient,
        )
        if any(value is not None for value in auger_values) and "auger" not in self.models:
            raise ValueError("Auger parameters require the auger model")
        if (auger_values[0] is None) != (auger_values[1] is None):
            raise ValueError("both electron and hole Auger coefficients are required")
        bgn_values = (
            self.parameters.bgn_reference_energy,
            self.parameters.bgn_reference_density,
        )
        if any(value is not None for value in bgn_values) and "slotboom_bgn" not in self.models:
            raise ValueError("band-gap-narrowing parameters require the slotboom_bgn model")
        if (bgn_values[0] is None) != (bgn_values[1] is None):
            raise ValueError("both band-gap-narrowing parameters are required")
        lifetime_values = (
            self.parameters.electron_lifetime,
            self.parameters.hole_lifetime,
        )
        if any(value is not None for value in lifetime_values) and "srh" not in self.models:
            raise ValueError("carrier lifetimes require the srh model")
        profile_regions = [profile.region for profile in self.temperature_profiles]
        if len(profile_regions) != len(set(profile_regions)):
            raise ValueError("temperature profiles must have unique regions")
        return self


class ProfileSampling(StrictModel):
    """Explicit profile display points; all solved evidence is still retained."""

    mode: Literal["explicit", "automatic"] = "explicit"
    bias_values: tuple[QuantityValue, ...] = Field(default=(), max_length=10000)
    labels: tuple[str, ...] = ()
    method: Literal["schedule_quantiles"] | None = None
    sample_count: int | None = Field(default=None, ge=2, le=100)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.mode == "explicit":
            if not self.bias_values or self.method is not None or self.sample_count is not None:
                raise ValueError("explicit sampling requires bias_values and no automatic method")
            if self.labels and len(self.labels) != len(self.bias_values):
                raise ValueError("each profile label must correspond to one explicit voltage")
        elif not self.method or self.sample_count is None:
            raise ValueError("automatic sampling requires an explicit selection method and count")
        elif self.bias_values or self.labels:
            raise ValueError("automatic sampling cannot supply explicit voltages or regime labels")
        return self

    @field_validator("bias_values")
    @classmethod
    def require_voltage(cls, values: tuple[QuantityValue, ...]) -> tuple[QuantityValue, ...]:
        return tuple(value.require("V", "voltage") for value in values)


class ExperimentSpec(StrictModel):
    schema_version: Literal["1.0"]
    name: str = Field(min_length=1)
    dimension: Literal[1, 2]
    regions: tuple[Region1D | Region2D, ...]
    interfaces: tuple[Interface1D, ...] = ()
    profiles: tuple[Profile1D, ...]
    contacts: tuple[Contact, ...]
    physics: PhysicsSelection
    study: Study1D
    profile_sampling: ProfileSampling | None = None
    observables: tuple[Observable, ...]
    mesh_anchors: tuple[MeshAnchor1D, ...] = ()
    # Two-dimensional structures only. Lines along the lateral axis where profiles are
    # extracted, and the device width that turns per-width terminal currents into amperes.
    profile_cuts: tuple[ProfileCut, ...] = ()
    width: QuantityValue | None = None
    sign_convention: SignConvention = Field(default_factory=SignConvention)
    solver: SolverControls = Field(default_factory=SolverControls)
    display_units: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Requested display units by canonical quantity or dataset ID, for example "
            "capacitance: F/cm^2 or electron_density: cm^-3. Canonical evidence remains SI; "
            "density cannot become an absolute quantity without physical area."
        ),
    )
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("display_units")
    @classmethod
    def require_valid_display_units(cls, value: dict[str, str]) -> dict[str, str]:
        for key, unit in value.items():
            if not key.strip() or not unit.strip():
                raise ValueError("Display quantity and unit must not be empty")
            QuantityValue.model_validate(f"1 {unit}")
        return normalize_display_units(value)

    def profile_bias_values_v(self) -> tuple[float, ...]:
        if not self.profile_sampling:
            return ()
        if self.profile_sampling.mode == "explicit":
            return tuple(value.to("V") for value in self.profile_sampling.bias_values)
        schedule = getattr(self.study, "bias_schedule", None) or self.study
        values = tuple(point.to("V") for point in expand_study_points(schedule))
        count = self.profile_sampling.sample_count
        if not count or count > len(values):
            raise ValueError("automatic sample count must not exceed approved bias schedule points")
        indices = tuple(round(index * (len(values) - 1) / (count - 1)) for index in range(count))
        return tuple(values[index] for index in indices)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_observables(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        observables = value.get("observables")
        if not isinstance(observables, (list, tuple)) or "terminal_current" not in {
            str(item) for item in observables
        }:
            return value
        migrated = dict(value)
        migrated["observables"] = tuple(
            "terminal_current_density" if str(item) == "terminal_current" else item
            for item in observables
        )
        metadata = dict(migrated.get("metadata") or {})
        metadata.setdefault(
            "migration.terminal_current",
            "schema 1.0 terminal_current mapped to terminal_current_density",
        )
        migrated["metadata"] = metadata
        return migrated

    @model_validator(mode="after")
    def validate_composition(self) -> Self:
        if self.profile_sampling:
            schedule = getattr(self.study, "bias_schedule", None) or self.study
            if isinstance(schedule, DCStudy | DCPointsStudy):
                biases = [point.to("V") for point in expand_study_points(schedule)]
            elif isinstance(schedule, EquilibriumStudy) or self.study.kind in {"ac", "frequency"}:
                biases = [0.0]
            else:
                raise ValueError("bias profile sampling requires an approved bias schedule")
            if any(
                not any(abs(value - bias) < 1e-10 for bias in biases)
                for value in self.profile_bias_values_v()
            ):
                raise ValueError("profile points must exist in the approved bias schedule")
        if self.dimension == 2:
            self._validate_two_dimensional()
            return self
        self._reject_two_dimensional_fields()
        if not self.regions:
            raise ValueError("at least one region is required")
        region_ids = [region.id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region IDs must be unique")
        for left, right in zip(self.regions, self.regions[1:], strict=False):
            if abs(left.x1.to("m") - right.x0.to("m")) > 1e-15:
                raise ValueError("regions must be ordered and contiguous")
        interface_ids = [interface.id for interface in self.interfaces]
        if len(interface_ids) != len(set(interface_ids)):
            raise ValueError("interface IDs must be unique")
        expected_boundaries = {
            (left.id, right.id)
            for left, right in zip(self.regions, self.regions[1:], strict=False)
            if left.material != right.material
        }
        actual_boundaries = {
            (interface.left_region, interface.right_region) for interface in self.interfaces
        }
        all_adjacent = {
            (left.id, right.id) for left, right in zip(self.regions, self.regions[1:], strict=False)
        }
        invalid_boundaries = actual_boundaries - all_adjacent
        if invalid_boundaries:
            raise ValueError("interfaces must reference adjacent ordered regions")
        missing_boundaries = expected_boundaries - actual_boundaries
        if missing_boundaries:
            raise ValueError("every material boundary requires an interface record")
        unknown_regions = {profile.region for profile in self.profiles} - set(region_ids)
        if unknown_regions:
            raise ValueError(f"profiles reference unknown regions: {sorted(unknown_regions)}")
        regions_by_id = {region.id: region for region in self.regions}
        unknown_temperature_regions = {
            profile.region for profile in self.physics.temperature_profiles
        } - set(region_ids)
        if unknown_temperature_regions:
            raise ValueError(
                "temperature profiles reference unknown regions: "
                f"{sorted(unknown_temperature_regions)}"
            )
        for profile in self.profiles:
            region = regions_by_id[profile.region]
            coordinates: tuple[QuantityValue, ...] = ()
            if isinstance(profile, PiecewiseConstantProfile):
                coordinates = profile.boundaries
            elif isinstance(profile, TabulatedProfile):
                coordinates = profile.positions
            if coordinates and (
                coordinates[0].to("m") < region.x0.to("m") - 1e-15
                or coordinates[-1].to("m") > region.x1.to("m") + 1e-15
            ):
                raise ValueError("profile coordinates must lie inside their region")
        for temperature_profile in self.physics.temperature_profiles:
            region = regions_by_id[temperature_profile.region]
            temperature_coordinates: tuple[QuantityValue, ...] = ()
            if isinstance(temperature_profile, PiecewiseConstantTemperatureProfile):
                temperature_coordinates = temperature_profile.boundaries
            elif isinstance(temperature_profile, TabulatedTemperatureProfile):
                temperature_coordinates = temperature_profile.positions
            if temperature_coordinates and (
                temperature_coordinates[0].to("m") < region.x0.to("m") - 1e-15
                or temperature_coordinates[-1].to("m") > region.x1.to("m") + 1e-15
            ):
                raise ValueError("temperature profile coordinates must lie inside their region")
        contact_ids = [contact.id for contact in self.contacts]
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("contact IDs must be unique")
        locations = [contact.location for contact in self.contacts]
        if len(locations) != len(set(locations)):
            raise ValueError("contact locations must be unique")
        study_contact = getattr(self.study, "contact", None)
        if study_contact is not None and study_contact not in contact_ids:
            raise ValueError("study references an unknown contact")
        if not self.observables:
            raise ValueError("at least one observable is required")
        stack_start = self.regions[0].x0.to("m")
        stack_stop = self.regions[-1].x1.to("m")
        anchor_positions = [anchor.position.to("m") for anchor in self.mesh_anchors]
        if len(anchor_positions) != len(set(anchor_positions)):
            raise ValueError("mesh anchor positions must be unique")
        if any(
            position < stack_start - 1e-15 or position > stack_stop + 1e-15
            for position in anchor_positions
        ):
            raise ValueError("every mesh anchor must lie inside the region stack")
        return self

    def _reject_two_dimensional_fields(self) -> None:
        """A one-dimensional experiment must not carry fields that only 2D can honor."""
        if any(isinstance(region, Region2D) for region in self.regions):
            raise ValueError("regions with a lateral extent require dimension 2")
        if any(isinstance(profile, BoxProfile) for profile in self.profiles):
            raise ValueError("box doping profiles require dimension 2")
        if any(
            contact.region is not None
            or contact.span is not None
            or contact.location in {ContactLocation.Y_MIN, ContactLocation.Y_MAX}
            for contact in self.contacts
        ):
            raise ValueError("contact regions, spans and lateral sides require dimension 2")
        if self.profile_cuts or self.width is not None:
            raise ValueError("profile cuts and device width require dimension 2")

    def _validate_two_dimensional(self) -> None:
        regions = list(self.regions)
        if not regions or not all(isinstance(region, Region2D) for region in regions):
            raise ValueError("a two-dimensional structure needs regions with y0 and y1")
        ids = [region.id for region in regions]
        if len(ids) != len(set(ids)):
            raise ValueError("region IDs must be unique")
        for index, first in enumerate(regions):
            for second in regions[index + 1 :]:
                if geometry2d.overlap(first, second):
                    raise ValueError(f"regions {first.id} and {second.id} overlap")
        if self.interfaces or self.mesh_anchors or self.physics.temperature_profiles:
            raise ValueError(
                "interfaces, mesh anchors and temperature profiles are not defined for "
                "two-dimensional structures"
            )
        by_id = {region.id: region for region in regions}
        for profile in self.profiles:
            region = by_id.get(profile.region)
            if region is None:
                raise ValueError(f"profile references unknown region: {profile.region}")
            if profile.kind not in {"constant", "box"}:
                raise ValueError("two-dimensional structures take constant or box doping only")
            if isinstance(profile, BoxProfile):
                x0, x1, y0, y1 = geometry2d.bounds(region)
                inside = (
                    x0 - 1e-15 <= profile.x0.to("m")
                    and profile.x1.to("m") <= x1 + 1e-15
                    and y0 - 1e-15 <= profile.y0.to("m")
                    and profile.y1.to("m") <= y1 + 1e-15
                )
                if not inside:
                    raise ValueError("a box doping window must lie inside its region")
        contact_ids = [contact.id for contact in self.contacts]
        if len(contact_ids) != len(set(contact_ids)):
            raise ValueError("contact IDs must be unique")
        for contact in self.contacts:
            region = by_id.get(contact.region or "")
            if region is None:
                raise ValueError(f"contact {contact.id} needs a region of this structure")
            lo, hi = (
                (region.y0.to("m"), region.y1.to("m"))
                if contact.location in {ContactLocation.X_MIN, ContactLocation.X_MAX}
                else (region.x0.to("m"), region.x1.to("m"))
            )
            if contact.span is not None and (
                contact.span[0].to("m") < lo - 1e-15 or contact.span[1].to("m") > hi + 1e-15
            ):
                raise ValueError(f"contact {contact.id} span lies outside its region side")
            others = [other for other in regions if other.id != region.id]
            if not geometry2d.segment_is_exposed(contact, region, others):
                raise ValueError(f"contact {contact.id} lies on a boundary shared with a region")
        placements = [(c.region, str(c.location), c.span) for c in self.contacts]
        if len(placements) != len(set(placements)):
            raise ValueError("contact placements must be unique")
        segments = [
            (c.id, *geometry2d.contact_segment(c, by_id[c.region or ""])[:2]) for c in self.contacts
        ]
        for index, (first_id, a0, a1) in enumerate(segments):
            for second_id, b0, b1 in segments[index + 1 :]:
                gap = 1e-12
                if all(
                    min(a0[axis], a1[axis]) <= max(b0[axis], b1[axis]) + gap
                    and min(b0[axis], b1[axis]) <= max(a0[axis], a1[axis]) + gap
                    for axis in (0, 1)
                ):
                    raise ValueError(
                        f"contacts {first_id} and {second_id} touch or overlap; electrodes need "
                        "a gap, so narrow one of them with a span that stops short of the other"
                    )
        study_contact = getattr(self.study, "contact", None)
        if study_contact is not None and study_contact not in contact_ids:
            raise ValueError("study references an unknown contact")
        if not self.observables:
            raise ValueError("at least one observable is required")
        depth_lo = min(region.x0.to("m") for region in regions)
        depth_hi = max(region.x1.to("m") for region in regions)
        cut_ids = [cut.id for cut in self.profile_cuts]
        if len(cut_ids) != len(set(cut_ids)):
            raise ValueError("profile cut IDs must be unique")
        if any(not depth_lo <= cut.at.to("m") <= depth_hi for cut in self.profile_cuts):
            raise ValueError("every profile cut must lie inside the structure")
        if self.width is not None:
            self.width.require("m", "length")
            if self.width.to("m") <= 0:
                raise ValueError("device width must be positive")

    def normalized(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)
