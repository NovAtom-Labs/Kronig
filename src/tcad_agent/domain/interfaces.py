"""Explicit material-boundary contracts for portable one-dimensional stacks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tcad_agent.domain.units import QuantityValue


class Interface1D(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    left_region: str = Field(min_length=1)
    right_region: str = Field(min_length=1)
    fixed_charge_density: QuantityValue | None = None
    mesh_spacing: QuantityValue | None = None

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
