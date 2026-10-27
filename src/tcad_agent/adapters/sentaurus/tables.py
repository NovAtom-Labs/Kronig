"""Versioned exported-table boundary. This is not a binary TDR decoder.

Spatial coordinates and dataset values carry native units; operating-point maps
use the SI units in their field names. No geometry or contact area is inferred.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
from itertools import pairwise, product
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from tcad_agent.domain.models import SignConvention, StrictModel
from tcad_agent.results.datasets import Dataset, DatasetCentering, ScientificAxis
from tcad_agent.results.derive import finite_difference
from tcad_agent.results.models import BiasPoint, CanonicalResult, FieldSeries, OperatingPoint

_MAX_BYTES = 64 * 1024 * 1024
_UNITS = {
    "1": ("1", 1),
    "V": ("V", 1),
    "mV": ("V", 1e-3),
    "m": ("m", 1),
    "cm": ("m", 1e-2),
    "um": ("m", 1e-6),
    "nm": ("m", 1e-9),
    "Hz": ("Hz", 1),
    "kHz": ("Hz", 1e3),
    "MHz": ("Hz", 1e6),
    "s": ("s", 1),
    "ms": ("s", 1e-3),
    "us": ("s", 1e-6),
    "ns": ("s", 1e-9),
    "K": ("K", 1),
    "V/m": ("V/m", 1),
    "V/cm": ("V/m", 1e2),
    "m^-3": ("m^-3", 1),
    "cm^-3": ("m^-3", 1e6),
    "eV": ("eV", 1),
    "A/m^2": ("A/m^2", 1),
    "A/cm^2": ("A/m^2", 1e4),
    "A": ("A", 1),
    "m^2/(V*s)": ("m^2/(V*s)", 1),
    "cm^2/(V*s)": ("m^2/(V*s)", 1e-4),
    "m^-3*s^-1": ("m^-3*s^-1", 1),
    "cm^-3*s^-1": ("m^-3*s^-1", 1e6),
    "C/m^3": ("C/m^3", 1),
    "C/cm^3": ("C/m^3", 1e6),
    "C/m^2": ("C/m^2", 1),
    "C/cm^2": ("C/m^2", 1e4),
    "C": ("C", 1),
    "F/m^2": ("F/m^2", 1),
    "F/cm^2": ("F/m^2", 1e4),
    "F": ("F", 1),
    "S": ("S", 1),
    "S/m^2": ("S/m^2", 1),
    "S/cm^2": ("S/m^2", 1e4),
}
_QUANTITIES = {
    "potential": "V",
    "electric_field": "V/m",
    "charge_density": "C/m^3",
    **dict.fromkeys(
        (
            "electron_density",
            "hole_density",
            "effective_density_conduction",
            "effective_density_valence",
            "donor_concentration",
            "acceptor_concentration",
            "net_doping",
            "effective_intrinsic_carrier_concentration",
        ),
        "m^-3",
    ),
    **dict.fromkeys(
        (
            "conduction_band",
            "valence_band",
            "fermi_level",
            "electron_quasi_fermi_level",
            "hole_quasi_fermi_level",
            "band_gap",
            "band_gap_narrowing",
            "electron_affinity",
        ),
        "eV",
    ),
    **dict.fromkeys(
        (
            "electron_current_density",
            "hole_current_density",
            "total_current_density",
            "terminal_current_density",
        ),
        "A/m^2",
    ),
    "absolute_terminal_current": "A",
    "electron_mobility": "m^2/(V*s)",
    "hole_mobility": "m^2/(V*s)",
    **dict.fromkeys(
        ("recombination_rate", "srh_recombination_rate", "auger_recombination_rate"), "m^-3*s^-1"
    ),
    "terminal_charge_density": "C/m^2",
    "absolute_terminal_charge": "C",
    "capacitance_density": "F/m^2",
    "capacitance": "F",
    "admittance": "S",
    "admittance_density": "S/m^2",
    "lattice_temperature": "K",
}
_AXIS_UNITS = {
    "position": "m",
    "bias": "V",
    "frequency": "Hz",
    "time": "s",
    "temperature": "K",
    "index": "1",
}


def quantity_conversion(quantity: str, unit: str) -> tuple[str, float]:
    if quantity not in _QUANTITIES or unit not in _UNITS:
        raise ValueError(f"unsupported quantity/unit: {quantity}/{unit}")
    canonical, scale = _UNITS[unit]
    if canonical != _QUANTITIES[quantity]:
        raise ValueError(f"unit {unit} is not valid for {quantity}")
    return canonical, scale


class CSVColumn(StrictModel):
    file: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*\.csv$", max_length=160)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    column: str = Field(min_length=1)
    imaginary_column: str | None = None


class ExportDataset(StrictModel):
    id: str
    quantity: str
    label: str
    unit: str
    axes: tuple[str, ...] = Field(max_length=4)
    shape: tuple[int, ...] = Field(max_length=4)
    centering: DatasetCentering
    values: tuple[float, ...] | None = Field(default=None, max_length=4_000_000)
    imaginary_values: tuple[float, ...] | None = Field(default=None, max_length=4_000_000)
    validity: tuple[bool, ...] | None = Field(default=None, max_length=4_000_000)
    table: CSVColumn | None = None

    @model_validator(mode="after")
    def check_storage(self):
        if (self.values is None) == (self.table is None):
            raise ValueError("exactly one of values or CSV table is required")
        if self.table is not None and self.imaginary_values is not None:
            raise ValueError("CSV imaginary values must come from the same table")
        if len(self.axes) != len(self.shape) or any(size <= 0 for size in self.shape):
            raise ValueError("dataset shape must have positive dimensions matching its axes")
        quantity_conversion(self.quantity, self.unit)
        return self


class ExportProvenance(StrictModel):
    compiler_version: str = Field(min_length=1)
    experiment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mesh_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TableExport(StrictModel):
    schema_version: Literal["2.0"]
    simulator_version: str = Field(min_length=1)
    status: Literal["completed"]
    provenance: ExportProvenance
    terminals: tuple[str, ...] = Field(max_length=64)
    # Physics models the exporter declares were selected for this run (from the submitted
    # experiment); validation uses them, for example to test Boltzmann applicability.
    physics_models: tuple[str, ...] = Field(default=(), max_length=32)
    # Parameters the experiment left unspecified, so the simulator's built-in values applied.
    native_defaults: tuple[str, ...] = Field(default=(), max_length=32)
    sign_convention: SignConvention
    axes: dict[str, ScientificAxis] = Field(max_length=64)
    datasets: dict[str, ExportDataset] = Field(min_length=1, max_length=256)
    operating_points: tuple[OperatingPoint, ...] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def check_points(self):
        if not self.simulator_version.strip():
            raise ValueError("simulator_version must not be blank")
        if len(set(self.terminals)) != len(self.terminals) or any(
            not name.strip() for name in self.terminals
        ):
            raise ValueError("terminal names must be nonempty and unique")
        if tuple(point.index for point in self.operating_points) != tuple(
            range(len(self.operating_points))
        ):
            raise ValueError("operating point indices must be unique and contiguous")
        for point in self.operating_points:
            maps = (
                point.terminal_currents_a_per_m2,
                point.terminal_electron_currents_a_per_m2,
                point.terminal_hole_currents_a_per_m2,
                point.terminal_charges_c_per_m2,
            )
            if any(set(mapping) - set(self.terminals) for mapping in maps):
                raise ValueError("operating point references an unknown terminal")
            if not all(
                math.isfinite(value)
                for mapping in (*maps, point.coordinates)
                for value in mapping.values()
            ):
                raise ValueError("operating point values must be finite SI values")
        return self


def _single_point_fields(axes, datasets, export) -> dict[str, FieldSeries]:
    """Plain profiles for a result with exactly one operating point (for example equilibrium).

    A family of profiles over several operating points is never collapsed into one profile;
    only a profile that already is unique is exposed in the legacy single-profile form.
    """
    if len(export.operating_points) != 1:
        return {}
    fields: dict[str, FieldSeries] = {}
    for key, dataset in datasets.items():
        positions = [name for name in dataset.axes if axes[name].kind == "position"]
        others = [name for name in dataset.axes if name not in positions]
        if (
            len(positions) != 1
            or dataset.centering is not DatasetCentering.NODE
            or any(axes[name].kind != "bias" or len(axes[name].values) != 1 for name in others)
            or len(dataset.values) != len(axes[positions[0]].values)
            or (dataset.validity is not None and not all(dataset.validity))
        ):
            continue
        fields[key] = FieldSeries(
            positions_m=tuple(axes[positions[0]].values),
            values=tuple(dataset.values),
            unit=dataset.unit,
        )
    return fields


def _terminal_curves(axes, bias_axes, export) -> dict[str, Dataset]:
    """Per-terminal curves over the bias axis, named exactly as the DEVSIM results name them.

    They are derived only from operating points, so every table export gets the same
    I-V, charge and capacitance views. A terminal missing from any point is skipped, never
    padded with zeros.
    """
    if len(bias_axes) != 1:
        return {}
    axis_id = bias_axes[0]
    ordered = []
    for value in axes[axis_id].values:
        match = [
            point
            for point in export.operating_points
            if axis_id in point.coordinates
            and math.isclose(point.coordinates[axis_id], value, rel_tol=1e-12, abs_tol=1e-15)
        ]
        if len(match) != 1:
            return {}
        ordered.append(match[0])
    coordinates = tuple(axes[axis_id].values)
    validity = tuple(point.state == "converged" for point in ordered)

    def curve(name, label, unit, values, source="native"):
        return Dataset(
            id=name,
            label=label,
            unit=unit,
            axes=(axis_id,),
            shape=(len(coordinates),),
            centering=DatasetCentering.OPERATING_POINT,
            values=values,
            validity=validity,
            source=source,
        )

    curves: dict[str, Dataset] = {}
    for terminal in export.terminals:
        series = {
            "terminal_current": ("Terminal current", "A/m^2", "terminal_currents_a_per_m2"),
            "terminal_electron_current": (
                "Terminal electron current",
                "A/m^2",
                "terminal_electron_currents_a_per_m2",
            ),
            "terminal_hole_current": (
                "Terminal hole current",
                "A/m^2",
                "terminal_hole_currents_a_per_m2",
            ),
            "terminal_charge": ("Terminal charge", "C/m^2", "terminal_charges_c_per_m2"),
        }
        for prefix, (label, unit, field) in series.items():
            if not all(terminal in getattr(point, field) for point in ordered):
                continue
            values = tuple(getattr(point, field)[terminal] for point in ordered)
            curves[f"{prefix}__{terminal}"] = curve(
                f"{prefix}__{terminal}", f"{label} at {terminal}", unit, values
            )
            if prefix == "terminal_current":
                curves[f"terminal_current_density__{terminal}"] = curve(
                    f"terminal_current_density__{terminal}",
                    f"Terminal current density at {terminal}",
                    unit,
                    values,
                    "derived:terminal-current-density-alias",
                )
            if prefix == "terminal_charge" and all(validity):
                slope = finite_difference(coordinates, values)
                if slope is not None:
                    curves[f"capacitance__{terminal}"] = curve(
                        f"capacitance__{terminal}",
                        f"Quasi-static capacitance at {terminal}",
                        "F/m^2",
                        slope,
                        f"derived:dQdV:terminal_charge__{terminal}",
                    )
    return curves


def _csv_values(root: Path, column: CSVColumn, source_hashes: dict[str, str]):
    path = root / column.file
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError("CSV file symlinks and escaping paths are forbidden")
    if path.stat().st_size > _MAX_BYTES:
        raise ValueError("CSV exceeds file size limit")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != column.sha256:
        raise ValueError("CSV source hash mismatch")
    source_hashes[column.file] = column.sha256
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
    names = reader.fieldnames or []
    if not names or len(names) != len(set(names)):
        raise ValueError("CSV column names must be nonempty and unique")
    if column.column not in names or (
        column.imaginary_column and column.imaginary_column not in names
    ):
        raise ValueError("CSV value column is missing")
    values, imaginary = [], []
    for row in reader:
        if None in row or any(value is None or not value.strip() for value in row.values()):
            raise ValueError("CSV row does not match its columns")
        values.append(float(row[column.column]))
        if column.imaginary_column:
            imaginary.append(float(row[column.imaginary_column]))
        if len(values) > 4_000_000:
            raise ValueError("CSV exceeds row count limit")
    return tuple(values), tuple(imaginary) if column.imaginary_column else None


def normalize_tables(payload: dict, path: Path, export_sha256: str) -> CanonicalResult:
    export = TableExport.model_validate(payload)
    if sum(math.prod(item.shape) for item in export.datasets.values()) > 4_000_000:
        raise ValueError("export exceeds aggregate dataset value budget")
    csv_names = {item.table.file for item in export.datasets.values() if item.table}
    if sum((path.parent / name).stat().st_size for name in csv_names) > _MAX_BYTES:
        raise ValueError("export exceeds total CSV size limit")
    axes = {}
    for key, axis in export.axes.items():
        if axis.unit not in _UNITS:
            raise ValueError(f"unsupported axis unit: {axis.unit}")
        unit, scale = _UNITS[axis.unit]
        if axis.kind != "parameter" and unit != _AXIS_UNITS[axis.kind]:
            raise ValueError(f"axis unit does not match {axis.kind}")
        values = tuple(value * scale for value in axis.values)
        if axis.kind in {"position", "time"} and any(b <= a for a, b in pairwise(values)):
            raise ValueError(f"{axis.kind} coordinates must be strictly increasing")
        if axis.kind in {"frequency", "temperature"} and any(value <= 0 for value in values):
            raise ValueError(f"{axis.kind} coordinates must be positive")
        axes[key] = ScientificAxis.model_validate(
            {**axis.model_dump(), "values": values, "unit": unit}
        )
    bias_axes = [name for name, axis in axes.items() if axis.kind == "bias"]
    if len(bias_axes) > 1:
        raise ValueError("multiple bias coordinate axes need separate export records")
    for point in export.operating_points:
        for name, value in point.coordinates.items():
            if name not in axes or axes[name].kind == "position":
                raise ValueError("operating point references an unknown study coordinate")
            matches = [
                index
                for index, candidate in enumerate(axes[name].values)
                if math.isclose(value, candidate, rel_tol=1e-12, abs_tol=1e-15)
            ]
            if len(matches) != 1:
                raise ValueError("operating point coordinate is absent or ambiguous on its axis")
    datasets, source_hashes = {}, {}
    for key, item in export.datasets.items():
        if set(item.axes) - set(axes):
            raise ValueError("dataset references an unknown coordinate axis")
        unit, scale = quantity_conversion(item.quantity, item.unit)
        values, imaginary = item.values, item.imaginary_values
        if item.table is not None:
            values, imaginary = _csv_values(path.parent.resolve(), item.table, source_hashes)
        assert values is not None
        dataset = Dataset(
            id=item.id,
            label=item.label,
            unit=unit,
            axes=item.axes,
            shape=item.shape,
            centering=item.centering,
            values=tuple(value * scale for value in values),
            imaginary_values=tuple(value * scale for value in imaginary)
            if imaginary is not None
            else None,
            validity=item.validity,
            source="sentaurus-exported-table",
            metadata={
                "quantity": item.quantity,
                **({"file": item.table.file, "sha256": item.table.sha256} if item.table else {}),
            },
        )
        study_axes = tuple(name for name in dataset.axes if axes[name].kind != "position")
        if (
            not study_axes
            and "position" in {str(axes[name].kind) for name in dataset.axes}
            and len(export.operating_points) > 1
        ):
            raise ValueError(
                "spatial datasets need an explicit study coordinate when several points exist"
            )
        for coordinates in (
            product(*(axes[name].values for name in study_axes)) if study_axes else ()
        ):
            matches = [
                point
                for point in export.operating_points
                if all(
                    name in point.coordinates
                    and math.isclose(value, point.coordinates[name], rel_tol=1e-12, abs_tol=1e-15)
                    for name, value in zip(study_axes, coordinates, strict=True)
                )
            ]
            if len(matches) != 1:
                raise ValueError("dataset coordinates do not identify exactly one operating point")
        # Failed solves are evidence, not valid scientific samples. Preserve any
        # exporter-supplied invalid mask and additionally mask matching failures.
        failures = [point for point in export.operating_points if point.state != "converged"]
        if failures:
            valid = list(dataset.validity or (True,) * len(dataset.values))
            for point in failures:
                if study_axes and not set(study_axes).issubset(point.coordinates):
                    continue
                shared = set(point.coordinates) & set(dataset.axes)
                for index in range(len(valid)):
                    offset = index
                    coordinates = {}
                    for axis_id, size in reversed(
                        tuple(zip(dataset.axes, dataset.shape, strict=True))
                    ):
                        coordinates[axis_id] = axes[axis_id].values[offset % size]
                        offset //= size
                    if not shared or all(
                        math.isclose(
                            coordinates[name], point.coordinates[name], rel_tol=1e-12, abs_tol=1e-15
                        )
                        for name in shared
                    ):
                        valid[index] = False
            dataset = dataset.model_copy(update={"validity": tuple(valid)})
        datasets[key] = dataset
    # Exporter-supplied datasets win over derived terminal curves of the same name.
    datasets = {**_terminal_curves(axes, bias_axes, export), **datasets}
    return CanonicalResult(
        backend="sentaurus",
        simulator_version=export.simulator_version,
        status=export.status,
        terminals=export.terminals,
        axes=axes,
        datasets=datasets,
        fields=_single_point_fields(axes, datasets, export),
        operating_points=export.operating_points,
        bias_points=tuple(
            BiasPoint(
                bias_v=point.coordinates[bias_axes[0]],
                converged=point.state == "converged",
                terminal_currents_a_per_m2=point.terminal_currents_a_per_m2,
                terminal_electron_currents_a_per_m2=point.terminal_electron_currents_a_per_m2,
                terminal_hole_currents_a_per_m2=point.terminal_hole_currents_a_per_m2,
            )
            for point in export.operating_points
            if bias_axes and bias_axes[0] in point.coordinates
        ),
        native_result_path=path,
        sign_convention=export.sign_convention.model_dump(),
        metadata={
            "native_export_sha256": export_sha256,
            "source_hashes": source_hashes,
            "declared_provenance": export.provenance.model_dump(),
            "physics_models": list(export.physics_models),
            "native_defaults": list(export.native_defaults),
            "qualification": "export_interoperability_only_not_native_physics_qualification",
        },
    )
