"""Reviewed, data-only DEVSIM 1D runtime copied into compiled workspaces.

All expression strings in this file are platform-owned. The input payload is a
strict numeric and identifier contract produced by the adapter compiler.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, cast


class TransientRecoveryExhausted(RuntimeError):
    """Raised when a transient step cannot be reduced within reviewed bounds."""


@dataclass
class AdaptiveStepController:
    initial_step: float
    minimum_step: float
    maximum_step: float
    maximum_retries: int
    growth_factor: float = 1.5
    reduction_factor: float = 0.5

    def __post_init__(self) -> None:
        if not 0 < self.minimum_step <= self.initial_step <= self.maximum_step:
            raise ValueError("transient step bounds must be positive and ordered")
        if self.maximum_retries < 0:
            raise ValueError("maximum transient retries must be nonnegative")
        self._step = self.initial_step
        self._retries = 0

    @property
    def attempt(self) -> int:
        return self._retries + 1

    def candidate(self, remaining: float) -> float:
        return min(self._step, self.maximum_step, remaining)

    def failed(self) -> float:
        self._retries += 1
        reduced = self._step * self.reduction_factor
        if self._retries > self.maximum_retries or reduced < self.minimum_step:
            raise TransientRecoveryExhausted(
                "transient step recovery exhausted retry or minimum-step limit"
            )
        self._step = reduced
        return self._step

    def succeeded(self) -> None:
        self._retries = 0
        self._step = min(self.maximum_step, self._step * self.growth_factor)


def waveform_voltage(study: dict[str, Any], time_s: float) -> float:
    """Evaluate an explicit transient waveform without simulator-specific state."""

    initial = float(study["initial_voltage_v"])
    final = float(study["final_voltage_v"])
    start = float(study["start_s"])
    stop = float(study["stop_s"])
    waveform = str(study["waveform"])
    if waveform == "step":
        return final
    if waveform == "ramp":
        fraction = min(1.0, max(0.0, (time_s - start) / (stop - start)))
        return initial + fraction * (final - initial)
    if waveform != "pulse":
        raise ValueError(f"unsupported transient waveform: {waveform}")
    delay = float(study["pulse_delay_s"])
    rise = float(study["rise_time_s"])
    width = float(study["pulse_width_s"])
    fall = float(study["fall_time_s"])
    elapsed = time_s - start
    if elapsed <= delay:
        return initial
    if rise > 0 and elapsed < delay + rise:
        return initial + (elapsed - delay) / rise * (final - initial)
    if elapsed <= delay + rise + width:
        return final
    if fall > 0 and elapsed < delay + rise + width + fall:
        fraction = (elapsed - delay - rise - width) / fall
        return final + fraction * (initial - final)
    return initial


def _inverse_fermi_ratio(ratio: float) -> float:
    """Pinned Joyce-Dixon inverse used by DEVSIM 2.9.1's native InvFermi."""

    if ratio <= 0:
        raise ValueError("Fermi carrier ratio must be positive")
    breakpoint = 8.46296036621705
    if ratio < breakpoint:
        return (
            math.log(ratio)
            + 0.5 / math.sqrt(math.pi) * ratio
            - 4.9500897298752622e-3 * ratio**2
            + 1.4838577128872821e-4 * ratio**3
            - 4.4256301190009895e-6 * ratio**4
        )
    return math.sqrt(
        (0.75 * math.sqrt(math.pi) * ratio) ** (4.0 / 3.0)
        - math.pi**2 / 6.0
    ) - 0.0137050034663995


def _fermi_ratio(eta: float) -> float:
    """Invert the pinned approximation with the same positive Newton update."""

    ratio = max(math.exp(min(eta, 700.0)), 1e-300)
    for _ in range(40):
        value = _inverse_fermi_ratio(ratio) - eta
        epsilon = max(ratio * 1e-7, 1e-12)
        derivative = (
            _inverse_fermi_ratio(ratio + epsilon)
            - _inverse_fermi_ratio(max(ratio - epsilon, ratio * 0.5))
        ) / (epsilon + min(epsilon, ratio * 0.5))
        update = -value / derivative
        while ratio + update <= 0:
            update *= 0.5
        ratio += update
        if abs(update) <= 1e-13 * max(abs(ratio), 1.0):
            break
    return ratio


def _fermi_contact_state(
    *,
    net_doping_cm3: float,
    conduction_density_cm3: float,
    valence_density_cm3: float,
    band_gap_ev: float,
    thermal_voltage_v: float,
) -> tuple[float, float, float]:
    """Return neutral n, p, and electrostatic potential for an ohmic boundary."""

    gap = band_gap_ev / thermal_voltage_v

    def neutrality(eta_n: float) -> float:
        electrons = conduction_density_cm3 * _fermi_ratio(eta_n)
        holes = valence_density_cm3 * _fermi_ratio(-gap - eta_n)
        return electrons - holes - net_doping_cm3

    lower = -max(gap + 80.0, 160.0)
    upper = max(gap + 80.0, 160.0)
    for _ in range(240):
        middle = 0.5 * (lower + upper)
        if neutrality(middle) < 0:
            lower = middle
        else:
            upper = middle
    eta_n = 0.5 * (lower + upper)
    electrons = conduction_density_cm3 * _fermi_ratio(eta_n)
    holes = valence_density_cm3 * _fermi_ratio(-gap - eta_n)
    energy_offset = 0.5 * band_gap_ev + 0.5 * thermal_voltage_v * math.log(
        conduction_density_cm3 / valence_density_cm3
    )
    potential = energy_offset + thermal_voltage_v * eta_n
    return electrons, holes, potential

NATIVE_MODEL_NAMES = {
    "potential": "Potential",
    "electric_field": "ElectricField",
    "electrostatic_flux": "PotentialEdgeFlux",
    "fixed_charge_density": "FixedBulkCharge",
    "electron_density": "Electrons",
    "hole_density": "Holes",
    "charge_density": "derived:ElectronCharge*(Holes-Electrons+NetDoping)",
    "net_doping": "NetDoping",
    "donor_concentration": "PhysicalDonors",
    "acceptor_concentration": "PhysicalAcceptors",
    "electron_current_density": "ElectronCurrent",
    "hole_current_density": "HoleCurrent",
    "total_current_density": "derived:ElectronCurrent+HoleCurrent",
    "electron_mobility": "selected electron mobility model",
    "hole_mobility": "selected hole mobility model",
    "srh_recombination_rate": "USRH",
    "auger_recombination_rate": "UAuger",
    "recombination_rate": "TotalRecombination",
    "total_recombination_rate": "TotalRecombination",
    "electron_generation_rate": "NetCarrierGeneration",
    "hole_generation_rate": "NetCarrierGeneration",
    "conduction_band": "ConductionBandEnergy",
    "valence_band": "ValenceBandEnergy",
    "intrinsic_energy": "IntrinsicEnergy",
    "fermi_level": "FermiLevelEnergy",
    "electron_quasi_fermi_level": "ElectronQuasiFermiEnergy",
    "hole_quasi_fermi_level": "HoleQuasiFermiEnergy",
    "electron_affinity": "ElectronAffinityEnergy",
    "band_gap": "MaterialBandGap",
    "band_gap_narrowing": "BandGapNarrowing",
    "effective_intrinsic_carrier_concentration": "EffectiveIntrinsicDensity",
}


def _boundary_tag(index: int, count: int) -> str:
    if index == 0:
        return "x_min"
    if index == count:
        return "x_max"
    return f"boundary_{index}"


def _backend_contact_id(contact: dict[str, Any]) -> str:
    """Return an expression-safe DEVSIM identifier for a public contact id."""
    return str(contact.get("backend_id") or contact["id"])


def _backend_contact_for_id(payload: dict[str, Any], contact_id: str) -> str:
    contact = next(
        item for item in payload["contacts"] if item["id"] == contact_id
    )
    return _backend_contact_id(contact)


def _profile_expression(profile: dict[str, Any], region: dict[str, Any]) -> str:
    kind = profile["kind"]
    if kind == "constant":
        return f"{profile['value_cm3']:.17e}"
    if kind == "fixed_charge":
        return f"{profile['density_c_cm3']:.17e}"
    if kind == "linear":
        width = region["x1_cm"] - region["x0_cm"]
        delta = profile["end_value_cm3"] - profile["start_value_cm3"]
        return (
            f"{profile['start_value_cm3']:.17e}+"
            f"((x-{region['x0_cm']:.17e})/{width:.17e})*{delta:.17e}"
        )
    if kind == "gaussian":
        return (
            f"{profile['peak_cm3']:.17e}*exp(-0.5*((x-"
            f"{profile['center_cm']:.17e})/"
            f"{profile['standard_deviation_cm']:.17e})^2)"
        )
    if kind == "error_function":
        argument = (
            f"((x-{profile['junction_position_cm']:.17e})/"
            f"{profile['characteristic_length_cm']:.17e})"
        )
        fraction = f"0.5*erfc{argument}"
        if profile["orientation"] == "increasing_x":
            fraction = f"(1-({fraction}))"
        return f"{profile['surface_value_cm3']:.17e}*({fraction})"
    if kind == "tabulated":
        positions = profile["positions_cm"]
        values = profile["values_cm3"]
        expression = f"{values[-1]:.17e}"
        for index in range(len(positions) - 2, -1, -1):
            x0, x1 = positions[index], positions[index + 1]
            y0, y1 = values[index], values[index + 1]
            if profile.get("interpolation", "linear") == "nearest":
                boundary = (x0 + x1) / 2
                segment = f"{y0:.17e}"
            else:
                boundary = x1
                segment = (
                    f"{y0:.17e}+(x-{x0:.17e})*"
                    f"{((y1-y0)/(x1-x0)):.17e}"
                )
            expression = f"ifelse(x < {boundary:.17e}, {segment}, {expression})"
        return expression
    if kind == "piecewise_constant":
        boundaries = profile["boundaries_cm"]
        values = profile["values_cm3"]
        expression = f"{values[-1]:.17e}"
        for index in range(len(values) - 2, -1, -1):
            expression = (
                f"ifelse(x < {boundaries[index + 1]:.17e}, "
                f"{values[index]:.17e}, {expression})"
            )
        return expression
    raise ValueError(f"unsupported profile kind: {kind}")


