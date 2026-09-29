"""Explicit material-boundary contracts for portable one-dimensional stacks."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tcad_agent.domain.units import QuantityValue


class Interface1D(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    left_region: str = Field(min_length=1)
    right_region: str = Field(min_length=1)
    fixed_charge_density: QuantityValue | None = None
    mesh_spacing: QuantityValue | None = None
    surface_electron_velocity: QuantityValue | None = None
    surface_hole_velocity: QuantityValue | None = None
    trap_density: QuantityValue | None = None
    trap_energy: QuantityValue | None = None
    trap_type: Literal["acceptor", "donor"] | None = None

    @field_validator("fixed_charge_density")
    @classmethod
    def require_sheet_density(
        cls, value: QuantityValue | None
    ) -> QuantityValue | None:
        if value is not None:
            value.require("1 / m**2", "inverse-area sheet density")
        return value

    @field_validator("mesh_spacing")
    @classmethod
    def require_positive_mesh_spacing(
        cls, value: QuantityValue | None
    ) -> QuantityValue | None:
        if value is not None:
            value.require("m", "length")
            if value.to("m") <= 0:
                raise ValueError("interface mesh spacing must be positive")
        return value

    @field_validator("surface_electron_velocity", "surface_hole_velocity")
    @classmethod
    def require_positive_surface_velocity(
        cls, value: QuantityValue | None
    ) -> QuantityValue | None:
        if value is not None:
            value.require("m/s", "surface recombination velocity")
            if value.to("m/s") <= 0:
                raise ValueError("surface recombination velocity must be positive")
        return value

    @field_validator("trap_density")
    @classmethod
    def require_positive_trap_density(
        cls, value: QuantityValue | None
    ) -> QuantityValue | None:
        if value is not None:
            value.require("1/m^2", "inverse-area trap density")
            if value.to("m^-2") <= 0:
                raise ValueError("interface trap density must be positive")
        return value

    @field_validator("trap_energy")
    @classmethod
    def require_trap_energy(
        cls, value: QuantityValue | None
    ) -> QuantityValue | None:
        if value is not None:
            value.require("eV", "trap energy")
        return value

    @model_validator(mode="after")
    def require_complete_surface_models(self) -> Self:
        velocities = (self.surface_electron_velocity, self.surface_hole_velocity)
        if (velocities[0] is None) != (velocities[1] is None):
            raise ValueError(
                "surface SRH requires both electron and hole capture velocities"
            )
        trap_values = (self.trap_density, self.trap_energy, self.trap_type)
        if any(value is not None for value in trap_values) and not all(
            value is not None for value in trap_values
        ):
            raise ValueError(
                "interface trap requires trap density, energy, and type"
            )
        return self
