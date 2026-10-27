"""Local conversion of Sentaurus Device TDR output into the strict table export.

Everything here runs on the researcher's workstation from files fetched over SSH, so
the remote host needs nothing beyond Sentaurus itself. The slab built by
``mesh.py`` must stay laterally uniform; any lateral variation fails the export
instead of being averaged away.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from tcad_agent.adapters.sentaurus.runtime import (
    ESCALATION_NOTES,
    ESCALATION_NOTES_2D,
    GENERATED_MESHES,
    MINIMUM_DIGITS,
    SentaurusJobManifest,
)
from tcad_agent.domain import geometry2d
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.studies import expand_study_points

_ELEMENT_VERTICES = {1: 2, 2: 3, 3: 4}
_ELEMENTARY_CHARGE_C = 1.602176634e-19
_UNIT_ALIASES = {
    "V*cm^-1": "V/cm",
    "A*cm^-2": "A/cm^2",
    "cm^2*V^-1*s^-1": "cm^2/(V*s)",
}
# TDR dataset -> (quantity, export unit, scale, vector component)
_FIELDS: dict[str, tuple[str, str, float, int | None]] = {
    "ElectrostaticPotential": ("potential", "V", 1.0, None),
    "eDensity": ("electron_density", "cm^-3", 1.0, None),
    "hDensity": ("hole_density", "cm^-3", 1.0, None),
    "ElectricField": ("electric_field", "V/cm", 1.0, 0),
    "SpaceCharge": ("charge_density", "C/cm^3", _ELEMENTARY_CHARGE_C, None),
    "ConductionBandEnergy": ("conduction_band", "eV", 1.0, None),
    "ValenceBandEnergy": ("valence_band", "eV", 1.0, None),
    "eCurrentDensity": ("electron_current_density", "A/cm^2", 1.0, 0),
    "hCurrentDensity": ("hole_current_density", "A/cm^2", 1.0, 0),
    "eMobility": ("electron_mobility", "cm^2/(V*s)", 1.0, None),
    "hMobility": ("hole_mobility", "cm^2/(V*s)", 1.0, None),
    "TotalRecombination": ("recombination_rate", "cm^-3*s^-1", 1.0, None),
    "srhRecombination": ("srh_recombination_rate", "cm^-3*s^-1", 1.0, None),
    "AugerRecombination": ("auger_recombination_rate", "cm^-3*s^-1", 1.0, None),
    "DopingConcentration": ("net_doping", "cm^-3", 1.0, None),
    "DonorConcentration": ("donor_concentration", "cm^-3", 1.0, None),
    "AcceptorConcentration": ("acceptor_concentration", "cm^-3", 1.0, None),
    "BandGap": ("band_gap", "eV", 1.0, None),
    "BandgapNarrowing": ("band_gap_narrowing", "eV", 1.0, None),
    "ElectronAffinity": ("electron_affinity", "eV", 1.0, None),
    "EffectiveIntrinsicDensity": (
        "effective_intrinsic_carrier_concentration",
        "cm^-3",
        1.0,
        None,
    ),
    "TotalCurrentDensity": ("total_current_density", "A/cm^2", 1.0, 0),
    "LatticeTemperature": ("lattice_temperature", "K", 1.0, None),
    "eEffectiveStateDensity": ("effective_density_conduction", "cm^-3", 1.0, None),
    "hEffectiveStateDensity": ("effective_density_valence", "cm^-3", 1.0, None),
    "eQuasiFermiEnergy": ("electron_quasi_fermi_level", "eV", 1.0, None),
    "hQuasiFermiEnergy": ("hole_quasi_fermi_level", "eV", 1.0, None),
}
_LABELS = {
    "potential": "Electrostatic potential",
    "electron_density": "Electron density",
    "hole_density": "Hole density",
    "electric_field": "Electric field",
    "charge_density": "Space charge density",
    "conduction_band": "Conduction band energy",
    "valence_band": "Valence band energy",
    "electron_current_density": "Electron current density",
    "hole_current_density": "Hole current density",
    "electron_mobility": "Electron mobility",
    "hole_mobility": "Hole mobility",
    "recombination_rate": "Total recombination rate",
    "effective_density_conduction": "Conduction-band effective density of states",
    "effective_density_valence": "Valence-band effective density of states",
    "electron_quasi_fermi_level": "Electron quasi-Fermi level",
    "hole_quasi_fermi_level": "Hole quasi-Fermi level",
    "srh_recombination_rate": "Shockley-Read-Hall recombination rate",
    "auger_recombination_rate": "Auger recombination rate",
    "net_doping": "Net doping (donors minus acceptors)",
    "donor_concentration": "Donor concentration",
    "acceptor_concentration": "Acceptor concentration",
    "band_gap": "Band gap",
    "band_gap_narrowing": "Band-gap narrowing",
    "electron_affinity": "Electron affinity",
    "effective_intrinsic_carrier_concentration": "Effective intrinsic carrier concentration",
    "total_current_density": "Total current density",
    "lattice_temperature": "Lattice temperature",
}
# Net, donor and acceptor doping each have their own native plot keyword; whatever a deck writes
# beyond what was asked for is dropped rather than exported unrequested.
_ONLY_WHEN_REQUESTED = frozenset({"net_doping", "donor_concentration", "acceptor_concentration"})
_LATERAL_RTOL = 1e-4


class NativeExportError(ValueError):
    """Raised when native output cannot be converted without guessing."""


_VOLTAGE_TOLERANCE_V = 1e-5


def _unreached_voltage(
    spec: ExperimentSpec, bias: float, terminals: dict[str, dict[str, float]]
) -> str | None:
    """Describe a point whose native contact voltages differ from what was requested.

    A solver ramp that stops short of its target does not stop the simulation: the next command
    runs and the plot of the unfinished ramp is still written. The voltage each contact really
    had is stored with the native data, so a point is accepted only when it matches the request;
    otherwise it is reported as failed instead of carrying the requested label on other data.
    """
    driven = getattr(spec.study, "contact", None)
    problems = []
    for contact in spec.contacts:
        wanted = contact.voltage_offset.to("V") + (bias if contact.id == driven else 0.0)
        actual = terminals[contact.id]["ContactExternalVoltage"]
        if abs(actual - wanted) > _VOLTAGE_TOLERANCE_V * max(1.0, abs(wanted)):
            problems.append(f"{contact.id} reached {actual:.6g} V instead of {wanted:.6g} V")
    if problems:
        return "the solver did not reach the requested bias: " + "; ".join(problems)
    return None


def native_defaults(spec: ExperimentSpec) -> list[str]:
    """Name every parameter family the experiment did not set, so it ran on Sentaurus defaults."""
    models = set(spec.physics.models)
    parameters = spec.physics.parameters
    notes = ["silicon material constants (permittivity, band gap, densities of states)"]
    if "constant_mobility" in models:
        notes.append("constant mobility values")
    if "srh" in models and parameters.electron_lifetime is None:
        notes.append("SRH lifetimes")
    if "auger" in models:
        notes.append("Auger coefficients")
    if {"band_gap_narrowing", "slotboom_bgn"} & models:
        notes.append("band-gap-narrowing parameters")
    requested = round(-math.log10(spec.solver.relative_error))
    if requested < MINIMUM_DIGITS:
        notes.append(
            f"solver precision tightened from {requested} to {MINIMUM_DIGITS} digits so "
            "terminal currents add up"
        )
    return notes


def escalation_notes(log_text: str, *, two_dimensional: bool = False) -> list[str]:
    """Say so when the results came from a stronger numerical strategy than the default.

    The run script logs the level that produced them. A level above 0 means the default solver
    gave up on a bias ramp first; the results are as valid as any other, but the method differs.
    """
    found = re.findall(r"KRONIG numerics level (\d+) stalled:([ \d]*)", log_text)
    if not found or int(found[-1][0]) == 0:
        return []
    level = int(found[-1][0])
    notes = ESCALATION_NOTES_2D if two_dimensional else ESCALATION_NOTES
    note = notes[min(level, len(notes)) - 1]
    return [
        "numerical strategy escalated: the default solver gave up on a bias ramp, so the results "
        f"come from a rerun with the {note} (level {level}; levels{found[-1][1]} stalled)"
    ]


def simulator_version(log_text: str) -> str:
    match = re.search(r"Sentaurus Device\s*\*+\s*\n\*+\s*Version\s+([A-Za-z0-9_.\-]+)", log_text)
    if match is None:
        match = re.search(r"Version\s+([A-Z]-\d{4}\.\d{2}(?:-SP\d+)?)", log_text)
    if match is None:
        raise NativeExportError("the Sentaurus Device release was not found in its log")
    return match.group(1)


def _text(value: object) -> str:
    return value.decode() if isinstance(value, bytes | np.bytes_) else str(value)


def _region_vertices(group) -> np.ndarray:
    raw = group["elements_0"][()]
    vertices: list[int] = []
    cursor = 0
    while cursor < len(raw):
        kind = int(raw[cursor])
        if kind not in _ELEMENT_VERTICES:
            raise NativeExportError(f"unsupported TDR element type {kind}")
        count = _ELEMENT_VERTICES[kind]
        vertices.extend(int(item) for item in raw[cursor + 1 : cursor + 1 + count])
        cursor += 1 + count
    return np.unique(np.asarray(vertices, dtype=np.int64))


_INTERFACE_OFFSET_UM = 1e-7


def _layout(
    x: np.ndarray, members: dict[int, np.ndarray], materials: dict[int, str]
) -> tuple[np.ndarray, dict[tuple[int, float], int]]:
    """Position grid and the grid slot of every (region, station).

    At a boundary between two regions a quantity can jump (doping, band-gap narrowing, mobility
    and recombination at a p-n junction as much as the permittivity at an oxide), so each side
    keeps its own slot, separated by a negligible offset that keeps the position axis strictly
    increasing. Merging same-material neighbors would average or drop one side of the jump.
    """
    slots: list[dict[str, object]] = []
    slot_of: dict[tuple[int, float], int] = {}
    for region in sorted(members, key=lambda item: float(np.min(x[members[item]]))):
        for station in sorted({round(float(x[vertex]), 9) for vertex in members[region]}):
            last = slots[-1] if slots else None
            if last is not None and abs(float(last["raw"]) - station) < 1e-9:
                last["x"] = station - _INTERFACE_OFFSET_UM
                position = station + _INTERFACE_OFFSET_UM
            else:
                position = station
            slots.append({"x": position, "raw": station, "material": materials[region]})
            slot_of[(region, station)] = len(slots) - 1
    positions = np.array([float(slot["x"]) for slot in slots])
    if np.any(np.diff(positions) <= 0):
        raise NativeExportError("the position grid is not strictly increasing")
    return positions, slot_of


def _read_point(path: Path, height_um: float):
    import h5py

    area_m2 = height_um * 1e-12  # slab height by the 1 um native depth of a 2D device
    with h5py.File(path, "r") as handle:
        geometry = handle["collection/geometry_0"]
        coordinates = geometry["vertex"][()]
        x = np.asarray(coordinates["x"], dtype=float)
        y = np.asarray(coordinates["y"], dtype=float)
        names: dict[int, str] = {}
        members: dict[int, np.ndarray] = {}
        materials: dict[int, str] = {}
        for key in geometry:
            if key.startswith("region_"):
                index = int(key.split("_")[1])
                group = geometry[key]
                names[index] = _text(group.attrs["name"])
                if int(group.attrs["type"]) == 0:
                    members[index] = _region_vertices(group)
                    materials[index] = _text(group.attrs.get("material", b""))
        state = handle["collection/geometry_0/state_0"]
        stations, slot_of = _layout(x, members, materials)
        profiles: dict[str, np.ndarray] = {}
        terminals: dict[str, dict[str, float]] = {}
        for key in state:
            if not key.startswith("dataset_"):
                continue
            node = state[key]
            name = _text(node.attrs["name"])
            region = int(node.attrs["region"])
            values = np.asarray(node["values"][()], dtype=float)
            if name.startswith("Contact"):
                terminals.setdefault(names[region], {})[name] = float(values[0])
                continue
            if name not in _FIELDS:
                continue
            _, _, scale, component = _FIELDS[name]
            if region not in members:
                continue
            count = len(members[region])
            if component is not None:
                values = values.reshape(count, -1)[:, component]
            if len(values) != count:
                raise NativeExportError(f"dataset {name} does not match its region vertices")
            sums = profiles.setdefault(name, np.zeros((2, len(stations))))
            for vertex, value in zip(members[region], values * scale, strict=True):
                station = slot_of[(region, round(float(x[vertex]), 9))]
                sums[0, station] += value
                sums[1, station] += 1
        # A quantity that exists in only some regions (carriers are absent in an oxide) is
        # marked invalid where it does not exist; no value is invented there.
        reduced = {
            name: (
                np.divide(sums[0], sums[1], out=np.zeros_like(sums[0]), where=sums[1] > 0),
                sums[1] > 0,
            )
            for name, sums in profiles.items()
        }
        _check_lateral_uniformity(state, members, names, x, y, stations)
        return stations, reduced, terminals, area_m2


def _check_lateral_uniformity(state, members, names, x, y, stations) -> None:
    for key in state:
        if not key.startswith("dataset_"):
            continue
        node = state[key]
        if _text(node.attrs["name"]) != "ElectrostaticPotential":
            continue
        region = int(node.attrs["region"])
        if region not in members:
            continue
        values = np.asarray(node["values"][()], dtype=float)
        rows: dict[float, list[float]] = {}
        for vertex, value in zip(members[region], values, strict=True):
            rows.setdefault(round(float(x[vertex]), 9), []).append(float(value))
        scale = max(float(np.max(np.abs(values))), 1e-12)
        for station, samples in rows.items():
            if max(samples) - min(samples) > _LATERAL_RTOL * scale:
                raise NativeExportError(
                    f"the 1D unit slab is not laterally uniform at x={station} um"
                )


def _region_triangles(group) -> np.ndarray:
    raw = group["elements_0"][()]
    triangles: list[list[int]] = []
    cursor = 0
    while cursor < len(raw):
        kind = int(raw[cursor])
        if kind not in _ELEMENT_VERTICES:
            raise NativeExportError(f"unsupported TDR element type {kind}")
        count = _ELEMENT_VERTICES[kind]
        if kind == 2:
            triangles.append([int(item) for item in raw[cursor + 1 : cursor + 4]])
        cursor += 1 + count
    return np.asarray(triangles, dtype=np.int64).reshape(-1, 3)


def _locate(triangles: np.ndarray, x: np.ndarray, y: np.ndarray, px: np.ndarray, py: float):
    """Triangle index and barycentric weights containing each sample point (or -1)."""
    ax, ay = x[triangles[:, 0]], y[triangles[:, 0]]
    bx, by = x[triangles[:, 1]], y[triangles[:, 1]]
    cx, cy = x[triangles[:, 2]], y[triangles[:, 2]]
    denominator = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    with np.errstate(divide="ignore", invalid="ignore"):
        w0 = (
            (by - cy)[None, :] * (px[:, None] - cx[None, :])
            + (cx - bx)[None, :] * (py - cy[None, :])
        ) / denominator[None, :]
        w1 = (
            (cy - ay)[None, :] * (px[:, None] - cx[None, :])
            + (ax - cx)[None, :] * (py - cy[None, :])
        ) / denominator[None, :]
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9) & np.isfinite(w0)
    found = np.where(inside.any(axis=1), inside.argmax(axis=1), -1)
    rows = np.arange(len(px))
    weights = np.stack([w0[rows, found], w1[rows, found], w2[rows, found]], axis=1)
    return found, weights


def _read_point_2d(path: Path, depths_um: list[float], grid_um: np.ndarray | None):
    """Terminal data and line-cut profiles of one native 2D result.

    ``depths_um`` are the cut depths on the spec stack axis (the editor's second coordinate).
    Values are interpolated linearly on the native triangles of the region containing each
    sample; a sample no region contains is invalid.
    """
    import h5py

    with h5py.File(path, "r") as handle:
        geometry = handle["collection/geometry_0"]
        vertices = geometry["vertex"][()]
        x = np.asarray(vertices["x"], dtype=float)  # lateral (editor X)
        y = np.asarray(vertices["y"], dtype=float)  # depth (editor Y)
        names: dict[int, str] = {}
        members: dict[int, np.ndarray] = {}
        triangles: dict[int, np.ndarray] = {}
        for key in geometry:
            if key.startswith("region_"):
                index = int(key.split("_")[1])
                group = geometry[key]
                names[index] = _text(group.attrs["name"])
                if int(group.attrs["type"]) == 0:
                    members[index] = _region_vertices(group)
                    triangles[index] = _region_triangles(group)
        grid = grid_um if grid_um is not None else np.unique(np.round(x, 9))
        state = geometry["state_0"]
        terminals: dict[str, dict[str, float]] = {}
        fields: dict[tuple[str, int], np.ndarray] = {}
        for key in state:
            if not key.startswith("dataset_"):
                continue
            node = state[key]
            name = _text(node.attrs["name"])
            region = int(node.attrs["region"])
            values = np.asarray(node["values"][()], dtype=float)
            if name.startswith("Contact"):
                terminals.setdefault(names[region], {})[name] = float(values[0])
                continue
            if name not in _FIELDS or region not in members or _FIELDS[name][3] is not None:
                continue  # vector quantities are not defined along a 2D cut
            scale = _FIELDS[name][2]
            full = np.full(len(x), np.nan)
            full[members[region]] = values * scale
            fields[(name, region)] = full
        profiles: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for cut_index, depth in enumerate(depths_um):
            hits = {region: _locate(triangles[region], x, y, grid, depth) for region in triangles}
            for (name, region), full in fields.items():
                found, weights = hits[region]
                tri = triangles[region]
                values = np.zeros(len(grid))
                valid = found >= 0
                if valid.any():
                    corners = tri[found[valid]]
                    values[valid] = (full[corners] * weights[valid]).sum(axis=1)
                key = name if cut_index == 0 else f"{name}@{cut_index}"
                previous = profiles.get(key)
                if previous is None:
                    profiles[key] = (values, valid & np.isfinite(values))
                else:  # the same quantity in another region fills samples the first lacked
                    merged = np.where(previous[1], previous[0], values)
                    profiles[key] = (merged, previous[1] | (valid & np.isfinite(values)))
        for key, (values, valid) in profiles.items():
            profiles[key] = (np.where(valid, values, 0.0), valid)
        return grid, profiles, terminals


def _contact_geometry_2d(spec: ExperimentSpec) -> dict[str, float]:
    """Length (m) of every contact segment."""
    by_id = {region.id: region for region in spec.regions}
    return {
        contact.id: geometry2d.segment_length(contact, by_id[contact.region])
        for contact in spec.contacts
    }


def build_export(raw_dir: Path, spec: ExperimentSpec, manifest: SentaurusJobManifest) -> Path:
    """Write ``sentaurus-result.json`` and ``profiles.csv`` beside the fetched outputs."""
    two_dimensional = manifest.mesh_generation == "sde_2d"
    if manifest.mesh_generation not in GENERATED_MESHES or (
        not two_dimensional and manifest.slab_height_um is None
    ):
        raise NativeExportError("local export requires a generated structure job")
    points = [point.to("V") for point in expand_study_points(spec.study)] or [0.0]
    log_path = raw_dir / "sdevice.stdout.log"
    if not log_path.is_file():
        raise NativeExportError("the Sentaurus Device log was not retrieved")
    log_text = log_path.read_text(errors="replace")
    version = simulator_version(log_text)
    escalation = escalation_notes(log_text, two_dimensional=two_dimensional)
    contacts = [contact.id for contact in spec.contacts]

    stations: np.ndarray | None = None
    per_point: list[dict[str, np.ndarray]] = []
    lengths = _contact_geometry_2d(spec) if two_dimensional else {}
    depths_um = [cut.at.to("m") * 1e6 for cut in spec.profile_cuts]
    unit_width_m = 1e-6  # native depth of a 2D result
    operating_points: list[dict[str, object]] = []
    for index, bias in enumerate(points):
        path = raw_dir / f"point_{index:04d}_des.tdr"
        if not path.is_file():
            raise NativeExportError(f"missing native output {path.name}")
        if two_dimensional:
            grid, profiles, terminals = _read_point_2d(path, depths_um, stations)
            areas = {name: lengths[name] * unit_width_m for name in lengths}
        else:
            grid, profiles, terminals, area = _read_point(path, manifest.slab_height_um)
            areas = {name: area for name in (contact.id for contact in spec.contacts)}
        if stations is None:
            stations = grid
        elif not np.array_equal(stations, grid):
            raise NativeExportError("the mesh changed between operating points")
        per_point.append(profiles)
        if set(terminals) != set(contacts):
            raise NativeExportError("native contacts differ from the experiment contacts")
        for name in contacts:
            if {"ContactCurrentFlux", "ContactCharge", "ContactExternalVoltage"} - set(
                terminals[name]
            ):
                raise NativeExportError(f"native output lacks terminal data for {name}")
        stalled = _unreached_voltage(spec, bias, terminals)
        operating_points.append(
            {
                "index": index,
                "state": "failed" if stalled else "converged",
                **({"message": stalled} if stalled else {}),
                "coordinates": {"bias": float(bias)},
                "terminal_currents_a_per_m2": {
                    name: terminals[name]["ContactCurrentFlux"] / areas[name] for name in contacts
                },
                "terminal_charges_c_per_m2": {
                    name: terminals[name]["ContactCharge"] / areas[name] for name in contacts
                },
            }
        )
    assert stations is not None
    keys = list(per_point[0]) if per_point else []
    present = [key for key in keys if all(key in profiles for profiles in per_point)]
    if not present and not two_dimensional:
        raise NativeExportError("no recognized spatial datasets were found")
    # The export contract has one bias axis covering every solved point, so spatial profiles
    # are exported at every solved bias. That always includes each requested sampling bias,
    # which must have been solved; extra profiles are real data, never a substitute.
    if spec.profile_sampling is not None:
        for wanted in spec.profile_bias_values_v():
            if not any(math.isclose(bias, wanted, abs_tol=1e-12) for bias in points):
                raise NativeExportError(f"requested profile bias {wanted} V was not simulated")
    profile_indices = list(range(len(points)))
    profile_biases = [float(bias) for bias in points]

    columns: dict[str, list[float]] = {}
    datasets: dict[str, dict[str, object]] = {}
    requested = {str(observable) for observable in spec.observables}
    for name in present:
        base, _, cut = name.partition("@")
        quantity, unit, _, _ = _FIELDS[base]
        if quantity in _ONLY_WHEN_REQUESTED and quantity not in requested:
            continue
        column = quantity if not cut else f"{quantity}__{spec.profile_cuts[int(cut)].id}"
        flat = [float(v) for i in profile_indices for v in per_point[i][name][0]]
        valid = [bool(v) for i in profile_indices for v in per_point[i][name][1]]
        if not all(math.isfinite(value) for value in flat):
            raise NativeExportError(f"dataset {name} contains non-finite values")
        columns[column] = flat
        datasets[column] = {
            "id": column,
            "quantity": quantity,
            "label": _LABELS[quantity],
            "unit": unit,
            "axes": ["bias", "position"],
            "shape": [len(profile_indices), len(stations)],
            "centering": "node",
            **({} if all(valid) else {"validity": valid}),
        }
    # Absolute quantities exist only for contacts whose physical area the researcher gave.
    for contact in spec.contacts:
        if two_dimensional:
            if spec.width is None:
                continue
            area = lengths[contact.id] * spec.width.to("m")
        elif contact.area is None:
            continue
        else:
            area = float(contact.area.to("m^2"))
        for prefix, quantity, unit, key in (
            (
                "absolute_terminal_current",
                "absolute_terminal_current",
                "A",
                "terminal_currents_a_per_m2",
            ),
            (
                "absolute_terminal_charge",
                "absolute_terminal_charge",
                "C",
                "terminal_charges_c_per_m2",
            ),
        ):
            name = f"{prefix}__{contact.id}"
            datasets[name] = {
                "id": name,
                "quantity": quantity,
                "label": f"{quantity.replace('_', ' ').capitalize()} at {contact.id}",
                "unit": unit,
                "axes": ["bias"],
                "shape": [len(points)],
                "centering": "operating_point",
                "values": [point[key][contact.id] * area for point in operating_points],
            }
    electron_level = columns.get("electron_quasi_fermi_level")
    hole_level = columns.get("hole_quasi_fermi_level")
    if electron_level and hole_level and spec.study.kind == "equilibrium":
        # A single Fermi level exists only at equilibrium, where both quasi-Fermi levels agree.
        spread = max(abs(a - b) for a, b in zip(electron_level, hole_level, strict=True))
        if spread > 1e-6:
            raise NativeExportError("quasi-Fermi levels disagree at equilibrium")
        columns["fermi_level"] = list(electron_level)
        datasets["fermi_level"] = {
            **datasets["electron_quasi_fermi_level"],
            "id": "fermi_level",
            "quantity": "fermi_level",
            "label": "Fermi level",
        }
    if not datasets:
        # A 2D run with no profile cut still returns its terminal curves.
        for name in contacts:
            datasets[f"terminal_current_density__{name}"] = {
                "id": f"terminal_current_density__{name}",
                "quantity": "terminal_current_density",
                "label": f"Terminal current density at {name}",
                "unit": "A/m^2",
                "axes": ["bias"],
                "shape": [len(points)],
                "centering": "operating_point",
                "values": [point["terminal_currents_a_per_m2"][name] for point in operating_points],
            }
    if columns:
        csv_path = raw_dir / "profiles.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(columns)
            for row in zip(*columns.values(), strict=True):
                writer.writerow([repr(value) for value in row])
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        for quantity, dataset in datasets.items():
            if "values" not in dataset:
                dataset["table"] = {"file": "profiles.csv", "sha256": digest, "column": quantity}

    export = {
        "schema_version": "2.0",
        "simulator_version": version,
        "status": "completed",
        "terminals": contacts,
        "physics_models": list(spec.physics.models),
        "native_defaults": [*native_defaults(spec), *escalation],
        "provenance": {
            "compiler_version": manifest.compiler_version,
            "experiment_sha256": manifest.inputs["experiment.json"],
            "mesh_sha256": manifest.inputs["mesh.scm"],
        },
        "sign_convention": {
            "terminal_current": "positive_into_device",
            "terminal_charge": "outward_displacement_flux",
        },
        "axes": {
            "bias": {
                "id": "bias",
                "kind": "bias",
                "label": "Drive voltage",
                "unit": "V",
                "values": profile_biases,
            },
            "position": {
                "id": "position",
                "kind": "position",
                "label": "Position",
                "unit": "um",
                "values": [float(value) for value in stations],
            },
        },
        "datasets": datasets,
        "operating_points": operating_points,
    }
    target = raw_dir / "sentaurus-result.json"
    target.write_text(json.dumps(export, indent=2) + "\n", encoding="utf-8")
    return target