def _sum_expressions(expressions: list[str]) -> str:
    return "+".join(f"({expression})" for expression in expressions) or "0"


def _contact_region(payload: dict[str, Any], location: str) -> dict[str, Any]:
    return cast(dict[str, Any], payload["regions"][0 if location == "x_min" else -1])


def _interface_name(
    payload: dict[str, Any], left_region: str, right_region: str
) -> str:
    for interface in payload["interfaces"]:
        if (
            interface["left_region"] == left_region
            and interface["right_region"] == right_region
        ):
            return str(interface["id"])
    return f"interface__{left_region}__{right_region}"


def _bias_points(study: dict[str, Any]) -> list[float]:
    if study["kind"] == "equilibrium":
        return [0.0]
    if study["kind"] in {"dc", "dc_points"}:
        return [float(value) for value in study["biases_v"]]
    if study["kind"] in {"ac", "frequency"}:
        return [0.0]
    if study["kind"] == "transient":
        return [float(study["initial_voltage_v"])]
    raise ValueError(f"study is not implemented by this runtime: {study['kind']}")


def _append_field(
    fields: dict[str, dict[str, Any]],
    name: str,
    positions: list[float],
    values: list[float],
    unit: str,
    centering: str,
) -> None:
    target = fields.setdefault(
        name,
        {"positions_cm": [], "values": [], "unit": unit, "centering": centering},
    )
    target["positions_cm"].extend(positions)
    target["values"].extend(values)


def _run_payload_series(
    payload: dict[str, Any],
    *,
    axis_id: str,
    axis_kind: str,
    axis_label: str,
    axis_unit: str,
    payload_field: str,
) -> int:
    """Run a registered parameter series in isolated DEVSIM processes."""

    values = [float(value) for value in payload["study"]["values_si"]]
    child_results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="temperature-series-", dir=Path.cwd()) as root:
        root_path = Path(root)
        for index, value in enumerate(values):
            point_path = root_path / f"point-{index:04d}"
            point_path.mkdir()
            child_payload = json.loads(json.dumps(payload))
            child_payload["physics"][payload_field] = value
            child_payload["study"] = {"kind": "equilibrium"}
            input_path = point_path / "input.json"
            input_path.write_text(json.dumps(child_payload, sort_keys=True, indent=2))
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), str(input_path)],
                cwd=point_path,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"{axis_label} point {value:g} {axis_unit} failed: "
                    f"{completed.stderr}"
                )
            child_results.append(
                json.loads((point_path / "native_result.json").read_text())
            )

    reference = child_results[0]
    study_points: list[dict[str, Any]] = []
    field_sweeps: dict[str, dict[str, Any]] = {}
    solver_events: list[dict[str, Any]] = []
    for value, child in zip(values, child_results, strict=True):
        solver_events.extend(
            {**event, "study_axis": axis_id, "study_coordinate": value}
            for event in child.get("solver_events", [])
        )
        point = child["bias_points"][0]
        study_points.append(
            {
                "coordinate": value,
                "converged": bool(point["converged"]),
                "currents_a_per_cm2": point["currents_a_per_cm2"],
                "electron_currents_a_per_cm2": point.get(
                    "electron_currents_a_per_cm2", {}
                ),
                "hole_currents_a_per_cm2": point.get(
                    "hole_currents_a_per_cm2", {}
                ),
                "charges_c_per_cm2": point["charges_c_per_cm2"],
                "attempts": point.get("attempts", 1),
                "message": point.get("message"),
            }
        )
        for name, field in child["fields"].items():
            target = field_sweeps.setdefault(
                name,
                {
                    "positions_cm": field["positions_cm"],
                    "values": [],
                    "validity": [],
                    "unit": field["unit"],
                    "centering": field["centering"],
                },
            )
            if (
                target["positions_cm"] != field["positions_cm"]
                or target["unit"] != field["unit"]
                or target["centering"] != field["centering"]
            ):
                raise ValueError(f"field topology changed during {axis_label}: {name}")
            target["values"].extend(field["values"])
            target["validity"].extend(
                [bool(point["converged"])] * len(field["values"])
            )
    combined = {
        "schema_version": "2.0",
        "simulator_version": reference["simulator_version"],
        "status": "completed",
        "terminals": reference["terminals"],
        "contact_areas_m2": reference.get("contact_areas_m2", {}),
        "interface_charge_densities_c_per_cm2": reference.get(
            "interface_charge_densities_c_per_cm2", {}
        ),
        "bias_points": [],
        "fields": reference["fields"],
        "field_sweeps": {},
        "frequency_points": [],
        "ac_contact": None,
        "study_axis": {
            "id": axis_id,
            "kind": axis_kind,
            "label": axis_label,
            "unit": axis_unit,
            "values": values,
        },
        "study_points": study_points,
        "study_field_sweeps": field_sweeps,
        "requested_observables": payload["observables"],
        "sign_convention": payload["sign_convention"],
        "parameter_set_id": reference.get("parameter_set_id"),
        "parameter_sources": reference.get("parameter_sources", {}),
        "solver_configuration": reference.get("solver_configuration", {}),
        "solver_events": solver_events,
        "native_model_names": reference.get("native_model_names", {}),
        "regions": reference.get("regions", []),
        "interfaces": reference.get("interfaces", []),
    }
    Path("native_result.json").write_text(
        json.dumps(combined, sort_keys=True, indent=2)
    )
    return 0


def _run_temperature_series(payload: dict[str, Any]) -> int:
    return _run_payload_series(
        payload,
        axis_id="temperature",
        axis_kind="temperature",
        axis_label="Temperature",
        axis_unit="K",
        payload_field="temperature_k",
    )


def _run_parameter_series(payload: dict[str, Any]) -> int:
    runtime_fields = {
        "physics.parameters.electron_lifetime": "electron_lifetime_s",
        "physics.parameters.hole_lifetime": "hole_lifetime_s",
        "physics.parameters.auger_electron_coefficient": "auger_electron_cm6_s",
        "physics.parameters.auger_hole_coefficient": "auger_hole_cm6_s",
        "physics.parameters.bgn_reference_energy": "bgn_reference_energy_ev",
        "physics.parameters.bgn_reference_density": "bgn_reference_density_cm3",
    }
    study = payload["study"]
    parameter_path = str(study["parameter_path"])
    payload_field = runtime_fields.get(parameter_path)
    if payload_field is None:
        raise ValueError(f"unregistered parameter sweep target: {parameter_path}")
    return _run_payload_series(
        payload,
        axis_id="parameter",
        axis_kind="parameter",
        axis_label=parameter_path,
        axis_unit=str(study["unit"]),
        payload_field=payload_field,
    )


