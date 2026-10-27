"""Strict normalization of allowlisted Sentaurus tabular exports."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from typing import Literal, Self

from pydantic import Field, model_validator

from tcad_agent.adapters.sentaurus.tables import normalize_tables, quantity_conversion
from tcad_agent.domain.models import StrictModel
from tcad_agent.results.models import BiasPoint, CanonicalResult, FieldSeries
from tcad_agent.runners.models import NativeRunResult

_POSITION_SCALE = {"m": 1.0, "cm": 1.0e-2, "um": 1.0e-6, "nm": 1.0e-9}
_VALUE_UNITS = {
    "V": ("V", 1.0),
    "V/m": ("V/m", 1.0),
    "V/cm": ("V/m", 1.0e2),
    "m^-3": ("m^-3", 1.0),
    "cm^-3": ("m^-3", 1.0e6),
    "eV": ("eV", 1.0),
    "A/m^2": ("A/m^2", 1.0),
    "A/cm^2": ("A/m^2", 1.0e4),
    "m^2/(V*s)": ("m^2/(V*s)", 1.0),
    "cm^2/(V*s)": ("m^2/(V*s)", 1.0e-4),
    "m^-3*s^-1": ("m^-3*s^-1", 1.0),
    "cm^-3*s^-1": ("m^-3*s^-1", 1.0e6),
    "C/m^3": ("C/m^3", 1.0),
    "C/cm^3": ("C/m^3", 1.0e6),
}
_ALLOWED_FIELDS = {
    "potential",
    "electric_field",
    "electron_density",
    "hole_density",
    "charge_density",
    "conduction_band",
    "valence_band",
    "fermi_level",
    "electron_current_density",
    "hole_current_density",
    "electron_mobility",
    "hole_mobility",
    "recombination_rate",
    "srh_recombination_rate",
    "auger_recombination_rate",
    "net_doping",
    "donor_concentration",
    "acceptor_concentration",
    "band_gap",
    "band_gap_narrowing",
    "electron_affinity",
    "effective_intrinsic_carrier_concentration",
    "total_current_density",
    "lattice_temperature",
}


class SentaurusNormalizationError(ValueError):
    pass


class NativeField(StrictModel):
    position: tuple[float, ...]
    position_unit: str
    values: tuple[float, ...]
    unit: str

    @model_validator(mode="after")
    def validate_table(self) -> Self:
        if len(self.position) != len(self.values) or not self.position:
            raise ValueError("position and values columns must have the same nonzero length")
        if not all(math.isfinite(value) for value in (*self.position, *self.values)):
            raise ValueError("tabular values must be finite")
        if len(set(self.position)) != len(self.position):
            raise ValueError("position column contains duplicate coordinates")
        if any(
            right <= left for left, right in zip(self.position, self.position[1:], strict=False)
        ):
            raise ValueError("position column must be strictly monotonic")
        if self.position_unit not in _POSITION_SCALE:
            raise ValueError("position unit is not allowlisted")
        if self.unit not in _VALUE_UNITS:
            raise ValueError("field unit is not allowlisted")
        return self


class NativeBiasPoint(StrictModel):
    bias_v: float
    converged: bool
    terminal_current_density: dict[str, float]

    @model_validator(mode="after")
    def require_finite_currents(self) -> Self:
        values = (self.bias_v, *self.terminal_current_density.values())
        if not all(math.isfinite(value) for value in values):
            raise ValueError("bias and current values must be finite")
        return self


class NativeSentaurusExport(StrictModel):
    schema_version: Literal["1.0"]
    simulator_version: str = Field(min_length=1)
    status: Literal["completed"]
    terminals: tuple[str, ...]
    current_density_unit: str
    bias_points: tuple[NativeBiasPoint, ...]
    fields: dict[str, NativeField]

    @model_validator(mode="after")
    def validate_allowlist(self) -> Self:
        unknown = set(self.fields) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"field names are not allowlisted: {sorted(unknown)}")
        if self.current_density_unit not in {"A/m^2", "A/cm^2"}:
            raise ValueError("current density unit is not allowlisted")
        if len(set(self.terminals)) != len(self.terminals) or any(
            not item.strip() for item in self.terminals
        ):
            raise ValueError("terminal names must be nonempty and unique")
        for point in self.bias_points:
            if set(point.terminal_current_density) - set(self.terminals):
                raise ValueError("unknown terminal in bias point")
        for name, field in self.fields.items():
            quantity_conversion(name, field.unit)
        return self


class SentaurusNormalizer:
    def normalize(self, native: NativeRunResult) -> CanonicalResult:
        if native.backend != "sentaurus":
            raise SentaurusNormalizationError("normalizer accepts only Sentaurus results")
        if native.status != "completed":
            return CanonicalResult(
                backend="sentaurus",
                status=native.status,
                native_result_path=native.result_path,
                error=native.error,
            )
        if native.result_path is None:
            raise SentaurusNormalizationError("completed run has no native result")
        try:
            if (
                native.result_path.is_symlink()
                or native.result_path.stat().st_size > 64 * 1024 * 1024
            ):
                raise ValueError("native export must be a bounded regular file, not a symlink")
            raw = native.result_path.read_bytes()
            payload = json.loads(raw)
            if isinstance(payload, dict) and payload.get("schema_version") == "2.0":
                return normalize_tables(
                    payload, native.result_path, hashlib.sha256(raw).hexdigest()
                )
            export = NativeSentaurusExport.model_validate(payload)
        except (OSError, ValueError, UnicodeError, csv.Error) as exc:
            raise SentaurusNormalizationError(f"invalid schema: {exc}") from exc

        current_scale = _VALUE_UNITS[export.current_density_unit][1]
        bias_points = tuple(
            BiasPoint(
                bias_v=point.bias_v,
                converged=point.converged,
                terminal_currents_a_per_m2={
                    terminal: value * current_scale
                    for terminal, value in point.terminal_current_density.items()
                },
            )
            for point in export.bias_points
        )
        fields: dict[str, FieldSeries] = {}
        for name, field in export.fields.items():
            canonical_unit, value_scale = _VALUE_UNITS[field.unit]
            position_scale = _POSITION_SCALE[field.position_unit]
            fields[name] = FieldSeries(
                positions_m=tuple(value * position_scale for value in field.position),
                values=tuple(value * value_scale for value in field.values),
                unit=canonical_unit,
            )
        return CanonicalResult(
            backend="sentaurus",
            simulator_version=export.simulator_version,
            status="completed",
            terminals=export.terminals,
            bias_points=bias_points,
            fields=fields,
            native_result_path=native.result_path,
            metadata={"native_export_sha256": hashlib.sha256(raw).hexdigest()},
        )
