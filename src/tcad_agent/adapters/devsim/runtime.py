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


def _initial_dc_bias(
    current: float, target: float, temperature: float, study: dict[str, Any]
) -> float:
    """Avoid a doomed full Newton jump when adaptive continuation is requested."""
    if study.get("strategy") != "adaptive":
        return target
    step = max(4 * 8.617333262145e-5 * temperature, study.get("minimum_step_v", 0.0))
    if abs(target - current) <= step:
        return target
    return current + math.copysign(step, target - current)


def configure_numerical_precision(backend: Any, solver: dict[str, Any]) -> dict[str, Any]:
    """Select arithmetic before creating models; unsupported requests fail closed."""
    resolved = solver["precision"]
    requested = solver.get("requested_precision", resolved)
    if resolved not in {"standard", "extended"}:
        raise ValueError(f"unsupported numerical precision: {resolved}")
    info = backend.get_parameter(name="info")
    supported = info.get("extended_precision") is True
    extended = resolved == "extended"
    if extended and not supported:
        raise RuntimeError("requested extended precision is unavailable in this DEVSIM build")
    native_parameters = {}
    for name in ("extended_model", "extended_equation", "extended_solver"):
        backend.set_parameter(name=name, value=extended)
        effective = backend.get_parameter(name=name)
        if effective != extended:
            raise RuntimeError(f"DEVSIM did not enable requested numerical precision: {name}")
        native_parameters[name] = effective
    return {
        "requested": requested,
        "resolved": resolved,
        "effective": resolved,
        "policy_version": "novatom.devsim.precision.2026-10-13.v1",
        "extended_precision_available": supported,
        "native_parameters": native_parameters,
        "backend_build_info": info,
    }


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
    return (
        math.sqrt((0.75 * math.sqrt(math.pi) * ratio) ** (4.0 / 3.0) - math.pi**2 / 6.0)
        - 0.0137050034663995
    )


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


def _fermi_one_models(prefix: str, eta_expression: str) -> dict[str, str]:
    """Native order-one supply and smooth derivative; no Python callbacks.

    DLMF25.12 dilogarithm identities transform to z<=1/2. The96-term
    positive series tail is bounded by2^-96/97^2 (<1.4e-33). Keep its
    rational coefficients in the native expression evaluator. The analytic
    F0 derivative avoids a spurious kink from abs(eta) at eta=0.
    """
    eta = f"{prefix}_eta"
    x = f"{prefix}_x"
    z = f"{prefix}_z"
    logarithm = f"{prefix}_log"
    negative = f"{prefix}_negative"
    models = {
        eta: eta_expression,
        x: f"exp(-abs({eta}))",
        z: f"{x}/(1+{x})",
    }
    # Bound expression nesting to the native parser's stack rather than
    # reducing the series accuracy. Each model continues the same Horner sum.
    for label, power, count in (("log", 1, 112), ("li2", 2, 96)):
        previous = "0"
        for block, upper in enumerate(range(count, 0, -8)):
            poly = previous
            for index in range(upper, upper - 8, -1):
                poly = f"1/{index**power}+{z}*({poly})"
            previous = f"{prefix}_{label}_poly_{block}"
            models[previous] = poly
        # -log(1-z)=log(1+x), but the series also resolves exp(-500)
        # without rounding1+x to1, even in extended native arithmetic.
        models[f"{prefix}_{label}"] = f"{z}*{previous}"
    models.update(
        {
            negative: f"{prefix}_li2+0.5*{logarithm}^2",
            f"{prefix}_supply": (
                f"ifelse({eta}>0,0.5*{eta}^2+"
                f"1.6449340668482264364724151666460252-{negative},{negative})"
            ),
            f"{prefix}_derivative": f"ifelse({eta}>0,{eta}+{logarithm},{logarithm})",
        }
    )
    return models


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
    contact = next(item for item in payload["contacts"] if item["id"] == contact_id)
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
                segment = f"{y0:.17e}+(x-{x0:.17e})*{((y1 - y0) / (x1 - x0)):.17e}"
            expression = f"ifelse(x < {boundary:.17e}, {segment}, {expression})"
        return expression
    if kind == "piecewise_constant":
        boundaries = profile["boundaries_cm"]
        values = profile["values_cm3"]
        expression = f"{values[-1]:.17e}"
        for index in range(len(values) - 2, -1, -1):
            expression = (
                f"ifelse(x < {boundaries[index + 1]:.17e}, {values[index]:.17e}, {expression})"
            )
        return expression
    raise ValueError(f"unsupported profile kind: {kind}")


def _sum_expressions(expressions: list[str]) -> str:
    return "+".join(f"({expression})" for expression in expressions) or "0"


def _temperature_expression(profile: dict[str, Any], region: dict[str, Any]) -> str:
    if profile["kind"] == "constant":
        return f"{float(profile['value_k']):.17e}"
    if profile["kind"] == "linear":
        width = float(region["x1_cm"]) - float(region["x0_cm"])
        delta = float(profile["end_k"]) - float(profile["start_k"])
        return (
            f"{float(profile['start_k']):.17e}+"
            f"((x-{float(region['x0_cm']):.17e})/{width:.17e})*{delta:.17e}"
        )
    if profile["kind"] == "piecewise_constant":
        boundaries = profile["boundaries_cm"]
        values = profile["values_k"]
        expression = f"{float(values[-1]):.17e}"
        for index in range(len(values) - 2, -1, -1):
            expression = (
                f"ifelse(x < {float(boundaries[index + 1]):.17e}, "
                f"{float(values[index]):.17e}, {expression})"
            )
        return expression
    positions = profile["positions_cm"]
    values = profile["values_k"]
    expression = f"{float(values[-1]):.17e}"
    for index in range(len(positions) - 2, -1, -1):
        x0, x1 = float(positions[index]), float(positions[index + 1])
        y0, y1 = float(values[index]), float(values[index + 1])
        segment = f"{y0:.17e}+(x-{x0:.17e})*{((y1 - y0) / (x1 - x0)):.17e}"
        expression = f"ifelse(x < {x1:.17e}, {segment}, {expression})"
    return expression


def _contact_region(payload: dict[str, Any], location: str) -> dict[str, Any]:
    return cast(dict[str, Any], payload["regions"][0 if location == "x_min" else -1])


def _interface_name(payload: dict[str, Any], left_region: str, right_region: str) -> str:
    for interface in payload["interfaces"]:
        if interface["left_region"] == left_region and interface["right_region"] == right_region:
            return str(interface["id"])
    return f"interface__{left_region}__{right_region}"