def main() -> int:
    import devsim  # type: ignore[import-untyped]
    from devsim import (
        add_1d_contact,
        add_1d_interface,
        add_1d_mesh_line,
        add_1d_region,
        circuit_alter,
        circuit_element,
        contact_equation,
        create_1d_mesh,
        create_device,
        edge_from_node_model,
        equation,
        finalize_mesh,
        get_circuit_node_value,
        get_contact_charge,
        get_contact_current,
        get_edge_model_values,
        get_node_model_values,
        get_parameter,
        interface_equation,
        set_node_values,
        set_parameter,
        solve,
    )
    from devsim.python_packages.Klaassen import (  # type: ignore[import-untyped]
        Klaassen_Mobility,
        Set_Mobility_Parameters,
    )
    from devsim.python_packages.model_create import (  # type: ignore[import-untyped]
        CreateContactNodeModel,
        CreateContactNodeModelDerivative,
        CreateContinuousInterfaceModel,
        CreateEdgeModel,
        CreateEdgeModelDerivatives,
        CreateNodeModel,
        CreateNodeModelDerivative,
        CreateSolution,
        InEdgeModelList,
    )
    from devsim.python_packages.simple_physics import (  # type: ignore[import-untyped]
        CreateOxideContact,
        CreateOxidePotentialOnly,
        CreateSiliconDriftDiffusion,
        CreateSiliconDriftDiffusionAtContact,
        CreateSiliconOxideInterface,
        CreateSiliconPotentialOnly,
        CreateSiliconPotentialOnlyContact,
        GetContactBiasName,
        GetContactNodeModelName,
        SetOxideParameters,
        SetSiliconParameters,
    )

    payload_path = Path(sys.argv[1] if len(sys.argv) > 1 else "input.json")
    payload = json.loads(payload_path.read_text())
    if payload.get("schema_version") != "2.0":
        raise ValueError("unsupported DEVSIM payload schema")
    if payload["study"]["kind"] == "temperature":
        return _run_temperature_series(payload)
    if payload["study"]["kind"] == "parameter":
        return _run_parameter_series(payload)
    device = "novatom_device"
    mesh = "novatom_mesh"
    regions = payload["regions"]
    study = payload["study"]
    solver_events: list[dict[str, Any]] = []
    is_ac = study["kind"] in {"ac", "frequency"}
    is_transient = study["kind"] == "transient"
    is_circuit_study = is_ac or is_transient
    circuit_source_name = "V_STUDY"
    contact_offsets = {
        contact["id"]: float(contact.get("voltage_offset_v", 0.0))
        for contact in payload["contacts"]
    }
    study_backend_contact = (
        _backend_contact_for_id(payload, study["contact"])
        if study.get("contact") is not None
        else None
    )
    if is_circuit_study:
        assert study_backend_contact is not None
        initial_value = contact_offsets[study["contact"]] + float(
            study.get("initial_voltage_v", 0.0)
        )
        circuit_element(
            name=circuit_source_name,
            n1=GetContactBiasName(study_backend_contact),
            n2=0,
            value=initial_value,
            acreal=study.get("amplitude_v", 0.0),
            acimag=0.0,
        )
    create_1d_mesh(mesh=mesh)
    mesh_lines: dict[float, dict[str, Any]] = {}
    for index in range(len(regions) + 1):
        if index == 0:
            position = regions[0]["x0_cm"]
            spacing = regions[0]["mesh_spacing_cm"]
        elif index == len(regions):
            position = regions[-1]["x1_cm"]
            spacing = regions[-1]["mesh_spacing_cm"]
        else:
            position = regions[index - 1]["x1_cm"]
            spacing = min(
                regions[index - 1]["mesh_spacing_cm"],
                regions[index]["mesh_spacing_cm"],
            )
            interface_record = next(
                (
                    item
                    for item in payload["interfaces"]
                    if item["left_region"] == regions[index - 1]["id"]
                    and item["right_region"] == regions[index]["id"]
                ),
                None,
            )
            if interface_record is not None and interface_record.get(
                "mesh_spacing_cm"
            ) is not None:
                spacing = min(spacing, float(interface_record["mesh_spacing_cm"]))
        mesh_lines[float(position)] = {
            "spacing": float(spacing),
            "tag": _boundary_tag(index, len(regions)),
        }
    for anchor_index, anchor in enumerate(payload.get("mesh_anchors", [])):
        position = float(anchor["position_cm"])
        spacing = float(anchor["spacing_cm"])
        existing = mesh_lines.get(position)
        if existing is None:
            mesh_lines[position] = {
                "spacing": spacing,
                "tag": f"mesh_anchor_{anchor_index}",
            }
        else:
            existing["spacing"] = min(float(existing["spacing"]), spacing)
    for position, line in sorted(mesh_lines.items()):
        add_1d_mesh_line(
            mesh=mesh,
            pos=position,
            ps=float(line["spacing"]),
            tag=str(line["tag"]),
        )
    for contact in payload["contacts"]:
        add_1d_contact(
            mesh=mesh,
            name=_backend_contact_id(contact),
            tag=contact["location"],
            material="metal",
        )
    interface_names: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for index, (left, right) in enumerate(pairwise(regions), start=1):
        name = _interface_name(payload, left["id"], right["id"])
        add_1d_interface(mesh=mesh, name=name, tag=_boundary_tag(index, len(regions)))
        interface_names.append((name, left, right))
    material_names = {
        "silicon": "Si",
        "silicon_dioxide": "Ox",
        "generic_dielectric": "Ox",
    }
    for index, region in enumerate(regions):
        add_1d_region(
            mesh=mesh,
            material=material_names[region["material"]],
            region=region["id"],
            tag1=_boundary_tag(index, len(regions)),
            tag2=_boundary_tag(index + 1, len(regions)),
        )
    finalize_mesh(mesh=mesh)
    create_device(mesh=mesh, device=device)

    temperature = payload["physics"]["temperature_k"]
    selected_models = set(payload["physics"]["models"])
    fermi_statistics = "fermi" in selected_models
    if fermi_statistics:
        set_parameter(device=device, name="FermiBlend", value=0.0)
    by_region: dict[str, list[dict[str, Any]]] = {
        region["id"]: [] for region in regions
    }
    for profile in payload["profiles"]:
        by_region[profile["region"]].append(profile)
    regions_with_fixed_bulk = {
        region_name
        for region_name, profiles in by_region.items()
        if any(profile["kind"] == "fixed_charge" for profile in profiles)
    }
    for region in regions:
        name = region["id"]
        fixed_bulk_charge = [
            _profile_expression(profile, region)
            for profile in by_region[name]
            if profile["kind"] == "fixed_charge"
        ]
        CreateNodeModel(
            device,
            name,
            "FixedBulkCharge",
            _sum_expressions(fixed_bulk_charge),
        )
        if region["material"] == "silicon":
            SetSiliconParameters(device, name, temperature)
            thermal_voltage = 8.617333262145e-5 * temperature
            band_gap = 1.17 - 4.73e-4 * temperature * temperature / (
                temperature + 636.0
            )
            density_scale = (temperature / 300.0) ** 1.5
            conduction_density = (
                payload["physics"]["effective_density_conduction_cm3"]
                * density_scale
            )
            valence_density = (
                payload["physics"]["effective_density_valence_cm3"]
                * density_scale
            )
            intrinsic_density = math.sqrt(
                conduction_density * valence_density
            ) * math.exp(-band_gap / (2.0 * thermal_voltage))
            for parameter, value in (
                ("ElectronAffinity", payload["physics"]["electron_affinity_ev"]),
                ("BandGap", band_gap),
                (
                    "EffectiveDensityConduction",
                    conduction_density,
                ),
                (
                    "EffectiveDensityValence",
                    valence_density,
                ),
                ("taun", payload["physics"]["electron_lifetime_s"]),
                ("taup", payload["physics"]["hole_lifetime_s"]),
                ("AugerElectron", payload["physics"]["auger_electron_cm6_s"]),
                ("AugerHole", payload["physics"]["auger_hole_cm6_s"]),
                (
                    "BGNReferenceEnergy",
                    payload["physics"]["bgn_reference_energy_ev"],
                ),
                (
                    "BGNReferenceDensity",
                    payload["physics"]["bgn_reference_density_cm3"],
                ),
                ("n_i", intrinsic_density),
                ("n1", intrinsic_density),
                ("p1", intrinsic_density),
                ("mu_n", 400.0 * (temperature / 300.0) ** -2.42),
                ("mu_p", 200.0 * (temperature / 300.0) ** -2.20),
                ("vsat_e", 1.0e7),
                ("vsat_h", 1.0e7),
            ):
                set_parameter(device=device, region=name, name=parameter, value=value)
            donors = [
                _profile_expression(profile, region)
                for profile in by_region[name]
                if profile.get("species") == "donor"
            ]
            acceptors = [
                _profile_expression(profile, region)
                for profile in by_region[name]
                if profile.get("species") == "acceptor"
            ]
            CreateNodeModel(
                device, name, "PhysicalDonors", _sum_expressions(donors)
            )
            CreateNodeModel(
                device, name, "PhysicalAcceptors", _sum_expressions(acceptors)
            )
            if "klaassen_mobility" in selected_models:
                # The reviewed DEVSIM Klaassen implementation divides by each
                # dopant species. A 1 cm^-3 computational floor is used only
                # inside the mobility model; electrostatics and reported dopant
                # fields retain the exact researcher-defined concentrations.
                CreateNodeModel(device, name, "Donors", "max(PhysicalDonors, 1)")
                CreateNodeModel(
                    device, name, "Acceptors", "max(PhysicalAcceptors, 1)"
                )
            else:
                CreateNodeModel(device, name, "Donors", "PhysicalDonors")
                CreateNodeModel(device, name, "Acceptors", "PhysicalAcceptors")
            CreateNodeModel(
                device,
                name,
                "NetDoping",
                "PhysicalDonors-PhysicalAcceptors",
            )
            CreateSolution(device, name, "Potential")
            CreateSiliconPotentialOnly(device, name)
            if name in regions_with_fixed_bulk:
                CreateNodeModel(
                    device,
                    name,
                    "PotentialChargeWithBulk",
                    "PotentialIntrinsicCharge+FixedBulkCharge",
                )
                CreateNodeModelDerivative(
                    device,
                    name,
                    "PotentialChargeWithBulk",
                    "PotentialIntrinsicCharge+FixedBulkCharge",
                    "Potential",
                )
                equation(
                    device=device,
                    region=name,
                    name="PotentialEquation",
                    variable_name="Potential",
                    node_model="PotentialChargeWithBulk",
                    edge_model="PotentialEdgeFlux",
                    variable_update="default",
                )
            if "slotboom_bgn" in selected_models:
                logarithm = "log((abs(NetDoping)+1)/BGNReferenceDensity)"
                bgn = (
                    f"BGNReferenceEnergy*({logarithm}+"
                    f"pow(({logarithm})^2+0.5, 0.5))"
                )
                CreateNodeModel(device, name, "BandGapNarrowing", bgn)
                CreateNodeModel(
                    device,
                    name,
                    "EffectiveIntrinsicDensity",
                    "n_i*exp(BandGapNarrowing/(2*V_t))",
                )
                electron_expression = "EffectiveIntrinsicDensity*exp(Potential/V_t)"
                hole_expression = "EffectiveIntrinsicDensity*exp(-Potential/V_t)"
                CreateNodeModel(device, name, "IntrinsicElectrons", electron_expression)
                CreateNodeModelDerivative(
                    device, name, "IntrinsicElectrons", electron_expression, "Potential"
                )
                CreateNodeModel(device, name, "IntrinsicHoles", hole_expression)
                CreateNodeModelDerivative(
                    device, name, "IntrinsicHoles", hole_expression, "Potential"
                )
            else:
                CreateNodeModel(device, name, "BandGapNarrowing", "0")
                CreateNodeModel(device, name, "EffectiveIntrinsicDensity", "n_i")
            CreateNodeModel(device, name, "ElectronAffinityEnergy", "ElectronAffinity")
            CreateNodeModel(device, name, "MaterialBandGap", "BandGap")
            CreateNodeModel(
                device,
                name,
                "EffectiveBandGap",
                "BandGap-BandGapNarrowing",
            )
            if fermi_statistics:
                electron_eta = (
                    "(Potential-0.5*EffectiveBandGap-"
                    "0.5*V_t*log(EffectiveDensityConduction/"
                    "EffectiveDensityValence))/V_t"
                )
                hole_eta = (
                    "(-Potential-0.5*EffectiveBandGap+"
                    "0.5*V_t*log(EffectiveDensityConduction/"
                    "EffectiveDensityValence))/V_t"
                )
                intrinsic_electrons = (
                    "(1-FermiBlend)*EffectiveIntrinsicDensity*exp(Potential/V_t)+"
                    f"FermiBlend*EffectiveDensityConduction*Fermi({electron_eta})"
                )
                intrinsic_holes = (
                    "(1-FermiBlend)*EffectiveIntrinsicDensity*exp(-Potential/V_t)+"
                    f"FermiBlend*EffectiveDensityValence*Fermi({hole_eta})"
                )
                CreateNodeModel(
                    device, name, "IntrinsicElectrons", intrinsic_electrons
                )
                CreateNodeModelDerivative(
                    device,
                    name,
                    "IntrinsicElectrons",
                    intrinsic_electrons,
                    "Potential",
                )
                CreateNodeModel(device, name, "IntrinsicHoles", intrinsic_holes)
                CreateNodeModelDerivative(
                    device,
                    name,
                    "IntrinsicHoles",
                    intrinsic_holes,
                    "Potential",
                )
        else:
            SetOxideParameters(device, name, temperature)
            if region["material"] == "generic_dielectric":
                set_parameter(
                    device=device,
                    region=name,
                    name="Permittivity",
                    value=float(region["relative_permittivity"]) * 8.85e-14,
                )
            CreateSolution(device, name, "Potential")
            CreateOxidePotentialOnly(device, name)
            if name in regions_with_fixed_bulk:
                equation(
                    device=device,
                    region=name,
                    name="PotentialEquation",
                    variable_name="Potential",
                    node_model="FixedBulkCharge",
                    edge_model="PotentialEdgeFlux",
                    variable_update="default",
                )

    carrier_contact_targets: dict[str, tuple[float, float]] = {}
    contact_equilibrium_potentials: dict[str, float] = {}
    fermi_contact_potentials: dict[str, float] = {}
    for contact in payload["contacts"]:
        region = _contact_region(payload, contact["location"])
        circuit_driven = is_circuit_study and contact["id"] == study["contact"]
        backend_contact = _backend_contact_id(contact)
        if contact["kind"] == "insulating":
            continue
        if not circuit_driven:
            set_parameter(
                device=device,
                name=GetContactBiasName(backend_contact),
                value=contact_offsets[contact["id"]],
            )
        if region["material"] == "silicon" and contact["kind"] == "ohmic":
            if fermi_statistics:
                region_name = region["id"]
                if not InEdgeModelList(device, region_name, "contactcharge_edge"):
                    CreateEdgeModel(
                        device,
                        region_name,
                        "contactcharge_edge",
                        "Permittivity*ElectricField",
                    )
                    CreateEdgeModelDerivatives(
                        device,
                        region_name,
                        "contactcharge_edge",
                        "Permittivity*ElectricField",
                        "Potential",
                    )
                endpoint = 0 if contact["location"] == "x_min" else -1
                net_doping = float(
                    get_node_model_values(
                        device=device, region=region_name, name="NetDoping"
                    )[endpoint]
                )
                effective_gap = float(
                    get_node_model_values(
                        device=device, region=region_name, name="EffectiveBandGap"
                    )[endpoint]
                )
                electrons, holes, potential = _fermi_contact_state(
                    net_doping_cm3=net_doping,
                    conduction_density_cm3=float(
                        get_parameter(
                            device=device,
                            region=region_name,
                            name="EffectiveDensityConduction",
                        )
                    ),
                    valence_density_cm3=float(
                        get_parameter(
                            device=device,
                            region=region_name,
                            name="EffectiveDensityValence",
                        )
                    ),
                    band_gap_ev=effective_gap,
                    thermal_voltage_v=float(
                        get_parameter(
                            device=device, region=region_name, name="V_t"
                        )
                    ),
                )
                effective_intrinsic = float(
                    get_node_model_values(
                        device=device,
                        region=region_name,
                        name="EffectiveIntrinsicDensity",
                    )[endpoint]
                )
                if net_doping >= 0:
                    boltzmann_electrons = 0.5 * (
                        net_doping
                        + math.sqrt(
                            net_doping * net_doping
                            + 4.0 * effective_intrinsic * effective_intrinsic
                        )
                    )
                else:
                    boltzmann_holes = 0.5 * (
                        -net_doping
                        + math.sqrt(
                            net_doping * net_doping
                            + 4.0 * effective_intrinsic * effective_intrinsic
                        )
                    )
                    boltzmann_electrons = (
                        effective_intrinsic * effective_intrinsic / boltzmann_holes
                    )
                boltzmann_potential = float(
                    get_parameter(device=device, region=region_name, name="V_t")
                ) * math.log(boltzmann_electrons / effective_intrinsic)
                carrier_contact_targets[contact["id"]] = (electrons, holes)
                fermi_contact_potentials[contact["id"]] = potential
                contact_equilibrium_potentials[contact["location"]] = (
                    boltzmann_potential + contact_offsets[contact["id"]]
                )
                model_name = GetContactNodeModelName(backend_contact)
                model = (
                    f"Potential-{GetContactBiasName(backend_contact)}-"
                    f"((1-FermiBlend)*{boltzmann_potential:.17e}+"
                    f"FermiBlend*{potential:.17e})"
                )
                CreateContactNodeModel(
                    device, backend_contact, model_name, model
                )
                CreateContactNodeModel(
                    device,
                    backend_contact,
                    f"{model_name}:Potential",
                    "1",
                )
                if circuit_driven:
                    CreateContactNodeModelDerivative(
                        device,
                        backend_contact,
                        model_name,
                        model,
                        GetContactBiasName(backend_contact),
                    )
                    contact_equation(
                        device=device,
                        contact=backend_contact,
                        name="PotentialEquation",
                        node_model=model_name,
                        edge_charge_model="contactcharge_edge",
                        circuit_node=GetContactBiasName(backend_contact),
                    )
                else:
                    contact_equation(
                        device=device,
                        contact=backend_contact,
                        name="PotentialEquation",
                        node_model=model_name,
                        edge_charge_model="contactcharge_edge",
                    )
            else:
                CreateSiliconPotentialOnlyContact(
                    device,
                    region["id"],
                    backend_contact,
                    is_circuit=circuit_driven,
                )
        elif (
            region["material"] in {"silicon_dioxide", "generic_dielectric"}
            and contact["kind"] in {"ideal_gate", "metal_work_function"}
        ):
            CreateOxideContact(device, region["id"], backend_contact)
            offset = 0.0
            if contact["kind"] == "metal_work_function":
                thermal_voltage = 8.617333262145e-5 * temperature
                intrinsic_work_function = (
                    payload["physics"]["electron_affinity_ev"]
                    + 0.5 * payload["physics"]["band_gap_ev"]
                    + 0.5
                    * thermal_voltage
                    * math.log(
                        payload["physics"]["effective_density_conduction_cm3"]
                        / payload["physics"]["effective_density_valence_cm3"]
                    )
                )
                offset = intrinsic_work_function - contact["work_function_ev"]
            if contact["kind"] == "metal_work_function" or circuit_driven:
                model_name = GetContactNodeModelName(backend_contact)
                model = (
                    f"Potential-{GetContactBiasName(backend_contact)}-"
                    f"{offset:.17g}"
                )
                CreateContactNodeModel(device, backend_contact, model_name, model)
                CreateContactNodeModel(
                    device,
                    backend_contact,
                    f"{model_name}:Potential",
                    "1",
                )
                if circuit_driven:
                    CreateContactNodeModelDerivative(
                        device,
                        backend_contact,
                        model_name,
                        model,
                        GetContactBiasName(backend_contact),
                    )
                    contact_equation(
                        device=device,
                        contact=backend_contact,
                        name="PotentialEquation",
                        node_model=model_name,
                        edge_charge_model="contactcharge_edge",
                        circuit_node=GetContactBiasName(backend_contact),
                    )
        else:
            raise ValueError("contact kind is incompatible with adjacent material")
    if fermi_statistics and {
        "x_min",
        "x_max",
    }.issubset(contact_equilibrium_potentials):
        stack_start = float(regions[0]["x0_cm"])
        stack_stop = float(regions[-1]["x1_cm"])
        start_potential = contact_equilibrium_potentials["x_min"]
        stop_potential = contact_equilibrium_potentials["x_max"]
        for region in regions:
            if region["material"] != "silicon":
                continue
            positions = list(
                get_node_model_values(
                    device=device, region=region["id"], name="x"
                )
            )
            values = [
                start_potential
                + (position - stack_start)
                / (stack_stop - stack_start)
                * (stop_potential - start_potential)
                for position in positions
            ]
            set_node_values(
                device=device,
                region=region["id"],
                name="Potential",
                values=values,
            )
    for interface, _left, _right in interface_names:
        CreateSiliconOxideInterface(device, interface)

    def apply_fixed_interface_charge(*, coupled_transport: bool) -> None:
        for interface, left, _right in interface_names:
            record = next(
                (
                    item
                    for item in payload["interfaces"]
                    if item["id"] == interface
                ),
                None,
            )
            if record is None:
                continue
            sheet_density = record.get("fixed_charge_cm2")
            if sheet_density in {None, 0.0}:
                continue
            region = left["id"]
            boundary = left["x1_cm"]
            tolerance = max(left["mesh_spacing_cm"] * 1e-6, 1e-20)
            interface_mask = (
                f"ifelse(abs(x-{boundary:.17g}) < {tolerance:.17g}, 1, 0)"
            )
            CreateNodeModel(device, region, "FixedInterfaceMask", interface_mask)
            fixed_charge = (
                f"ElectronCharge*{float(sheet_density):.17e}/NodeVolume*"
                "FixedInterfaceMask"
            )
            CreateNodeModel(
                device, region, "FixedInterfaceChargeVolume", fixed_charge
            )
            base: str | None
            if left["material"] == "silicon":
                base = (
                    "PotentialChargeWithBulk"
                    if region in regions_with_fixed_bulk
                    else (
                        "PotentialNodeCharge"
                        if coupled_transport
                        else "PotentialIntrinsicCharge"
                    )
                )
                update = "log_damp"
            else:
                base = (
                    "FixedBulkCharge" if region in regions_with_fixed_bulk else None
                )
                update = "default"
            combined = (
                f"{base}+FixedInterfaceChargeVolume"
                if base is not None
                else "FixedInterfaceChargeVolume"
            )
            CreateNodeModel(device, region, "PotentialChargeWithInterface", combined)
            CreateNodeModelDerivative(
                device,
                region,
                "PotentialChargeWithInterface",
                combined,
                "Potential",
            )
            equation(
                device=device,
                region=region,
                name="PotentialEquation",
                variable_name="Potential",
                node_model="PotentialChargeWithInterface",
                edge_model="PotentialEdgeFlux",
                variable_update=update,
            )

    apply_fixed_interface_charge(coupled_transport=False)
    solver = payload["solver"]
    solve(
        type="dc",
        absolute_error=float(solver["electrostatic_absolute_error"]),
        relative_error=float(solver["relative_error"]),
        maximum_iterations=int(solver["maximum_iterations"]),
    )
    solver_events.append(
        {"phase": "poisson_initialization", "outcome": "converged", "attempt": 1}
    )
    if fermi_statistics:
        for continuation_step in range(1, 50):
            blend = continuation_step / 50.0
            set_parameter(device=device, name="FermiBlend", value=blend)
            solve(
                type="dc",
                absolute_error=float(solver["electrostatic_absolute_error"]),
                relative_error=float(solver["relative_error"]),
                maximum_iterations=int(solver["maximum_iterations"]),
            )
            solver_events.append(
                {
                    "phase": "fermi_statistics_continuation",
                    "outcome": "converged",
                    "attempt": continuation_step,
                    "blend": blend,
                }
            )
        for region in regions:
            if region["material"] != "silicon":
                continue
            name = region["id"]
            electron_eta = (
                "(Potential-0.5*EffectiveBandGap-"
                "0.5*V_t*log(EffectiveDensityConduction/"
                "EffectiveDensityValence))/V_t"
            )
            hole_eta = (
                "(-Potential-0.5*EffectiveBandGap+"
                "0.5*V_t*log(EffectiveDensityConduction/"
                "EffectiveDensityValence))/V_t"
            )
            intrinsic_electrons = (
                f"EffectiveDensityConduction*Fermi({electron_eta})"
            )
            intrinsic_holes = f"EffectiveDensityValence*Fermi({hole_eta})"
            CreateNodeModel(device, name, "IntrinsicElectrons", intrinsic_electrons)
            CreateNodeModelDerivative(
                device,
                name,
                "IntrinsicElectrons",
                intrinsic_electrons,
                "Potential",
            )
            CreateNodeModel(device, name, "IntrinsicHoles", intrinsic_holes)
            CreateNodeModelDerivative(
                device,
                name,
                "IntrinsicHoles",
                intrinsic_holes,
                "Potential",
            )
        for contact in payload["contacts"]:
            if contact["id"] not in fermi_contact_potentials:
                continue
            backend_contact = _backend_contact_id(contact)
            model_name = GetContactNodeModelName(backend_contact)
            model = (
                f"Potential-{GetContactBiasName(backend_contact)}-"
                f"{fermi_contact_potentials[contact['id']]:.17e}"
            )
            CreateContactNodeModel(device, backend_contact, model_name, model)
            CreateContactNodeModel(
                device, backend_contact, f"{model_name}:Potential", "1"
            )
            if is_circuit_study and contact["id"] == study.get("contact"):
                CreateContactNodeModelDerivative(
                    device,
                    backend_contact,
                    model_name,
                    model,
                    GetContactBiasName(backend_contact),
                )
        solve(
            type="dc",
            absolute_error=float(solver["electrostatic_absolute_error"]),
            relative_error=float(solver["relative_error"]),
            maximum_iterations=int(solver["maximum_iterations"]),
        )
        solver_events.append(
            {
                "phase": "fermi_statistics_finalization",
                "outcome": "converged",
                "attempt": 50,
                "blend": 1.0,
            }
        )

    drift_diffusion = {
        "electron_continuity",
        "hole_continuity",
    }.issubset(payload["physics"]["equations"])
    if drift_diffusion:
        for region in regions:
            if region["material"] != "silicon":
                continue
            name = region["id"]
            CreateSolution(device, name, "Electrons")
            CreateSolution(device, name, "Holes")
            set_node_values(
                device=device,
                region=name,
                name="Electrons",
                init_from="IntrinsicElectrons",
            )
            set_node_values(
                device=device,
                region=name,
                name="Holes",
                init_from="IntrinsicHoles",
            )
            electron_mobility_model = "mu_n"
            hole_mobility_model = "mu_p"
            if "klaassen_mobility" in selected_models:
                Set_Mobility_Parameters(device, name)
                Klaassen_Mobility(device, name)
                electron_mobility_model = "mu_bulk_e"
                hole_mobility_model = "mu_bulk_h"
            if "high_field_saturation" in selected_models:
                electron_expression = (
                    f"2*{electron_mobility_model}/"
                    f"(1+pow(1+4*pow({electron_mobility_model}*"
                    "abs(ElectricField)/vsat_e, 2), 0.5))"
                )
                hole_expression = (
                    f"2*{hole_mobility_model}/"
                    f"(1+pow(1+4*pow({hole_mobility_model}*"
                    "abs(ElectricField)/vsat_h, 2), 0.5))"
                )
                CreateEdgeModel(
                    device,
                    name,
                    "HighFieldElectronMobility",
                    electron_expression,
                )
                CreateEdgeModel(
                    device,
                    name,
                    "HighFieldHoleMobility",
                    hole_expression,
                )
                electron_mobility_model = "HighFieldElectronMobility"
                hole_mobility_model = "HighFieldHoleMobility"
            CreateSiliconDriftDiffusion(
                device,
                name,
                electron_mobility_model,
                hole_mobility_model,
            )
            if name in regions_with_fixed_bulk:
                potential_charge_with_bulk = "PotentialNodeCharge+FixedBulkCharge"
                CreateNodeModel(
                    device,
                    name,
                    "PotentialChargeWithBulk",
                    potential_charge_with_bulk,
                )
                CreateNodeModelDerivative(
                    device,
                    name,
                    "PotentialChargeWithBulk",
                    potential_charge_with_bulk,
                    "Potential",
                    "Electrons",
                    "Holes",
                )
                equation(
                    device=device,
                    region=name,
                    name="PotentialEquation",
                    variable_name="Potential",
                    node_model="PotentialChargeWithBulk",
                    edge_model="PotentialEdgeFlux",
                    variable_update="log_damp",
                )
            auger_expression = "0"
            if "auger" in selected_models:
                auger_expression = (
                    "(AugerElectron*Electrons+AugerHole*Holes)*"
                    "(Electrons*Holes-EffectiveIntrinsicDensity^2)"
                )
            CreateNodeModel(device, name, "UAuger", auger_expression)
            CreateNodeModelDerivative(
                device, name, "UAuger", auger_expression, "Electrons", "Holes"
            )
            total_recombination = "USRH+UAuger"
            CreateNodeModel(
                device, name, "TotalRecombination", total_recombination
            )
            CreateNodeModelDerivative(
                device,
                name,
                "TotalRecombination",
                total_recombination,
                "Electrons",
                "Holes",
            )
            CreateNodeModel(device, name, "NetCarrierGeneration", "-TotalRecombination")
            electron_generation = "-ElectronCharge*TotalRecombination"
            hole_generation = "ElectronCharge*TotalRecombination"
            CreateNodeModel(device, name, "ElectronGeneration", electron_generation)
            CreateNodeModelDerivative(
                device,
                name,
                "ElectronGeneration",
                electron_generation,
                "Electrons",
                "Holes",
            )
            CreateNodeModel(device, name, "HoleGeneration", hole_generation)
            CreateNodeModelDerivative(
                device,
                name,
                "HoleGeneration",
                hole_generation,
                "Electrons",
                "Holes",
            )
            intrinsic_energy = "-Potential"
            conduction_band = (
                "IntrinsicEnergy+0.5*(BandGap-BandGapNarrowing)+"
                "0.5*V_t*log(EffectiveDensityConduction/EffectiveDensityValence)"
            )
            valence_band = (
                "IntrinsicEnergy-0.5*(BandGap-BandGapNarrowing)+"
                "0.5*V_t*log(EffectiveDensityConduction/EffectiveDensityValence)"
            )
            CreateNodeModel(device, name, "IntrinsicEnergy", intrinsic_energy)
            CreateNodeModel(device, name, "ConductionBandEnergy", conduction_band)
            CreateNodeModel(device, name, "ValenceBandEnergy", valence_band)
            electron_quasi_fermi = (
                "ConductionBandEnergy+V_t*InvFermi("
                "Electrons/EffectiveDensityConduction)"
                if fermi_statistics
                else (
                    "ConductionBandEnergy+V_t*"
                    "log(Electrons/EffectiveDensityConduction)"
                )
            )
            hole_quasi_fermi = (
                "ValenceBandEnergy-V_t*InvFermi("
                "Holes/EffectiveDensityValence)"
                if fermi_statistics
                else (
                    "ValenceBandEnergy-V_t*"
                    "log(Holes/EffectiveDensityValence)"
                )
            )
            CreateNodeModel(
                device,
                name,
                "ElectronQuasiFermiEnergy",
                electron_quasi_fermi,
            )
            CreateNodeModelDerivative(
                device,
                name,
                "ElectronQuasiFermiEnergy",
                electron_quasi_fermi,
                "Potential",
                "Electrons",
            )
            CreateNodeModel(
                device,
                name,
                "HoleQuasiFermiEnergy",
                hole_quasi_fermi,
            )
            CreateNodeModelDerivative(
                device,
                name,
                "HoleQuasiFermiEnergy",
                hole_quasi_fermi,
                "Potential",
                "Holes",
            )
            CreateNodeModel(
                device,
                name,
                "FermiLevelEnergy",
                "0.5*(ElectronQuasiFermiEnergy+HoleQuasiFermiEnergy)",
            )
            if fermi_statistics:
                edge_from_node_model(
                    device=device, region=name, node_model="BandGapNarrowing"
                )
                electron_energy_n0 = (
                    "(-Potential@n0+0.5*(BandGap-BandGapNarrowing@n0)+"
                    "0.5*V_t*log(EffectiveDensityConduction/"
                    "EffectiveDensityValence)+V_t*InvFermi("
                    "Electrons@n0/EffectiveDensityConduction))"
                )
                electron_energy_n1 = electron_energy_n0.replace("@n0", "@n1")
                hole_energy_n0 = (
                    "(-Potential@n0-0.5*(BandGap-BandGapNarrowing@n0)+"
                    "0.5*V_t*log(EffectiveDensityConduction/"
                    "EffectiveDensityValence)-V_t*InvFermi("
                    "Holes@n0/EffectiveDensityValence))"
                )
                hole_energy_n1 = hole_energy_n0.replace("@n0", "@n1")
                electron_current = (
                    f"ElectronCharge*{electron_mobility_model}*"
                    "0.5*(Electrons@n0+Electrons@n1)*EdgeInverseLength*"
                    f"(({electron_energy_n1})-({electron_energy_n0}))"
                )
                hole_current = (
                    f"ElectronCharge*{hole_mobility_model}*"
                    "0.5*(Holes@n0+Holes@n1)*EdgeInverseLength*"
                    f"(({hole_energy_n1})-({hole_energy_n0}))"
                )
                CreateEdgeModel(device, name, "ElectronCurrent", electron_current)
                for variable in ("Potential", "Electrons", "Holes"):
                    CreateEdgeModelDerivatives(
                        device,
                        name,
                        "ElectronCurrent",
                        electron_current,
                        variable,
                    )
                CreateEdgeModel(device, name, "HoleCurrent", hole_current)
                for variable in ("Potential", "Electrons", "Holes"):
                    CreateEdgeModelDerivatives(
                        device,
                        name,
                        "HoleCurrent",
                        hole_current,
                        variable,
                    )
        for contact in payload["contacts"]:
            if contact["kind"] == "insulating":
                continue
            region = _contact_region(payload, contact["location"])
            if region["material"] == "silicon" and contact["kind"] == "ohmic":
                if fermi_statistics:
                    backend_contact = _backend_contact_id(contact)
                    electrons, holes = carrier_contact_targets[contact["id"]]
                    for variable, equation_name, target in (
                        (
                            "Electrons",
                            "ElectronContinuityEquation",
                            electrons,
                        ),
                        ("Holes", "HoleContinuityEquation", holes),
                    ):
                        model_name = f"{backend_contact}_{variable.lower()}_fermi"
                        model = f"{variable}-{target:.17e}"
                        CreateContactNodeModel(
                            device, backend_contact, model_name, model
                        )
                        CreateContactNodeModel(
                            device,
                            backend_contact,
                            f"{model_name}:{variable}",
                            "1",
                        )
                        options: dict[str, Any] = {
                            "device": device,
                            "contact": backend_contact,
                            "name": equation_name,
                            "node_model": model_name,
                            "edge_current_model": (
                                "ElectronCurrent"
                                if variable == "Electrons"
                                else "HoleCurrent"
                            ),
                        }
                        if is_circuit_study and contact["id"] == study["contact"]:
                            options["circuit_node"] = GetContactBiasName(
                                backend_contact
                            )
                        contact_equation(**options)
                else:
                    CreateSiliconDriftDiffusionAtContact(
                        device,
                        region["id"],
                        _backend_contact_id(contact),
                        is_circuit=(
                            is_circuit_study and contact["id"] == study["contact"]
                        ),
                    )
        for interface, left, right in interface_names:
            if left["material"] == right["material"] == "silicon":
                for variable, equation_name in (
                    ("Electrons", "ElectronContinuityEquation"),
                    ("Holes", "HoleContinuityEquation"),
                ):
                    model = CreateContinuousInterfaceModel(device, interface, variable)
                    interface_equation(
                        device=device,
                        interface=interface,
                        name=equation_name,
                        interface_model=model,
                        type="continuous",
                    )
        apply_fixed_interface_charge(coupled_transport=True)
        solve(
            type="dc",
            absolute_error=float(solver["carrier_absolute_error"]),
            relative_error=float(solver["relative_error"]),
            maximum_iterations=int(solver["maximum_iterations"]),
        )
        solver_events.append(
            {"phase": "coupled_initialization", "outcome": "converged", "attempt": 1}
        )
    if is_transient:
        solve(
            type="transient_dc",
            absolute_error=float(
                solver[
                    "carrier_absolute_error"
                    if drift_diffusion
                    else "electrostatic_absolute_error"
                ]
            ),
            relative_error=float(solver["transient_initial_relative_error"]),
            maximum_iterations=int(solver["maximum_iterations"]),
        )
        solver_events.append(
            {"phase": "transient_initialization", "outcome": "converged", "attempt": 1}
        )

    requested = set(payload["observables"])

    def extract_fields() -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        for region in regions:
            name = region["id"]
            node_positions = list(
                get_node_model_values(device=device, region=name, name="x")
            )
            edge_positions = [
                (left + right) / 2 for left, right in pairwise(node_positions)
            ]
            if "potential" in requested:
                _append_field(
                    fields,
                    "potential",
                    node_positions,
                    list(
                        get_node_model_values(
                            device=device, region=name, name="Potential"
                        )
                    ),
                    "V",
                    "node",
                )
            if "electric_field" in requested:
                _append_field(
                    fields,
                    "electric_field",
                    edge_positions,
                    list(
                        get_edge_model_values(
                            device=device, region=name, name="ElectricField"
                        )
                    ),
                    "V/cm",
                    "edge",
                )
            if "electrostatic_flux" in requested:
                _append_field(
                    fields,
                    "electrostatic_flux",
                    edge_positions,
                    list(
                        get_edge_model_values(
                            device=device, region=name, name="PotentialEdgeFlux"
                        )
                    ),
                    "C/cm^2",
                    "edge",
                )
            if "fixed_charge_density" in requested:
                _append_field(
                    fields,
                    "fixed_charge_density",
                    node_positions,
                    list(
                        get_node_model_values(
                            device=device, region=name, name="FixedBulkCharge"
                        )
                    ),
                    "C/cm^3",
                    "node",
                )
            if region["material"] != "silicon":
                continue
            model_outputs = {
                "electron_density": ("Electrons", "cm^-3", "node"),
                "hole_density": ("Holes", "cm^-3", "node"),
                "recombination_rate": ("TotalRecombination", "cm^-3/s", "node"),
                "srh_recombination_rate": ("USRH", "cm^-3/s", "node"),
                "auger_recombination_rate": ("UAuger", "cm^-3/s", "node"),
                "total_recombination_rate": (
                    "TotalRecombination",
                    "cm^-3/s",
                    "node",
                ),
                "electron_generation_rate": (
                    "NetCarrierGeneration",
                    "cm^-3/s",
                    "node",
                ),
                "hole_generation_rate": (
                    "NetCarrierGeneration",
                    "cm^-3/s",
                    "node",
                ),
                "conduction_band": ("ConductionBandEnergy", "eV", "node"),
                "valence_band": ("ValenceBandEnergy", "eV", "node"),
                "intrinsic_energy": ("IntrinsicEnergy", "eV", "node"),
                "electron_affinity": ("ElectronAffinityEnergy", "eV", "node"),
                "band_gap": ("MaterialBandGap", "eV", "node"),
                "band_gap_narrowing": ("BandGapNarrowing", "eV", "node"),
                "effective_intrinsic_carrier_concentration": (
                    "EffectiveIntrinsicDensity",
                    "cm^-3",
                    "node",
                ),
                "fermi_level": ("FermiLevelEnergy", "eV", "node"),
                "electron_quasi_fermi_level": (
                    "ElectronQuasiFermiEnergy",
                    "eV",
                    "node",
                ),
                "hole_quasi_fermi_level": (
                    "HoleQuasiFermiEnergy",
                    "eV",
                    "node",
                ),
                "electron_current_density": ("ElectronCurrent", "A/cm^2", "edge"),
                "hole_current_density": ("HoleCurrent", "A/cm^2", "edge"),
            }
            for output, (model, unit, centering) in model_outputs.items():
                if output not in requested or not drift_diffusion:
                    continue
                positions = node_positions if centering == "node" else edge_positions
                getter = (
                    get_node_model_values
                    if centering == "node"
                    else get_edge_model_values
                )
                _append_field(
                    fields,
                    output,
                    positions,
                    list(getter(device=device, region=name, name=model)),
                    unit,
                    centering,
                )
            doping = list(
                get_node_model_values(device=device, region=name, name="NetDoping")
            )
            if "net_doping" in requested:
                _append_field(
                    fields, "net_doping", node_positions, doping, "cm^-3", "node"
                )
            for output, native_name in (
                ("donor_concentration", "PhysicalDonors"),
                ("acceptor_concentration", "PhysicalAcceptors"),
            ):
                if output in requested:
                    _append_field(
                        fields,
                        output,
                        node_positions,
                        list(
                            get_node_model_values(
                                device=device, region=name, name=native_name
                            )
                        ),
                        "cm^-3",
                        "node",
                    )
            if drift_diffusion:
                electrons = list(
                    get_node_model_values(
                        device=device, region=name, name="Electrons"
                    )
                )
                holes = list(
                    get_node_model_values(device=device, region=name, name="Holes")
                )
                if "charge_density" in requested:
                    charge = float(
                        get_parameter(
                            device=device, region=name, name="ElectronCharge"
                        )
                    )
                    values = [
                        charge * (p - n + dop)
                        for p, n, dop in zip(holes, electrons, doping, strict=True)
                    ]
                    _append_field(
                        fields,
                        "charge_density",
                        node_positions,
                        values,
                        "C/cm^3",
                        "node",
                    )
                for output, parameter in (
                    ("electron_mobility", "mu_n"),
                    ("hole_mobility", "mu_p"),
                ):
                    if output in requested:
                        if "high_field_saturation" in selected_models:
                            model = (
                                "HighFieldElectronMobility"
                                if output == "electron_mobility"
                                else "HighFieldHoleMobility"
                            )
                            values = list(
                                get_edge_model_values(
                                    device=device, region=name, name=model
                                )
                            )
                            positions = edge_positions
                            centering = "edge"
                        elif "klaassen_mobility" in selected_models:
                            model = (
                                "mu_bulk_e_Node"
                                if output == "electron_mobility"
                                else "mu_bulk_h_Node"
                            )
                            values = list(
                                get_node_model_values(
                                    device=device, region=name, name=model
                                )
                            )
                            positions = node_positions
                            centering = "node"
                        else:
                            mobility = float(
                                get_parameter(
                                    device=device, region=name, name=parameter
                                )
                            )
                            values = [mobility] * len(node_positions)
                            positions = node_positions
                            centering = "node"
                        _append_field(
                            fields,
                            output,
                            positions,
                            values,
                            "cm^2/V/s",
                            centering,
                        )
                if "total_current_density" in requested:
                    electron_current = list(
                        get_edge_model_values(
                            device=device, region=name, name="ElectronCurrent"
                        )
                    )
                    hole_current = list(
                        get_edge_model_values(
                            device=device, region=name, name="HoleCurrent"
                        )
                    )
                    _append_field(
                        fields,
                        "total_current_density",
                        edge_positions,
                        [
                            electron + hole
                            for electron, hole in zip(
                                electron_current, hole_current, strict=True
                            )
                        ],
                        "A/cm^2",
                        "edge",
                    )
        return fields

    requested_contact = (
        None if is_circuit_study else payload["study"].get("contact")
    )
    points: list[dict[str, Any]] = []
    field_samples: list[dict[str, Any]] = []
    current_bias = 0.0
    dc_absolute_error = float(
        solver[
            "carrier_absolute_error"
            if drift_diffusion
            else "electrostatic_absolute_error"
        ]
    )
    for requested_bias in _bias_points(payload["study"]):
        bias = requested_bias
        converged = True
        attempts = 1
        message = None
        if requested_contact is not None:
            assert study_backend_contact is not None
            set_parameter(
                device=device,
                name=GetContactBiasName(study_backend_contact),
                value=bias + contact_offsets[requested_contact],
            )
            try:
                solve(
                    type="dc",
                    absolute_error=dc_absolute_error,
                    relative_error=float(solver["relative_error"]),
                    maximum_iterations=int(solver["maximum_iterations"]),
                )
                solver_events.append(
                    {
                        "phase": "requested_operating_point",
                        "requested_bias_v": requested_bias,
                        "attempted_bias_v": bias,
                        "attempt": attempts,
                        "outcome": "converged",
                    }
                )
            except Exception:
                solver_events.append(
                    {
                        "phase": "requested_operating_point",
                        "requested_bias_v": requested_bias,
                        "attempted_bias_v": bias,
                        "attempt": attempts,
                        "outcome": "failed",
                    }
                )
                converged = False
                study = payload["study"]
                if study.get("strategy") == "adaptive":
                    left = current_bias
                    right = requested_bias
                    for _retry in range(study.get("maximum_retries", 0)):
                        midpoint = left + (right - left) / 2
                        if abs(midpoint - left) < study.get("minimum_step_v", 0.0):
                            break
                        set_parameter(
                            device=device,
                            name=GetContactBiasName(study_backend_contact),
                            value=midpoint + contact_offsets[requested_contact],
                        )
                        try:
                            solve(
                                type="dc",
                                absolute_error=dc_absolute_error,
                                relative_error=float(solver["relative_error"]),
                                maximum_iterations=int(solver["maximum_iterations"]),
                            )
                        except Exception:
                            solver_events.append(
                                {
                                    "phase": "recovery_midpoint",
                                    "requested_bias_v": requested_bias,
                                    "attempted_bias_v": midpoint,
                                    "attempt": attempts + 1,
                                    "outcome": "failed",
                                }
                            )
                            right = midpoint
                            continue
                        solver_events.append(
                            {
                                "phase": "recovery_midpoint",
                                "requested_bias_v": requested_bias,
                                "attempted_bias_v": midpoint,
                                "attempt": attempts + 1,
                                "outcome": "converged",
                            }
                        )
                        left = midpoint
                        set_parameter(
                            device=device,
                            name=GetContactBiasName(study_backend_contact),
                            value=(
                                requested_bias + contact_offsets[requested_contact]
                            ),
                        )
                        attempts += 1
                        try:
                            solve(
                                type="dc",
                                absolute_error=dc_absolute_error,
                                relative_error=float(solver["relative_error"]),
                                maximum_iterations=int(solver["maximum_iterations"]),
                            )
                        except Exception:
                            solver_events.append(
                                {
                                    "phase": "recovery_target_retry",
                                    "requested_bias_v": requested_bias,
                                    "attempted_bias_v": requested_bias,
                                    "attempt": attempts,
                                    "outcome": "failed",
                                }
                            )
                            continue
                        solver_events.append(
                            {
                                "phase": "recovery_target_retry",
                                "requested_bias_v": requested_bias,
                                "attempted_bias_v": requested_bias,
                                "attempt": attempts,
                                "outcome": "converged",
                            }
                        )
                        converged = True
                        break
                if not converged:
                    message = "nonlinear solve did not converge"
                    set_parameter(
                        device=device,
                        name=GetContactBiasName(study_backend_contact),
                        value=current_bias + contact_offsets[requested_contact],
                    )
                    solve(
                        type="dc",
                        absolute_error=dc_absolute_error,
                        relative_error=float(solver["relative_error"]),
                        maximum_iterations=int(solver["maximum_iterations"]),
                    )
        if converged:
            current_bias = requested_bias
        currents: dict[str, float] = {}
        electron_currents: dict[str, float] = {}
        hole_currents: dict[str, float] = {}
        charges: dict[str, float] = {}
        for contact in payload["contacts"]:
            if contact["kind"] == "insulating":
                continue
            region = _contact_region(payload, contact["location"])
            backend_contact = _backend_contact_id(contact)
            current = 0.0
            electron_current = 0.0
            hole_current = 0.0
            if drift_diffusion and region["material"] == "silicon":
                electron_current = get_contact_current(
                    device=device,
                    contact=backend_contact,
                    equation="ElectronContinuityEquation",
                )
                hole_current = get_contact_current(
                    device=device,
                    contact=backend_contact,
                    equation="HoleContinuityEquation",
                )
                current = electron_current + hole_current
            currents[contact["id"]] = current
            electron_currents[contact["id"]] = electron_current
            hole_currents[contact["id"]] = hole_current
            charges[contact["id"]] = get_contact_charge(
                device=device,
                contact=backend_contact,
                equation="PotentialEquation",
            )
        points.append(
            {
                "bias_v": bias,
                "converged": converged,
                "currents_a_per_cm2": currents,
                "electron_currents_a_per_cm2": electron_currents,
                "hole_currents_a_per_cm2": hole_currents,
                "charges_c_per_cm2": charges,
                "attempts": attempts,
                "message": message,
            }
        )
        field_samples.append({"valid": converged, "fields": extract_fields()})

    frequency_points: list[dict[str, float]] = []
    if is_ac:
        amplitude = float(study["amplitude_v"])
        for frequency in study["frequencies_hz"]:
            solve(type="ac", frequency=float(frequency))
            solver_events.append(
                {
                    "phase": "small_signal_ac",
                    "frequency_hz": float(frequency),
                    "attempt": 1,
                    "outcome": "converged",
                }
            )
            source_current_real = float(
                get_circuit_node_value(
                    node=f"{circuit_source_name}.I", solution="ssac_real"
                )
            )
            source_current_imag = float(
                get_circuit_node_value(
                    node=f"{circuit_source_name}.I", solution="ssac_imag"
                )
            )
            admittance_real = -source_current_real / amplitude
            admittance_imag = -source_current_imag / amplitude
            frequency_points.append(
                {
                    "frequency_hz": float(frequency),
                    "current_real_a_per_cm2": -source_current_real,
                    "current_imag_a_per_cm2": -source_current_imag,
                    "admittance_real_s_per_cm2": admittance_real,
                    "admittance_imag_s_per_cm2": admittance_imag,
                    "conductance_s_per_cm2": admittance_real,
                    "capacitance_f_per_cm2": admittance_imag
                    / (2.0 * math.pi * float(frequency)),
                }
            )

    transient_points: list[dict[str, Any]] = []
    transient_field_samples: list[dict[str, Any]] = []
    if is_transient:
        current_time = float(study["start_s"])
        stop_time = float(study["stop_s"])
        step_controller = AdaptiveStepController(
            initial_step=float(study["initial_step_s"]),
            minimum_step=float(study["minimum_step_s"]),
            maximum_step=float(study["maximum_step_s"]),
            maximum_retries=int(study["maximum_retries"]),
        )
        steps = 0
        recovery_exhausted = False
        last_converged_fields = extract_fields()
        while current_time < stop_time and steps < int(study["maximum_steps"]):
            step = step_controller.candidate(stop_time - current_time)
            next_time = current_time + step
            source_voltage = waveform_voltage(study, next_time)
            circuit_alter(
                name=circuit_source_name,
                value=source_voltage + contact_offsets[study["contact"]],
            )
            attempt = step_controller.attempt
            try:
                solve(
                    type="transient_bdf1",
                    absolute_error=float(
                        solver[
                            "carrier_absolute_error"
                            if drift_diffusion
                            else "electrostatic_absolute_error"
                        ]
                    ),
                    relative_error=float(solver["transient_step_relative_error"]),
                    maximum_iterations=int(solver["maximum_iterations"]),
                    tdelta=step,
                    charge_error=1,
                )
            except devsim.error as exc:
                solver_events.append(
                    {
                        "phase": "transient_step",
                        "time_s": next_time,
                        "step_s": step,
                        "attempt": attempt,
                        "outcome": "failed",
                        "message": str(exc),
                    }
                )
                try:
                    step_controller.failed()
                except TransientRecoveryExhausted as recovery_error:
                    transient_points.append(
                        {
                            "coordinate": next_time,
                            "converged": False,
                            "currents_a_per_cm2": {},
                            "electron_currents_a_per_cm2": {},
                            "hole_currents_a_per_cm2": {},
                            "charges_c_per_cm2": {},
                            "attempts": attempt,
                            "message": str(recovery_error),
                        }
                    )
                    transient_field_samples.append(
                        {"valid": False, "fields": last_converged_fields}
                    )
                    recovery_exhausted = True
                    break
                continue
            solver_events.append(
                {
                    "phase": "transient_step",
                    "time_s": next_time,
                    "step_s": step,
                    "attempt": attempt,
                    "outcome": "converged",
                }
            )
            transient_currents: dict[str, float] = {}
            transient_electron_currents: dict[str, float] = {}
            transient_hole_currents: dict[str, float] = {}
            transient_charges: dict[str, float] = {}
            for contact in payload["contacts"]:
                if contact["kind"] == "insulating":
                    continue
                backend_contact = _backend_contact_id(contact)
                if contact["id"] == study["contact"]:
                    current = -float(
                        get_circuit_node_value(
                            node=f"{circuit_source_name}.I", solution="dcop"
                        )
                    )
                    electron_current = 0.0
                    hole_current = 0.0
                else:
                    region = _contact_region(payload, contact["location"])
                    current = 0.0
                    electron_current = 0.0
                    hole_current = 0.0
                    if drift_diffusion and region["material"] == "silicon":
                        electron_current = get_contact_current(
                            device=device,
                            contact=backend_contact,
                            equation="ElectronContinuityEquation",
                        )
                        hole_current = get_contact_current(
                            device=device,
                            contact=backend_contact,
                            equation="HoleContinuityEquation",
                        )
                        current = electron_current + hole_current
                transient_currents[contact["id"]] = current
                transient_electron_currents[contact["id"]] = electron_current
                transient_hole_currents[contact["id"]] = hole_current
                transient_charges[contact["id"]] = get_contact_charge(
                    device=device,
                    contact=backend_contact,
                    equation="PotentialEquation",
                )
            transient_points.append(
                {
                    "coordinate": next_time,
                    "converged": True,
                    "currents_a_per_cm2": transient_currents,
                    "electron_currents_a_per_cm2": transient_electron_currents,
                    "hole_currents_a_per_cm2": transient_hole_currents,
                    "charges_c_per_cm2": transient_charges,
                    "attempts": attempt,
                    "message": None,
                }
            )
            last_converged_fields = extract_fields()
            transient_field_samples.append(
                {"valid": True, "fields": last_converged_fields}
            )
            current_time = next_time
            step_controller.succeeded()
            steps += 1
        if current_time < stop_time and not recovery_exhausted:
            raise RuntimeError("transient study exhausted maximum_steps")

    fields = extract_fields()
    field_sweeps: dict[str, dict[str, Any]] = {}
    for name, field in fields.items():
        values: list[float] = []
        validity: list[bool] = []
        for sample in field_samples:
            sampled_field = sample["fields"].get(name)
            if (
                sampled_field is None
                or sampled_field["positions_cm"] != field["positions_cm"]
                or len(sampled_field["values"]) != len(field["values"])
            ):
                raise ValueError(f"field topology changed during study: {name}")
            values.extend(sampled_field["values"])
            validity.extend([bool(sample["valid"])] * len(sampled_field["values"]))
        field_sweeps[name] = {
            "positions_cm": field["positions_cm"],
            "values": values,
            "validity": validity,
            "unit": field["unit"],
            "centering": field["centering"],
        }

    transient_field_sweeps: dict[str, dict[str, Any]] = {}
    if is_transient:
        fields = transient_field_samples[-1]["fields"]
        for name, field in fields.items():
            transient_values: list[float] = []
            transient_validity: list[bool] = []
            for sample in transient_field_samples:
                sampled = sample["fields"][name]
                if sampled["positions_cm"] != field["positions_cm"]:
                    raise ValueError(
                        f"field topology changed during transient study: {name}"
                    )
                transient_values.extend(sampled["values"])
                transient_validity.extend([True] * len(sampled["values"]))
            transient_field_sweeps[name] = {
                "positions_cm": field["positions_cm"],
                "values": transient_values,
                "validity": transient_validity,
                "unit": field["unit"],
                "centering": field["centering"],
            }

    result = {
        "schema_version": "2.0",
        "simulator_version": devsim.__version__,
        "status": "completed",
        "terminals": [
            contact["id"]
            for contact in payload["contacts"]
            if contact["kind"] != "insulating"
        ],
        "contact_areas_m2": {
            contact["id"]: contact.get("area_m2")
            for contact in payload["contacts"]
            if contact["kind"] != "insulating" and contact.get("area_m2") is not None
        },
        "interface_charge_densities_c_per_cm2": {
            interface["id"]: 1.602176634e-19
            * float(interface.get("fixed_charge_cm2") or 0.0)
            for interface in payload["interfaces"]
        },
        "requested_observables": payload["observables"],
        "sign_convention": payload["sign_convention"],
        "parameter_set_id": payload["physics"]["parameter_set_id"],
        "parameter_sources": payload["physics"].get("parameter_sources", {}),
        "solver_configuration": payload["solver"],
        "solver_events": solver_events,
        "native_model_names": {
            name: NATIVE_MODEL_NAMES[name]
            for name in payload["observables"]
            if name in NATIVE_MODEL_NAMES
        },
        "regions": [
            {
                "id": region["id"],
                "material": region["material"],
                "x0_cm": region["x0_cm"],
                "x1_cm": region["x1_cm"],
                "mesh_spacing_cm": region["mesh_spacing_cm"],
            }
            for region in regions
        ],
        "interfaces": [
            {
                "id": interface["id"],
                "left_region": interface["left_region"],
                "right_region": interface["right_region"],
            }
            for interface in payload["interfaces"]
        ],
        "bias_points": points,
        "fields": fields,
        "field_sweeps": field_sweeps,
        "frequency_points": frequency_points,
        "ac_contact": study.get("contact") if is_ac else None,
        "study_axis": (
            {
                "id": "time",
                "kind": "time",
                "label": "Time",
                "unit": "s",
                "values": [point["coordinate"] for point in transient_points],
            }
            if is_transient
            else None
        ),
        "study_points": transient_points,
        "study_field_sweeps": transient_field_sweeps,
    }
    Path("native_result.json").write_text(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
