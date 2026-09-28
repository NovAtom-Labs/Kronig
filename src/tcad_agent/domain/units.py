"""Canonical parsing and conversion for physical quantities."""

import math
from collections.abc import Mapping
from typing import Any, Self

import pint
from pydantic import ConfigDict, model_validator
from pydantic.main import BaseModel

from tcad_agent.domain.errors import UnitError

UNIT_REGISTRY = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)


class QuantityValue(BaseModel):
    """An immutable quantity stored in SI base units."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    magnitude_si: float
    si_unit: str
    dimensionality: str

    @model_validator(mode="before")
    @classmethod
    def parse_quantity(cls, value: Any) -> Any:
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return value
        if not isinstance(value, str) or not value.strip():
            raise UnitError("physical quantities require an explicit value and unit")
        try:
            quantity = UNIT_REGISTRY.Quantity(value).to_base_units()
        except (pint.DimensionalityError, pint.UndefinedUnitError, ValueError) as exc:
            raise UnitError(f"invalid physical quantity: {value!r}") from exc
        return {
            "magnitude_si": float(f"{float(quantity.magnitude):.15g}"),
            "si_unit": str(quantity.units),
            "dimensionality": str(quantity.dimensionality),
        }

    @model_validator(mode="after")
    def validate_canonical_quantity(self) -> Self:
        if not math.isfinite(self.magnitude_si):
            raise UnitError("physical quantity magnitude must be finite")
        try:
            quantity = UNIT_REGISTRY.Quantity(self.magnitude_si, self.si_unit)
            declared_dimensionality = UNIT_REGISTRY.get_dimensionality(self.dimensionality)
        except (pint.UndefinedUnitError, ValueError) as exc:
            raise UnitError(f"invalid canonical SI unit: {self.si_unit!r}") from exc
        if quantity.dimensionality != declared_dimensionality:
            raise UnitError("canonical quantity dimensionality does not match its unit")
        return self

    def is_compatible_with(self, unit: str) -> bool:
        quantity = UNIT_REGISTRY.Quantity(self.magnitude_si, self.si_unit)
        return quantity.is_compatible_with(unit)

    def require(self, unit: str, dimension_name: str) -> Self:
        if not self.is_compatible_with(unit):
            raise UnitError(f"quantity must have {dimension_name} dimensions")
        return self

    def to(self, unit: str) -> float:
        try:
            converted = UNIT_REGISTRY.Quantity(self.magnitude_si, self.si_unit).to(unit)
        except pint.DimensionalityError as exc:
            raise UnitError(f"quantity is not compatible with {unit}") from exc
        return float(converted.magnitude)
