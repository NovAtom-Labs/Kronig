"""Unit-safe normalization helpers for reviewed DEVSIM native fields."""

from __future__ import annotations

from typing import Any

_UNIT_CONVERSIONS: dict[str, tuple[float, str]] = {
    "cm^-3": (1e6, "m^-3"),
    "V/cm": (1e2, "V/m"),
    "A/cm^2": (1e4, "A/m^2"),
    "C/cm^3": (1e6, "C/m^3"),
    "C/cm^2": (1e4, "C/m^2"),
    "cm^-3/s": (1e6, "m^-3/s"),
    "cm^2/V/s": (1e-4, "m^2/V/s"),
}


def normalize_native_field(
    field: dict[str, Any],
) -> tuple[tuple[float, ...], tuple[float, ...], str]:
    scale, unit = _UNIT_CONVERSIONS.get(field["unit"], (1.0, str(field["unit"])))
    positions = tuple(float(value) * 1e-2 for value in field["positions_cm"])
    values = tuple(float(value) * scale for value in field["values"])
    if len(positions) != len(values):
        raise ValueError("native field coordinate and value lengths differ")
    return positions, values, unit