def _bias_points(study: dict[str, Any]) -> list[float]:
    if study["kind"] == "equilibrium":
        return [0.0]
    if study["kind"] in {"dc", "dc_points"}:
        return [float(value) for value in study["biases_v"]]
    if study["kind"] in {"ac", "frequency"}:
        return [float(value) for value in study.get("biases_v", [0.0])]
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
                    f"{axis_label} point {value:g} {axis_unit} failed: {completed.stderr}"
                )
            child_results.append(json.loads((point_path / "native_result.json").read_text()))

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
                "electron_currents_a_per_cm2": point.get("electron_currents_a_per_cm2", {}),
                "hole_currents_a_per_cm2": point.get("hole_currents_a_per_cm2", {}),
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
            target["validity"].extend([bool(point["converged"])] * len(field["values"]))
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
        "numerical_precision": reference.get("numerical_precision", {}),
        "solver_events": solver_events,
        "native_model_names": reference.get("native_model_names", {}),
        "regions": reference.get("regions", []),
        "interfaces": reference.get("interfaces", []),
    }
    Path("native_result.json").write_text(json.dumps(combined, sort_keys=True, indent=2))
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
        delete_contact_equation,
        delete_equation,
        delete_interface_equation,
        edge_from_node_model,
        equation,
        finalize_mesh,
        get_circuit_node_value,
        get_contact_charge,
        get_contact_current,
        get_contact_equation_command,
        get_contact_equation_list,
        get_edge_model_values,
        get_equation_command,
        get_equation_list,
        get_interface_equation_command,
        get_interface_equation_list,
        get_node_model_values,
        get_parameter,
        interface_equation,
        node_solution,
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
        CreateInterfaceModel,
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
    numerical_precision = configure_numerical_precision(devsim, payload["solver"])
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
            if interface_record is not None and interface_record.get("mesh_spacing_cm") is not None:
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
    temperature_profiles = {
        profile["region"]: profile for profile in payload["physics"].get("temperature_profiles", [])
    }
    fermi_statistics = "fermi" in selected_models
    if fermi_statistics:
        set_parameter(device=device, name="FermiBlend", value=0.0)
    by_region: dict[str, list[dict[str, Any]]] = {region["id"]: [] for region in regions}
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
            band_gap = 1.17 - 4.73e-4 * temperature * temperature / (temperature + 636.0)
            density_scale = (temperature / 300.0) ** 1.5
            conduction_density = (
                payload["physics"]["effective_density_conduction_cm3"] * density_scale
            )
            valence_density = payload["physics"]["effective_density_valence_cm3"] * density_scale
            intrinsic_density = math.sqrt(conduction_density * valence_density) * math.exp(
                -band_gap / (2.0 * thermal_voltage)
            )
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
            temperature_profile = temperature_profiles.get(name)
            if temperature_profile is not None:
                local_temperature = _temperature_expression(temperature_profile, region)
                CreateNodeModel(device, name, "LatticeTemperature", local_temperature)
                local_band_gap = "1.17-4.73e-4*LatticeTemperature^2/(LatticeTemperature+636)"
                local_nc = (
                    f"{float(payload['physics']['effective_density_conduction_cm3']):.17e}*"
                    "pow(LatticeTemperature/300, 1.5)"
                )
                local_nv = (
                    f"{float(payload['physics']['effective_density_valence_cm3']):.17e}*"
                    "pow(LatticeTemperature/300, 1.5)"
                )
                for local_name, expression in (
                    ("V_t", "8.617333262145e-5*LatticeTemperature"),
                    ("BandGap", local_band_gap),
                    ("EffectiveDensityConduction", local_nc),
                    ("EffectiveDensityValence", local_nv),
                    (
                        "n_i",
                        "pow(EffectiveDensityConduction*EffectiveDensityValence,0.5)*"
                        "exp(-BandGap/(2*V_t))",
                    ),
                    ("n1", "n_i"),
                    ("p1", "n_i"),
                    ("mu_n", "400*pow(LatticeTemperature/300, -2.42)"),
                    ("mu_p", "200*pow(LatticeTemperature/300, -2.20)"),
                ):
                    CreateNodeModel(device, name, local_name, expression)
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
            CreateNodeModel(device, name, "PhysicalDonors", _sum_expressions(donors))
            CreateNodeModel(device, name, "PhysicalAcceptors", _sum_expressions(acceptors))
            if "klaassen_mobility" in selected_models:
                # The reviewed DEVSIM Klaassen implementation divides by each
                # dopant species. A 1 cm^-3 computational floor is used only
                # inside the mobility model; electrostatics and reported dopant
                # fields retain the exact researcher-defined concentrations.
                CreateNodeModel(device, name, "Donors", "max(PhysicalDonors, 1)")
                CreateNodeModel(device, name, "Acceptors", "max(PhysicalAcceptors, 1)")
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
                bgn = f"BGNReferenceEnergy*({logarithm}+pow(({logarithm})^2+0.5, 0.5))"
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
                    get_node_model_values(device=device, region=region_name, name="NetDoping")[
                        endpoint
                    ]
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
                        get_parameter(device=device, region=region_name, name="V_t")
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
                if "slotboom_bgn" in selected_models:
                    majority_n = (
                        "0.5*(NetDoping+pow(NetDoping^2+4*EffectiveIntrinsicDensity^2,0.5))"
                    )
                    majority_p = (
                        "0.5*(-NetDoping+pow(NetDoping^2+4*EffectiveIntrinsicDensity^2,0.5))"
                    )
                    model_name = GetContactNodeModelName(backend_contact)
                    model = (
                        f"Potential-{GetContactBiasName(backend_contact)}+"
                        f"ifelse(NetDoping>0,-V_t*log(({majority_n})/EffectiveIntrinsicDensity),"
                        f"V_t*log(({majority_p})/EffectiveIntrinsicDensity))"
                    )
                    CreateContactNodeModel(device, backend_contact, model_name, model)
        elif region["material"] == "silicon" and contact["kind"] == "metal_work_function":
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
            thermal_voltage = float(get_parameter(device=device, region=region_name, name="V_t"))
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
            model_name = GetContactNodeModelName(backend_contact)
            model = f"Potential-{GetContactBiasName(backend_contact)}-{offset:.17g}"
            if contact["kind"] == "metal_work_function":
                # Pin Ec-EFm to Phi_m-chi using the same local effective gap
                # and DOS as the carrier population model, including BGN/T.
                model = (
                    f"Potential-{GetContactBiasName(backend_contact)}-(ElectronAffinity+"
                    "0.5*EffectiveBandGap+0.5*V_t*log(EffectiveDensityConduction/"
                    f"EffectiveDensityValence)-{contact['work_function_ev']:.17g})"
                )
                endpoint = 0 if contact["location"] == "x_min" else -1
                effective_gap = get_node_model_values(
                    device=device, region=region_name, name="EffectiveBandGap"
                )[endpoint]
                offset = (
                    float(payload["physics"]["electron_affinity_ev"])
                    + 0.5 * effective_gap
                    + 0.5
                    * thermal_voltage
                    * math.log(
                        get_parameter(
                            device=device, region=region_name, name="EffectiveDensityConduction"
                        )
                        / get_parameter(
                            device=device, region=region_name, name="EffectiveDensityValence"
                        )
                    )
                    - contact["work_function_ev"]
                )
                contact_equilibrium_potentials[contact["location"]] = (
                    offset + contact_offsets[contact["id"]]
                )
            CreateContactNodeModel(device, backend_contact, model_name, model)
            CreateContactNodeModel(device, backend_contact, f"{model_name}:Potential", "1")
            if circuit_driven:
                CreateContactNodeModelDerivative(
                    device,
                    backend_contact,
                    model_name,
                    model,
                    GetContactBiasName(backend_contact),
                )
            potential_options: dict[str, Any] = {
                "device": device,
                "contact": backend_contact,
                "name": "PotentialEquation",
                "node_model": model_name,
                "edge_charge_model": "contactcharge_edge",
            }
            if circuit_driven:
                potential_options["circuit_node"] = GetContactBiasName(backend_contact)
            contact_equation(**potential_options)
        elif region["material"] in {"silicon_dioxide", "generic_dielectric"} and contact[
            "kind"
        ] in {"ideal_gate", "metal_work_function"}:
            CreateOxideContact(device, region["id"], backend_contact)
            offset = 0.0
            if contact.get("work_function_ev") is not None:
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
            if contact.get("work_function_ev") is not None or circuit_driven:
                model_name = GetContactNodeModelName(backend_contact)
                model = f"Potential-{GetContactBiasName(backend_contact)}-{offset:.17g}"
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
            positions = list(get_node_model_values(device=device, region=region["id"], name="x"))
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
        extra_by_region: dict[str, list[str]] = {}
        for interface, left, right in interface_names:
            record = next(
                (item for item in payload["interfaces"] if item["id"] == interface),
                None,
            )
            if record is None:
                continue
            region = left["id"]
            boundary = left["x1_cm"]
            tolerance = max(left["mesh_spacing_cm"] * 1e-6, 1e-20)
            interface_mask = f"ifelse(abs(x-{boundary:.17g}) < {tolerance:.17g}, 1, 0)"
            mask_name = f"InterfaceMask_{interface}"
            CreateNodeModel(device, region, mask_name, interface_mask)
            sheet_density = record.get("fixed_charge_cm2")
            if sheet_density not in {None, 0.0}:
                fixed_name = f"FixedInterfaceChargeVolume_{interface}"
                fixed_charge = f"ElectronCharge*{float(sheet_density):.17e}/NodeVolume*{mask_name}"
                CreateNodeModel(device, region, fixed_name, fixed_charge)
                extra_by_region.setdefault(region, []).append(fixed_name)
            trap_name = f"InterfaceTrapChargeVolume_{interface}"
            if coupled_transport and record.get("trap_density_cm2") is not None:
                silicon = left if left["material"] == "silicon" else right
                extra_by_region.setdefault(silicon["id"], []).append(trap_name)
        for region, extra_models in extra_by_region.items():
            left = next(item for item in regions if item["id"] == region)
            base: str | None
            if left["material"] == "silicon":
                base = (
                    "PotentialChargeWithBulk"
                    if region in regions_with_fixed_bulk
                    else (
                        "PotentialNodeCharge" if coupled_transport else "PotentialIntrinsicCharge"
                    )
                )
                update = "log_damp"
            else:
                base = "FixedBulkCharge" if region in regions_with_fixed_bulk else None
                update = "default"
            combined = (
                "+".join((base, *extra_models)) if base is not None else "+".join(extra_models)
            )
            CreateNodeModel(device, region, "PotentialChargeWithInterface", combined)
            CreateNodeModelDerivative(
                device,
                region,
                "PotentialChargeWithInterface",
                combined,
                "Potential",
                *(("Electrons", "Holes") if coupled_transport else ()),
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
    solver_events.append({"phase": "poisson_initialization", "outcome": "converged", "attempt": 1})
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
            intrinsic_electrons = f"EffectiveDensityConduction*Fermi({electron_eta})"
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
            CreateContactNodeModel(device, backend_contact, f"{model_name}:Potential", "1")
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
    electrostatic_equations = {
        region["id"]: get_equation_command(
            device=device, region=region["id"], name="PotentialEquation"
        )
        for region in regions
    }
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
            thermal_voltage_edge_model = "V_t"
            if name in temperature_profiles:
                for local_model in ("V_t", "mu_n", "mu_p"):
                    edge_from_node_model(device=device, region=name, node_model=local_model)
                CreateEdgeModel(
                    device,
                    name,
                    "LocalThermalVoltage",
                    "0.5*(V_t@n0+V_t@n1)",
                )
                CreateEdgeModel(
                    device,
                    name,
                    "LocalElectronMobility",
                    "0.5*(mu_n@n0+mu_n@n1)",
                )
                CreateEdgeModel(
                    device,
                    name,
                    "LocalHoleMobility",
                    "0.5*(mu_p@n0+mu_p@n1)",
                )
                thermal_voltage_edge_model = "LocalThermalVoltage"
                electron_mobility_model = "LocalElectronMobility"
                hole_mobility_model = "LocalHoleMobility"
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
            # Use the same statistics and effective gap in transport and
            # recombination. Classical n*p-ni^2 violates detailed balance
            # for degenerate populations, including unbiased metal contacts.
            if fermi_statistics:
                recombination_models = {
                    "CarrierAffinity": (
                        "InvFermi(Electrons/EffectiveDensityConduction)+"
                        "InvFermi(Holes/EffectiveDensityValence)+EffectiveBandGap/V_t"
                    ),
                    "ElectronDegeneracy": (
                        "exp(log(Electrons/EffectiveDensityConduction)-"
                        "InvFermi(Electrons/EffectiveDensityConduction))"
                    ),
                    "HoleDegeneracy": (
                        "exp(log(Holes/EffectiveDensityValence)-"
                        "InvFermi(Holes/EffectiveDensityValence))"
                    ),
                    "RecombinationDriving": ("Electrons*Holes*CarrierAffinity/B(-CarrierAffinity)"),
                }
            else:
                recombination_models = {
                    "ElectronDegeneracy": "1",
                    "HoleDegeneracy": "1",
                    "RecombinationDriving": "Electrons*Holes-EffectiveIntrinsicDensity^2",
                }
            for model_id, expression in recombination_models.items():
                CreateNodeModel(device, name, model_id, expression)
                CreateNodeModelDerivative(device, name, model_id, expression, "Electrons", "Holes")
            srh = (
                "RecombinationDriving/(taup*(Electrons+ElectronDegeneracy*"
                "EffectiveIntrinsicDensity)+taun*(Holes+HoleDegeneracy*EffectiveIntrinsicDensity))"
                if "srh" in selected_models
                else "0"
            )
            CreateNodeModel(device, name, "USRH", srh)
            CreateNodeModelDerivative(device, name, "USRH", srh, "Electrons", "Holes")
            if name in temperature_profiles:
                local_vdiff = "(Potential@n0-Potential@n1)/LocalThermalVoltage"
                CreateEdgeModel(device, name, "vdiff", local_vdiff)
                CreateEdgeModelDerivatives(device, name, "vdiff", local_vdiff, "Potential")
                local_bernoulli = "B(vdiff)"
                CreateEdgeModel(device, name, "Bern01", local_bernoulli)
                CreateEdgeModelDerivatives(device, name, "Bern01", local_bernoulli, "Potential")
                local_electron_current = (
                    "ElectronCharge*LocalElectronMobility*EdgeInverseLength*"
                    "LocalThermalVoltage*kahan3(Electrons@n1*Bern01,"
                    "Electrons@n1*vdiff,-Electrons@n0*Bern01)"
                )
                local_hole_current = (
                    "-ElectronCharge*LocalHoleMobility*EdgeInverseLength*"
                    "LocalThermalVoltage*kahan3(Holes@n1*Bern01,"
                    "-Holes@n0*Bern01,-Holes@n0*vdiff)"
                )
                CreateEdgeModel(device, name, "ElectronCurrent", local_electron_current)
                for variable in ("Potential", "Electrons", "Holes"):
                    CreateEdgeModelDerivatives(
                        device,
                        name,
                        "ElectronCurrent",
                        local_electron_current,
                        variable,
                    )
                CreateEdgeModel(device, name, "HoleCurrent", local_hole_current)
                for variable in ("Potential", "Electrons", "Holes"):
                    CreateEdgeModelDerivatives(
                        device,
                        name,
                        "HoleCurrent",
                        local_hole_current,
                        variable,
                    )
            surface_volume_models: list[str] = []
            for interface_name, left, right in interface_names:
                record = next(
                    (item for item in payload["interfaces"] if item["id"] == interface_name),
                    None,
                )
                if record is None:
                    continue
                if (
                    record.get("surface_electron_velocity_cm_s") is None
                    and record.get("trap_density_cm2") is None
                ):
                    continue
                silicon = left if left["material"] == "silicon" else right
                if silicon["id"] != name:
                    continue
                boundary = silicon["x1_cm"] if silicon is left else silicon["x0_cm"]
                tolerance = max(float(silicon["mesh_spacing_cm"]) * 1e-6, 1e-20)
                mask_name = f"SurfaceMask_{interface_name}"
                CreateNodeModel(
                    device,
                    name,
                    mask_name,
                    f"ifelse(abs(x-{float(boundary):.17g}) < {tolerance:.17g}, 1, 0)",
                )
                trap_energy = float(record.get("trap_energy_ev") or 0.0)
                electron_capture = float(record.get("surface_electron_velocity_cm_s") or 1.0)
                hole_capture = float(record.get("surface_hole_velocity_cm_s") or 1.0)
                electron_trap_density = (
                    f"ElectronDegeneracy*EffectiveIntrinsicDensity*exp({trap_energy:.17e}/V_t)"
                )
                hole_trap_density = (
                    f"HoleDegeneracy*EffectiveIntrinsicDensity*exp(-{trap_energy:.17e}/V_t)"
                )
                denominator = (
                    f"(Electrons+({electron_trap_density}))/{hole_capture:.17e}+"
                    f"(Holes+({hole_trap_density}))/{electron_capture:.17e}"
                )
                sheet_name = f"SurfaceRecombinationSheet_{interface_name}"
                sheet_expression = f"RecombinationDriving/({denominator})"
                CreateNodeModel(device, name, sheet_name, sheet_expression)
                CreateNodeModelDerivative(
                    device,
                    name,
                    sheet_name,
                    sheet_expression,
                    "Electrons",
                    "Holes",
                )
                volume_name = f"SurfaceRecombinationVolume_{interface_name}"
                volume_expression = f"{sheet_name}*{mask_name}/NodeVolume"
                CreateNodeModel(device, name, volume_name, volume_expression)
                CreateNodeModelDerivative(
                    device,
                    name,
                    volume_name,
                    volume_expression,
                    "Electrons",
                    "Holes",
                )
                if record.get("surface_electron_velocity_cm_s") is not None:
                    surface_volume_models.append(volume_name)
                if record.get("trap_density_cm2") is not None:
                    occupancy_name = f"InterfaceTrapOccupancy_{interface_name}"
                    occupancy = (
                        f"({electron_capture:.17e}*Electrons+"
                        f"{hole_capture:.17e}*({hole_trap_density}))/"
                        f"({electron_capture:.17e}*(Electrons+({electron_trap_density}))+"
                        f"{hole_capture:.17e}*(Holes+({hole_trap_density})))"
                    )
                    CreateNodeModel(device, name, occupancy_name, occupancy)
                    CreateNodeModelDerivative(
                        device,
                        name,
                        occupancy_name,
                        occupancy,
                        "Electrons",
                        "Holes",
                    )
                    sheet_charge_name = f"InterfaceTrapChargeSheet_{interface_name}"
                    density = float(record["trap_density_cm2"])
                    charge_state = (
                        f"-{occupancy_name}"
                        if record["trap_type"] == "acceptor"
                        else f"(1-{occupancy_name})"
                    )
                    sheet_charge = f"ElectronCharge*{density:.17e}*{charge_state}"
                    CreateNodeModel(device, name, sheet_charge_name, sheet_charge)
                    CreateNodeModelDerivative(
                        device,
                        name,
                        sheet_charge_name,
                        sheet_charge,
                        "Electrons",
                        "Holes",
                    )
                    trap_volume_name = f"InterfaceTrapChargeVolume_{interface_name}"
                    trap_volume = f"{sheet_charge_name}*{mask_name}/NodeVolume"
                    CreateNodeModel(device, name, trap_volume_name, trap_volume)
                    CreateNodeModelDerivative(
                        device,
                        name,
                        trap_volume_name,
                        trap_volume,
                        "Electrons",
                        "Holes",
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
                auger_expression = "(AugerElectron*Electrons+AugerHole*Holes)*RecombinationDriving"
            CreateNodeModel(device, name, "UAuger", auger_expression)
            CreateNodeModelDerivative(
                device, name, "UAuger", auger_expression, "Electrons", "Holes"
            )
            total_recombination = "+".join(("USRH", "UAuger", *surface_volume_models))
            CreateNodeModel(device, name, "TotalRecombination", total_recombination)
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
            CreateNodeModelDerivative(
                device, name, "IntrinsicEnergy", intrinsic_energy, "Potential"
            )
            CreateNodeModel(device, name, "ConductionBandEnergy", conduction_band)
            CreateNodeModelDerivative(
                device, name, "ConductionBandEnergy", conduction_band, "Potential"
            )
            CreateNodeModel(device, name, "ValenceBandEnergy", valence_band)
            CreateNodeModelDerivative(device, name, "ValenceBandEnergy", valence_band, "Potential")
            electron_quasi_fermi = (
                "ConductionBandEnergy+V_t*InvFermi(Electrons/EffectiveDensityConduction)"
                if fermi_statistics
                else ("ConductionBandEnergy+V_t*log(Electrons/EffectiveDensityConduction)")
            )
            hole_quasi_fermi = (
                "ValenceBandEnergy-V_t*InvFermi(Holes/EffectiveDensityValence)"
                if fermi_statistics
                else ("ValenceBandEnergy-V_t*log(Holes/EffectiveDensityValence)")
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
                "Holes",
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
                "Electrons",
            )
            CreateNodeModel(
                device,
                name,
                "FermiLevelEnergy",
                "0.5*(ElectronQuasiFermiEnergy+HoleQuasiFermiEnergy)",
            )
            if fermi_statistics:
                edge_from_node_model(device=device, region=name, node_model="BandGapNarrowing")
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
                electron_current_expression = (
                    f"ElectronCharge*{electron_mobility_model}*"
                    "0.5*(Electrons@n0+Electrons@n1)*EdgeInverseLength*"
                    f"(({electron_energy_n1})-({electron_energy_n0}))"
                )
                hole_current_expression = (
                    f"ElectronCharge*{hole_mobility_model}*"
                    "0.5*(Holes@n0+Holes@n1)*EdgeInverseLength*"
                    f"(({hole_energy_n1})-({hole_energy_n0}))"
                )
                CreateEdgeModel(device, name, "ElectronCurrent", electron_current_expression)
                for variable in ("Potential", "Electrons", "Holes"):
                    CreateEdgeModelDerivatives(
                        device,
                        name,
                        "ElectronCurrent",
                        electron_current_expression,
                        variable,
                    )
                CreateEdgeModel(device, name, "HoleCurrent", hole_current_expression)
                for variable in ("Potential", "Electrons", "Holes"):
                    CreateEdgeModelDerivatives(
                        device,
                        name,
                        "HoleCurrent",
                        hole_current_expression,
                        variable,
                    )
            if not fermi_statistics:
                edge_from_node_model(device=device, region=name, node_model="Electrons")
                edge_from_node_model(device=device, region=name, node_model="Holes")
                electron_drift = (
                    f"ElectronCharge*{electron_mobility_model}*"
                    "0.5*(Electrons@n0+Electrons@n1)*ElectricField"
                )
                electron_diffusion = (
                    f"ElectronCharge*{electron_mobility_model}*{thermal_voltage_edge_model}*"
                    "(Electrons@n1-Electrons@n0)*EdgeInverseLength"
                )
                hole_drift = (
                    f"ElectronCharge*{hole_mobility_model}*0.5*(Holes@n0+Holes@n1)*ElectricField"
                )
                hole_diffusion = (
                    f"-ElectronCharge*{hole_mobility_model}*{thermal_voltage_edge_model}*"
                    "(Holes@n1-Holes@n0)*EdgeInverseLength"
                )
                for model_name, model_expression in (
                    ("ElectronDriftCurrent", electron_drift),
                    ("ElectronDiffusionCurrent", electron_diffusion),
                    ("HoleDriftCurrent", hole_drift),
                    ("HoleDiffusionCurrent", hole_diffusion),
                ):
                    CreateEdgeModel(device, name, model_name, model_expression)
                decomposition_residual = (
                    "ElectronCurrent+HoleCurrent-ElectronDriftCurrent-"
                    "ElectronDiffusionCurrent-HoleDriftCurrent-"
                    "HoleDiffusionCurrent"
                )
                CreateEdgeModel(
                    device,
                    name,
                    "CurrentDecompositionResidual",
                    decomposition_residual,
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
                        CreateContactNodeModel(device, backend_contact, model_name, model)
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
                                "ElectronCurrent" if variable == "Electrons" else "HoleCurrent"
                            ),
                        }
                        if is_circuit_study and contact["id"] == study["contact"]:
                            options["circuit_node"] = GetContactBiasName(backend_contact)
                        contact_equation(**options)
                else:
                    CreateSiliconDriftDiffusionAtContact(
                        device,
                        region["id"],
                        _backend_contact_id(contact),
                        is_circuit=(is_circuit_study and contact["id"] == study["contact"]),
                    )
                    if "slotboom_bgn" in selected_models:
                        backend_contact = _backend_contact_id(contact)
                        majority_n = (
                            "0.5*(NetDoping+pow(NetDoping^2+4*EffectiveIntrinsicDensity^2,0.5))"
                        )
                        majority_p = (
                            "0.5*(-NetDoping+pow(NetDoping^2+4*EffectiveIntrinsicDensity^2,0.5))"
                        )
                        for variable, suffix, target in (
                            (
                                "Electrons",
                                "nodeelectrons",
                                f"ifelse(NetDoping>0,{majority_n},"
                                f"EffectiveIntrinsicDensity^2/({majority_p}))",
                            ),
                            (
                                "Holes",
                                "nodeholes",
                                f"ifelse(NetDoping<0,{majority_p},"
                                f"EffectiveIntrinsicDensity^2/({majority_n}))",
                            ),
                        ):
                            CreateContactNodeModel(
                                device,
                                backend_contact,
                                f"{backend_contact}{suffix}",
                                f"{variable}-({target})",
                            )
            elif region["material"] == "silicon" and contact["kind"] == "metal_work_function":
                backend_contact = _backend_contact_id(contact)
                region_name = region["id"]
                edge_from_node_model(
                    device=device, region=region_name, node_model="BandGapNarrowing"
                )
                electron_richardson = float(contact.get("electron_richardson_a_cm2_k2") or 112.0)
                hole_richardson = float(contact.get("hole_richardson_a_cm2_k2") or 32.0)
                contact_endpoint = "n0" if contact["location"] == "x_min" else "n1"
                for variable, equation_name, current_model in (
                    (
                        "Electrons",
                        "ElectronContinuityEquation",
                        "ElectronCurrent",
                    ),
                    (
                        "Holes",
                        "HoleContinuityEquation",
                        "HoleCurrent",
                    ),
                ):
                    flux_name = f"{backend_contact}_{variable.lower()}_thermionic"
                    # Contact edge terms are added to the region balance with
                    # +n0/-n1 signs. Outward conventional emission is negative
                    # for electrons and positive for holes at either endpoint.
                    normal_sign = (-1 if contact["location"] == "x_min" else 1) * (
                        1 if variable == "Electrons" else -1
                    )
                    density = (
                        "EffectiveDensityConduction"
                        if variable == "Electrons"
                        else "EffectiveDensityValence"
                    )
                    bias_name = GetContactBiasName(backend_contact)
                    gap = f"(BandGap-BandGapNarrowing@{contact_endpoint})"
                    dos_offset = "0.5*V_t*log(EffectiveDensityConduction/EffectiveDensityValence)"
                    eta_metal = (
                        f"(Potential@{contact_endpoint}-{bias_name}-0.5*{gap}-{dos_offset})/V_t"
                        if variable == "Electrons"
                        else (
                            f"(-Potential@{contact_endpoint}+{bias_name}-0.5*{gap}+"
                            f"{dos_offset})/V_t"
                        )
                    )
                    richardson = electron_richardson if variable == "Electrons" else hole_richardson
                    coefficient = f"{normal_sign}*{richardson:.17g}*{temperature:.17g}^2"
                    flux = (
                        f"{coefficient}*({variable}@{contact_endpoint}/{density}-exp({eta_metal}))"
                    )
                    if fermi_statistics:
                        surface = f"{flux_name}_surface"
                        metal = f"{flux_name}_metal"
                        for prefix, eta in (
                            (surface, f"InvFermi({variable}@{contact_endpoint}/{density})"),
                            (metal, eta_metal),
                        ):
                            for model_id, expression in _fermi_one_models(prefix, eta).items():
                                CreateEdgeModel(device, region_name, model_id, expression)
                            for differentiated in ("Potential", "Electrons", "Holes"):
                                CreateEdgeModelDerivatives(
                                    device, region_name, f"{prefix}_eta", eta, differentiated
                                )
                        flux = f"{coefficient}*({surface}_supply-{metal}_supply)"
                        CreateEdgeModel(device, region_name, flux_name, flux)
                        for differentiated in ("Potential", "Electrons", "Holes"):
                            for endpoint_name in ("n0", "n1"):
                                derivative = (
                                    f"{coefficient}*({surface}_derivative*"
                                    f"{surface}_eta:{differentiated}@{endpoint_name}-"
                                    f"{metal}_derivative*{metal}_eta:{differentiated}@{endpoint_name})"
                                )
                                CreateEdgeModel(
                                    device,
                                    region_name,
                                    f"{flux_name}:{differentiated}@{endpoint_name}",
                                    derivative,
                                )
                        if is_circuit_study and contact["id"] == study["contact"]:
                            sign = "1" if variable == "Electrons" else "-1"
                            CreateEdgeModel(
                                device,
                                region_name,
                                f"{flux_name}:{bias_name}",
                                f"{sign}*{coefficient}*{metal}_derivative/V_t",
                            )
                    else:
                        CreateEdgeModel(device, region_name, flux_name, flux)
                        for differentiated in ("Potential", "Electrons", "Holes"):
                            CreateEdgeModelDerivatives(
                                device, region_name, flux_name, flux, differentiated
                            )
                        if is_circuit_study and contact["id"] == study["contact"]:
                            sign = "1" if variable == "Electrons" else "-1"
                            CreateEdgeModel(
                                device,
                                region_name,
                                f"{flux_name}:{bias_name}",
                                f"{sign}*{coefficient}*exp({eta_metal})/V_t",
                            )
                    schottky_options: dict[str, Any] = {
                        "device": device,
                        "contact": backend_contact,
                        "name": equation_name,
                        "edge_model": flux_name,
                        "edge_current_model": current_model,
                    }
                    if is_circuit_study and contact["id"] == study["contact"]:
                        schottky_options["circuit_node"] = GetContactBiasName(backend_contact)
                    contact_equation(**schottky_options)
        for interface, left, right in interface_names:
            if left["material"] == right["material"] == "silicon":
                for variable, equation_name in (
                    ("Electrons", "ElectronContinuityEquation"),
                    ("Holes", "HoleContinuityEquation"),
                ):
                    if fermi_statistics or "slotboom_bgn" in selected_models:
                        # A doping-dependent band step does not permit imposing
                        # equal densities across the interface. Match chemical
                        # potential and conserve flux instead, including its
                        # cross-variable Jacobian in the continuity equation.
                        quasi_fermi = (
                            "ElectronQuasiFermiEnergy"
                            if variable == "Electrons"
                            else "HoleQuasiFermiEnergy"
                        )
                        model = f"{variable}_chemical_continuity"
                        expression = f"{quasi_fermi}@r0-{quasi_fermi}@r1"
                        CreateInterfaceModel(device, interface, model, expression)
                        for differentiated in ("Potential", "Electrons", "Holes"):
                            for side in ("r0", "r1"):
                                CreateInterfaceModel(
                                    device,
                                    interface,
                                    f"{model}:{differentiated}@{side}",
                                    f"diff({expression},{differentiated}@{side})",
                                )
                    else:
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
                    "carrier_absolute_error" if drift_diffusion else "electrostatic_absolute_error"
                ]
            ),
            relative_error=float(solver["transient_initial_relative_error"]),
            maximum_iterations=int(solver["maximum_iterations"]),
        )
        solver_events.append(
            {"phase": "transient_initialization", "outcome": "converged", "attempt": 1}
        )

    requested = set(payload["observables"])
    native_model_names = dict(NATIVE_MODEL_NAMES)
    if not drift_diffusion:
        native_model_names.update(
            electron_density="IntrinsicElectrons", hole_density="IntrinsicHoles"
        )

    def extract_fields() -> dict[str, dict[str, Any]]:
        fields: dict[str, dict[str, Any]] = {}
        for region in regions:
            name = region["id"]
            node_positions = list(get_node_model_values(device=device, region=name, name="x"))
            edge_positions = [(left + right) / 2 for left, right in pairwise(node_positions)]
            if "potential" in requested:
                _append_field(
                    fields,
                    "potential",
                    node_positions,
                    list(get_node_model_values(device=device, region=name, name="Potential")),
                    "V",
                    "node",
                )
            if "electric_field" in requested:
                _append_field(
                    fields,
                    "electric_field",
                    edge_positions,
                    list(get_edge_model_values(device=device, region=name, name="ElectricField")),
                    "V/cm",
                    "edge",
                )
            if "electrostatic_flux" in requested:
                _append_field(
                    fields,
                    "electrostatic_flux",
                    edge_positions,
                    list(
                        get_edge_model_values(device=device, region=name, name="PotentialEdgeFlux")
                    ),
                    "C/cm^2",
                    "edge",
                )
            if "fixed_charge_density" in requested:
                _append_field(
                    fields,
                    "fixed_charge_density",
                    node_positions,
                    list(get_node_model_values(device=device, region=name, name="FixedBulkCharge")),
                    "C/cm^3",
                    "node",
                )
            if "lattice_temperature" in requested and name in temperature_profiles:
                _append_field(
                    fields,
                    "lattice_temperature",
                    node_positions,
                    list(
                        get_node_model_values(
                            device=device,
                            region=name,
                            name="LatticeTemperature",
                        )
                    ),
                    "K",
                    "node",
                )
            if region["material"] != "silicon":
                continue
            model_outputs = {
                "electron_density": (native_model_names["electron_density"], "cm^-3", "node"),
                "hole_density": (native_model_names["hole_density"], "cm^-3", "node"),
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
                "electron_drift_current_density": (
                    "ElectronDriftCurrent",
                    "A/cm^2",
                    "edge",
                ),
                "electron_diffusion_current_density": (
                    "ElectronDiffusionCurrent",
                    "A/cm^2",
                    "edge",
                ),
                "hole_drift_current_density": (
                    "HoleDriftCurrent",
                    "A/cm^2",
                    "edge",
                ),
                "hole_diffusion_current_density": (
                    "HoleDiffusionCurrent",
                    "A/cm^2",
                    "edge",
                ),
                "current_decomposition_residual": (
                    "CurrentDecompositionResidual",
                    "A/cm^2",
                    "edge",
                ),
            }
            for output, (model, unit, centering) in model_outputs.items():
                if output not in requested or (
                    not drift_diffusion and output not in {"electron_density", "hole_density"}
                ):
                    continue
                positions = node_positions if centering == "node" else edge_positions
                getter = get_node_model_values if centering == "node" else get_edge_model_values
                _append_field(
                    fields,
                    output,
                    positions,
                    list(getter(device=device, region=name, name=model)),
                    unit,
                    centering,
                )
            doping = list(get_node_model_values(device=device, region=name, name="NetDoping"))
            if "net_doping" in requested:
                _append_field(fields, "net_doping", node_positions, doping, "cm^-3", "node")
            for output, native_name in (
                ("donor_concentration", "PhysicalDonors"),
                ("acceptor_concentration", "PhysicalAcceptors"),
            ):
                if output in requested:
                    _append_field(
                        fields,
                        output,
                        node_positions,
                        list(get_node_model_values(device=device, region=name, name=native_name)),
                        "cm^-3",
                        "node",
                    )
            if drift_diffusion:
                electrons = list(
                    get_node_model_values(device=device, region=name, name="Electrons")
                )
                holes = list(get_node_model_values(device=device, region=name, name="Holes"))
                if "charge_density" in requested:
                    charge = float(get_parameter(device=device, region=name, name="ElectronCharge"))
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
                                get_edge_model_values(device=device, region=name, name=model)
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
                                get_node_model_values(device=device, region=name, name=model)
                            )
                            positions = node_positions
                            centering = "node"
                        else:
                            mobility = float(
                                get_parameter(device=device, region=name, name=parameter)
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
                    electron_current_values = list(
                        get_edge_model_values(device=device, region=name, name="ElectronCurrent")
                    )
                    hole_current_values = list(
                        get_edge_model_values(device=device, region=name, name="HoleCurrent")
                    )
                    _append_field(
                        fields,
                        "total_current_density",
                        edge_positions,
                        [
                            electron + hole
                            for electron, hole in zip(
                                electron_current_values,
                                hole_current_values,
                                strict=True,
                            )
                        ],
                        "A/cm^2",
                        "edge",
                    )
        return fields

    requested_contact = None if is_transient else payload["study"].get("contact")

    def set_dc_bias(value: float) -> None:
        voltage = value + contact_offsets[requested_contact]
        if is_ac:
            circuit_alter(name=circuit_source_name, value=voltage)
        else:
            set_parameter(
                device=device, name=GetContactBiasName(study_backend_contact), value=voltage
            )

    frequency_points: list[dict[str, Any]] = []

    def sample_ac(bias: float, dc_valid: bool) -> None:
        amplitude = float(study["amplitude_v"])
        for frequency in study["frequencies_hz"]:
            valid = dc_valid
            real = imaginary = 0.0
            if valid:
                try:
                    solve(type="ac", frequency=float(frequency))
                    real = -float(
                        get_circuit_node_value(
                            node=f"{circuit_source_name}.I", solution="ssac_real"
                        )
                    )
                    imaginary = -float(
                        get_circuit_node_value(
                            node=f"{circuit_source_name}.I", solution="ssac_imag"
                        )
                    )
                except Exception:
                    valid = False
            solver_events.append(
                {
                    "phase": "small_signal_ac",
                    "frequency_hz": float(frequency),
                    "bias_v": bias,
                    "attempt": 1,
                    "outcome": "converged" if valid else "failed",
                }
            )
            frequency_points.append(
                {
                    "bias_v": bias,
                    "valid": valid,
                    "frequency_hz": float(frequency),
                    "current_real_a_per_cm2": real,
                    "current_imag_a_per_cm2": imaginary,
                    "admittance_real_s_per_cm2": real / amplitude,
                    "admittance_imag_s_per_cm2": imaginary / amplitude,
                    "conductance_s_per_cm2": real / amplitude,
                    "capacitance_f_per_cm2": imaginary
                    / amplitude
                    / (2 * math.pi * float(frequency)),
                }
            )

    points: list[dict[str, Any]] = []
    field_samples: list[dict[str, Any]] = []
    current_bias = 0.0
    dc_absolute_error = float(
        solver["carrier_absolute_error" if drift_diffusion else "electrostatic_absolute_error"]
    )
    state_variables = [
        (region["id"], variable)
        for region in regions
        for variable in (
            ("Potential", "Electrons", "Holes")
            if drift_diffusion and region["material"] == "silicon"
            else ("Potential",)
        )
    ]
    for region_name, variable in state_variables:
        for checkpoint in ("Previous", "Recovery"):
            node_solution(device=device, region=region_name, name=f"{checkpoint}{variable}")

    def checkpoint_state(checkpoint: str, *, restore: bool = False) -> None:
        # Native model-to-model copies retain extended arithmetic; a Python
        # float round trip would truncate the last converged state to double.
        for region_name, variable in state_variables:
            saved = f"{checkpoint}{variable}"
            set_node_values(
                device=device,
                region=region_name,
                name=variable if restore else saved,
                init_from=saved if restore else variable,
            )

    conducting_contacts = [
        contact
        for contact in payload["contacts"]
        if _contact_region(payload, contact["location"])["material"] == "silicon"
        and contact["kind"] != "insulating"
    ]
    driven_contact = next(
        (contact for contact in payload["contacts"] if contact["id"] == requested_contact), None
    )
    equilibrium_predictor = bool(
        drift_diffusion
        and not is_transient
        and driven_contact is not None
        and _contact_region(payload, driven_contact["location"])["material"] != "silicon"
        and conducting_contacts
        and all(contact["kind"] == "ohmic" for contact in conducting_contacts)
        # Intrinsic carrier models use the grounded electrochemical reference.
        # A common nonzero contact potential requires a separate gauge transform.
        and all(contact_offsets[contact["id"]] == 0 for contact in conducting_contacts)
        and not any(
            interface.get("trap_density_cm2") is not None
            or interface.get("surface_electron_velocity_cm_s") is not None
            for interface in payload["interfaces"]
        )
    )

    def predict_stationary_equilibrium(bias_v: float) -> None:
        if not equilibrium_predictor:
            return
        # Only the Newton starting state is predicted. Every original carrier,
        # contact and interface equation is restored before the coupled solve
        # and before any AC response or canonical field is extracted.
        region_commands = [
            get_equation_command(device=device, region=region["id"], name=name)
            for region in regions
            for name in get_equation_list(device=device, region=region["id"])
        ]
        contact_commands = [
            get_contact_equation_command(
                device=device, contact=_backend_contact_id(contact), name=name
            )
            for contact in payload["contacts"]
            for name in get_contact_equation_list(
                device=device, contact=_backend_contact_id(contact)
            )
            if name in {"ElectronContinuityEquation", "HoleContinuityEquation"}
        ]
        interface_commands = [
            get_interface_equation_command(device=device, interface=interface, name=name)
            for interface, _left, _right in interface_names
            for name in get_interface_equation_list(device=device, interface=interface)
            if name in {"ElectronContinuityEquation", "HoleContinuityEquation"}
        ]
        try:
            for command in contact_commands:
                delete_contact_equation(
                    device=device, contact=command["contact"], name=command["name"]
                )
            for command in interface_commands:
                delete_interface_equation(
                    device=device, interface=command["interface"], name=command["name"]
                )
            for command in region_commands:
                if command["name"] in {"ElectronContinuityEquation", "HoleContinuityEquation"}:
                    delete_equation(device=device, region=command["region"], name=command["name"])
            for command in electrostatic_equations.values():
                equation(**command)
            solve(
                type="dc",
                absolute_error=float(solver["electrostatic_absolute_error"]),
                relative_error=float(solver["relative_error"]),
                maximum_iterations=int(solver["maximum_iterations"]),
            )
            for region in regions:
                if region["material"] == "silicon":
                    for variable in ("Electrons", "Holes"):
                        set_node_values(
                            device=device,
                            region=region["id"],
                            name=variable,
                            init_from=f"Intrinsic{variable}",
                        )
            solver_events.append(
                {
                    "phase": "stationary_equilibrium_predictor",
                    "bias_v": bias_v,
                    "outcome": "converged",
                    "carrier_equations_restored_before_verification": True,
                }
            )
        finally:
            for command in region_commands:
                equation(**command)
            for command in contact_commands:
                contact_equation(**command)
            for command in interface_commands:
                interface_equation(**command)

    for requested_bias in _bias_points(payload["study"]):
        print(f"Requested operating point: {requested_bias:.17g} V", flush=True)
        bias = requested_bias
        converged = True
        attempts = 1
        message = None
        if requested_contact is not None:
            assert study_backend_contact is not None
            checkpoint_state("Previous")
            checkpoint_state("Recovery")
            study = payload["study"]
            first_bias = (
                bias
                if equilibrium_predictor
                else _initial_dc_bias(current_bias, bias, temperature, study)
            )
            set_dc_bias(first_bias)
            left = current_bias
            step = (first_bias - current_bias) / 2
            failed_initial_attempt = False
            try:
                predict_stationary_equilibrium(first_bias)
                solve(
                    type="dc",
                    absolute_error=dc_absolute_error,
                    relative_error=float(solver["relative_error"]),
                    maximum_iterations=int(solver["maximum_iterations"]),
                )
                solver_events.append(
                    {
                        "phase": (
                            "requested_operating_point"
                            if first_bias == requested_bias
                            else "initial_continuation_step"
                        ),
                        "requested_bias_v": requested_bias,
                        "attempted_bias_v": first_bias,
                        "attempt": attempts,
                        "outcome": "converged",
                    }
                )
                converged = first_bias == requested_bias
                if not converged:
                    left = first_bias
                    step = (first_bias - current_bias) * 1.5
                    checkpoint_state("Recovery")
            except Exception:
                failed_initial_attempt = True
                solver_events.append(
                    {
                        "phase": "requested_operating_point",
                        "requested_bias_v": requested_bias,
                        "attempted_bias_v": first_bias,
                        "attempt": attempts,
                        "outcome": "failed",
                    }
                )
                converged = False
            if not converged:
                if study.get("strategy") == "adaptive":
                    minimum = max(float(study.get("minimum_step_v", 0.0)), 1e-12)
                    maximum = max(minimum, 8 * 8.617333262145e-5 * temperature)
                    controller = AdaptiveStepController(
                        initial_step=min(
                            max(
                                abs(first_bias - current_bias)
                                if failed_initial_attempt
                                else abs(step),
                                minimum,
                            ),
                            maximum,
                        ),
                        minimum_step=minimum,
                        maximum_step=maximum,
                        maximum_retries=study.get("maximum_retries", 0),
                    )
                    continue_allowed = True
                    if failed_initial_attempt:
                        try:
                            controller.failed()
                        except TransientRecoveryExhausted:
                            continue_allowed = False
                    # Successful continuation points are not failed retries.
                    # Bound total work separately from consecutive failures;
                    # the runner's elapsed-time budget is authoritative too.
                    for _advance in range(10000 if continue_allowed else 0):
                        remaining = requested_bias - left
                        candidate = left + math.copysign(
                            controller.candidate(abs(remaining)), remaining
                        )
                        checkpoint_state("Recovery", restore=True)
                        print(f"Continuation operating point: {candidate:.17g} V", flush=True)
                        set_dc_bias(candidate)
                        attempts += 1
                        try:
                            predict_stationary_equilibrium(candidate)
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
                                    "attempted_bias_v": candidate,
                                    "attempt": attempts,
                                    "outcome": "failed",
                                }
                            )
                            try:
                                controller.failed()
                            except TransientRecoveryExhausted:
                                break
                            continue
                        solver_events.append(
                            {
                                "phase": (
                                    "requested_operating_point"
                                    if candidate == requested_bias
                                    else "recovery_midpoint"
                                ),
                                "requested_bias_v": requested_bias,
                                "attempted_bias_v": candidate,
                                "attempt": attempts,
                                "outcome": "converged",
                            }
                        )
                        left = candidate
                        checkpoint_state("Recovery")
                        if candidate == requested_bias:
                            converged = True
                            break
                        controller.succeeded()
                if not converged:
                    message = "nonlinear solve did not converge"
                    checkpoint_state("Previous", restore=True)
                    set_dc_bias(current_bias)
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
        if is_ac:
            sample_ac(bias, converged)

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
                        get_circuit_node_value(node=f"{circuit_source_name}.I", solution="dcop")
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
            transient_field_samples.append({"valid": True, "fields": last_converged_fields})
            current_time = next_time
            step_controller.succeeded()
            steps += 1
        if current_time < stop_time and not recovery_exhausted:
            raise RuntimeError("transient study exhausted maximum_steps")

    fields = extract_fields()
    field_sweeps: dict[str, dict[str, Any]] = {}
    for name, field in fields.items():
        sweep_values: list[float] = []
        validity: list[bool] = []
        for sample in field_samples:
            sampled_field = sample["fields"].get(name)
            if (
                sampled_field is None
                or sampled_field["positions_cm"] != field["positions_cm"]
                or len(sampled_field["values"]) != len(field["values"])
            ):
                raise ValueError(f"field topology changed during study: {name}")
            sweep_values.extend(sampled_field["values"])
            validity.extend([bool(sample["valid"])] * len(sampled_field["values"]))
        field_sweeps[name] = {
            "positions_cm": field["positions_cm"],
            "values": sweep_values,
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
                    raise ValueError(f"field topology changed during transient study: {name}")
                transient_values.extend(sampled["values"])
                transient_validity.extend([True] * len(sampled["values"]))
            transient_field_sweeps[name] = {
                "positions_cm": field["positions_cm"],
                "values": transient_values,
                "validity": transient_validity,
                "unit": field["unit"],
                "centering": field["centering"],
            }

    interface_charge_densities: dict[str, float] = {}
    interface_surface_rates: dict[str, float] = {}
    interface_trap_occupancies: dict[str, float] = {}
    for interface, left, right in interface_names:
        record = next(
            (item for item in payload["interfaces"] if item["id"] == interface),
            None,
        )
        if record is None:
            continue
        charge = 1.602176634e-19 * float(record.get("fixed_charge_cm2") or 0.0)
        silicon = left if left["material"] == "silicon" else right
        interface_endpoint = -1 if silicon is left else 0
        if record.get("trap_density_cm2") is not None:
            charge += float(
                get_node_model_values(
                    device=device,
                    region=silicon["id"],
                    name=f"InterfaceTrapChargeSheet_{interface}",
                )[interface_endpoint]
            )
            interface_trap_occupancies[interface] = float(
                get_node_model_values(
                    device=device,
                    region=silicon["id"],
                    name=f"InterfaceTrapOccupancy_{interface}",
                )[interface_endpoint]
            )
        if record.get("surface_electron_velocity_cm_s") is not None:
            interface_surface_rates[interface] = float(
                get_node_model_values(
                    device=device,
                    region=silicon["id"],
                    name=f"SurfaceRecombinationSheet_{interface}",
                )[interface_endpoint]
            )
        interface_charge_densities[interface] = charge

    result = {
        "schema_version": "2.0",
        "simulator_version": devsim.__version__,
        "status": "completed",
        "terminals": [
            contact["id"] for contact in payload["contacts"] if contact["kind"] != "insulating"
        ],
        "contact_areas_m2": {
            contact["id"]: contact.get("area_m2")
            for contact in payload["contacts"]
            if contact["kind"] != "insulating" and contact.get("area_m2") is not None
        },
        "interface_charge_densities_c_per_cm2": interface_charge_densities,
        "interface_surface_recombination_cm2_s": interface_surface_rates,
        "interface_trap_occupancies": interface_trap_occupancies,
        "requested_observables": payload["observables"],
        "sign_convention": payload["sign_convention"],
        "parameter_set_id": payload["physics"]["parameter_set_id"],
        "parameter_sources": payload["physics"].get("parameter_sources", {}),
        "solver_configuration": payload["solver"],
        "numerical_precision": numerical_precision,
        "profile_bias_values_v": payload.get("profile_bias_values_v"),
        "profile_sampling_provenance": payload.get("profile_sampling_provenance"),
        "solver_events": solver_events,
        "native_model_names": {
            name: native_model_names[name]
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
        "ac_bias_scheduled": bool(study.get("bias_scheduled", False)),
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
