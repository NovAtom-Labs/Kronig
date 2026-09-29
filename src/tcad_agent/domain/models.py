"""Pydantic contracts for simulator-neutral TCAD experiments."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tcad_agent.domain.interfaces import Interface1D
from tcad_agent.domain.profiles import ConstantProfile, Profile1D, ProfileSpecies
from tcad_agent.domain.studies import DCStudy, EquilibriumStudy, Study1D
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
    "Observable",
    "PhysicsSelection",
    "ProfileSpecies",
    "Region1D",
    "StrictModel",
]


class StrictModel(BaseModel):
    """Immutable model that rejects unrecognized researcher intent."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class ContactLocation(StrEnum):
    X_MIN = "x_min"
    X_MAX = "x_max"


class ContactKind(StrEnum):
    OHMIC = "ohmic"
    IDEAL_GATE = "ideal_gate"
    METAL_WORK_FUNCTION = "metal_work_function"


class Equation(StrEnum):
    POISSON = "poisson"
    ELECTRON_CONTINUITY = "electron_continuity"
    HOLE_CONTINUITY = "hole_continuity"


class Observable(StrEnum):
    TERMINAL_CURRENT = "terminal_current"
    TERMINAL_CHARGE = "terminal_charge"
    POTENTIAL = "potential"
    ELECTRIC_FIELD = "electric_field"
    ELECTRON_DENSITY = "electron_density"
    HOLE_DENSITY = "hole_density"
    CHARGE_DENSITY = "charge_density"
    CONDUCTION_BAND = "conduction_band"
    VALENCE_BAND = "valence_band"
    FERMI_LEVEL = "fermi_level"
    ELECTRON_CURRENT_DENSITY = "electron_current_density"
    HOLE_CURRENT_DENSITY = "hole_current_density"
    ELECTRON_MOBILITY = "electron_mobility"
    HOLE_MOBILITY = "hole_mobility"
    RECOMBINATION_RATE = "recombination_rate"


class Region1D(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    material: str = Field(min_length=1)
    x0: QuantityValue
    x1: QuantityValue
    mesh_spacing: QuantityValue | None = None

    @field_validator("x0", "x1", "mesh_spacing")
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
        return self


class Contact(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    location: ContactLocation
    kind: ContactKind
    work_function: QuantityValue | None = None

    @field_validator("work_function")
    @classmethod
    def require_energy(cls, value: QuantityValue | None) -> QuantityValue | None:
        if value is not None:
            value.require("eV", "energy")
        return value

    @model_validator(mode="after")
    def require_kind_specific_fields(self) -> Self:
        if self.kind is ContactKind.METAL_WORK_FUNCTION and self.work_function is None:
            raise ValueError("metal work-function contact requires work_function")
        if self.kind is ContactKind.OHMIC and self.work_function is not None:
            raise ValueError("ohmic contact cannot define work_function")
        return self


class PhysicsSelection(StrictModel):
    equations: tuple[Equation, ...]
    models: tuple[str, ...] = ()
    temperature: QuantityValue = Field(
        default_factory=lambda: QuantityValue.model_validate("300 K")
    )

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
        return self


class ExperimentSpec(StrictModel):
    schema_version: Literal["1.0"]
    name: str = Field(min_length=1)
    dimension: Literal[1]
    regions: tuple[Region1D, ...]
    interfaces: tuple[Interface1D, ...] = ()
    profiles: tuple[Profile1D, ...]
    contacts: tuple[Contact, ...]
    physics: PhysicsSelection
    study: Study1D
    observables: tuple[Observable, ...]
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_composition(self) -> Self:
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
            (interface.left_region, interface.right_region)
            for interface in self.interfaces
        }
        all_adjacent = {
            (left.id, right.id)
            for left, right in zip(self.regions, self.regions[1:], strict=False)
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
        return self

    def normalized(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)
