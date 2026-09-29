"""Reviewed, data-only DEVSIM 1D runtime copied into compiled workspaces.

All expression strings in this file are platform-owned. The input payload is a
strict numeric and identifier contract produced by the adapter compiler.
"""

from __future__ import annotations

import json
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any, cast


def _boundary_tag(index: int, count: int) -> str:
    if index == 0:
        return "x_min"
    if index == count:
        return "x_max"
    return f"boundary_{index}"


def _profile_expression(profile: dict[str, Any], region: dict[str, Any]) -> str:
    kind = profile["kind"]
    if kind == "constant":
        return f"{profile['value_cm3']:.17g}"
    if kind == "linear":
        width = region["x1_cm"] - region["x0_cm"]
        delta = profile["end_value_cm3"] - profile["start_value_cm3"]
        return (
            f"{profile['start_value_cm3']:.17g}+"
            f"((x-{region['x0_cm']:.17g})/{width:.17g})*{delta:.17g}"
        )
    if kind == "gaussian":
        return (
            f"{profile['peak_cm3']:.17g}*exp(-0.5*((x-"
            f"{profile['center_cm']:.17g})/{profile['standard_deviation_cm']:.17g})^2)"
        )
    if kind == "error_function":
        argument = (
            f"((x-{profile['junction_position_cm']:.17g})/"
            f"{profile['characteristic_length_cm']:.17g})"
        )
        fraction = f"0.5*erfc{argument}"
        if profile["orientation"] == "increasing_x":
            fraction = f"(1-({fraction}))"
        return f"{profile['surface_value_cm3']:.17g}*({fraction})"
    if kind == "tabulated":
        positions = profile["positions_cm"]
        values = profile["values_cm3"]
        expression = f"{values[-1]:.17g}"
        for index in range(len(positions) - 2, -1, -1):
            x0, x1 = positions[index], positions[index + 1]
            y0, y1 = values[index], values[index + 1]
            if profile.get("interpolation", "linear") == "nearest":
                boundary = (x0 + x1) / 2
                segment = f"{y0:.17g}"
            else:
                boundary = x1
                segment = f"{y0:.17g}+(x-{x0:.17g})*{((y1-y0)/(x1-x0)):.17g}"
            expression = f"ifelse(x < {boundary:.17g}, {segment}, {expression})"
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


def main() -> int:
    import devsim  # type: ignore[import-untyped]
    from devsim import (
        add_1d_contact,
        add_1d_interface,
        add_1d_mesh_line,
        add_1d_region,
        create_1d_mesh,
        create_device,
        finalize_mesh,
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
    from devsim.python_packages.model_create import (  # type: ignore[import-untyped]
        CreateContinuousInterfaceModel,
        CreateNodeModel,
        CreateSolution,
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
        SetOxideParameters,
        SetSiliconParameters,
    )

    payload_path = Path(sys.argv[1] if len(sys.argv) > 1 else "input.json")
    payload = json.loads(payload_path.read_text())
    if payload.get("schema_version") != "2.0":
        raise ValueError("unsupported DEVSIM payload schema")
    if any(
        interface.get("fixed_charge_cm2") not in {None, 0.0}
        for interface in payload["interfaces"]
    ):
        raise ValueError("fixed interface charge is not reviewed in this runtime")
    if any(
        contact["kind"] == "metal_work_function" for contact in payload["contacts"]
    ):
        raise ValueError("metal work-function boundary is not reviewed in this runtime")

    device = "novatom_device"
    mesh = "novatom_mesh"
    regions = payload["regions"]
    create_1d_mesh(mesh=mesh)
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
        add_1d_mesh_line(
            mesh=mesh,
            pos=position,
            ps=spacing,
            tag=_boundary_tag(index, len(regions)),
        )
    for contact in payload["contacts"]:
        add_1d_contact(
            mesh=mesh,
            name=contact["id"],
            tag=contact["location"],
            material="metal",
        )
    interface_names: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for index, (left, right) in enumerate(pairwise(regions), start=1):
        name = _interface_name(payload, left["id"], right["id"])
        add_1d_interface(mesh=mesh, name=name, tag=_boundary_tag(index, len(regions)))
        interface_names.append((name, left, right))
    material_names = {"silicon": "Si", "silicon_dioxide": "Ox"}
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
    by_region: dict[str, list[dict[str, Any]]] = {
        region["id"]: [] for region in regions
    }
    for profile in payload["profiles"]:
        by_region[profile["region"]].append(profile)
    for region in regions:
        name = region["id"]
        if region["material"] == "silicon":
            SetSiliconParameters(device, name, temperature)
            set_parameter(device=device, region=name, name="taun", value=1e-8)
            set_parameter(device=device, region=name, name="taup", value=1e-8)
            donors = [
                _profile_expression(profile, region)
                for profile in by_region[name]
                if profile["species"] == "donor"
            ]
            acceptors = [
                _profile_expression(profile, region)
                for profile in by_region[name]
                if profile["species"] == "acceptor"
            ]
            CreateNodeModel(device, name, "Donors", _sum_expressions(donors))
            CreateNodeModel(device, name, "Acceptors", _sum_expressions(acceptors))
            CreateNodeModel(device, name, "NetDoping", "Donors-Acceptors")
            CreateSolution(device, name, "Potential")
            CreateSiliconPotentialOnly(device, name)
        else:
            SetOxideParameters(device, name, temperature)
            CreateSolution(device, name, "Potential")
            CreateOxidePotentialOnly(device, name)

    for contact in payload["contacts"]:
        region = _contact_region(payload, contact["location"])
        set_parameter(device=device, name=GetContactBiasName(contact["id"]), value=0.0)
        if region["material"] == "silicon" and contact["kind"] == "ohmic":
            CreateSiliconPotentialOnlyContact(device, region["id"], contact["id"])
        elif (
            region["material"] == "silicon_dioxide"
            and contact["kind"] == "ideal_gate"
        ):
            CreateOxideContact(device, region["id"], contact["id"])
        else:
            raise ValueError("contact kind is incompatible with adjacent material")
    for interface, _left, _right in interface_names:
        CreateSiliconOxideInterface(device, interface)
    solve(type="dc", absolute_error=1.0, relative_error=1e-10, maximum_iterations=80)

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
            CreateSiliconDriftDiffusion(device, name)
        for contact in payload["contacts"]:
            region = _contact_region(payload, contact["location"])
            if region["material"] == "silicon" and contact["kind"] == "ohmic":
                CreateSiliconDriftDiffusionAtContact(
                    device, region["id"], contact["id"]
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
        solve(type="dc", absolute_error=1e10, relative_error=1e-10, maximum_iterations=80)

    requested_contact = payload["study"].get("contact")
    points: list[dict[str, Any]] = []
    for bias in _bias_points(payload["study"]):
        if requested_contact is not None:
            set_parameter(
                device=device,
                name=GetContactBiasName(requested_contact),
                value=bias,
            )
            solve(type="dc", absolute_error=1e10, relative_error=1e-10, maximum_iterations=80)
        currents: dict[str, float] = {}
        charges: dict[str, float] = {}
        for contact in payload["contacts"]:
            region = _contact_region(payload, contact["location"])
            current = 0.0
            if drift_diffusion and region["material"] == "silicon":
                current = get_contact_current(
                    device=device,
                    contact=contact["id"],
                    equation="ElectronContinuityEquation",
                ) + get_contact_current(
                    device=device,
                    contact=contact["id"],
                    equation="HoleContinuityEquation",
                )
            currents[contact["id"]] = current
            charges[contact["id"]] = get_contact_charge(
                device=device,
                contact=contact["id"],
                equation="PotentialEquation",
            )
        points.append(
            {
                "bias_v": bias,
                "converged": True,
                "currents_a_per_cm2": currents,
                "charges_c_per_cm2": charges,
                "attempts": 1,
            }
        )

    requested = set(payload["observables"])
    fields: dict[str, dict[str, Any]] = {}
    for region in regions:
        name = region["id"]
        node_positions = list(
            get_node_model_values(device=device, region=name, name="x")
        )
        edge_positions = [(left + right) / 2 for left, right in pairwise(node_positions)]
        if "potential" in requested:
            _append_field(
                fields,
                "potential",
                node_positions,
                list(
                    get_node_model_values(device=device, region=name, name="Potential")
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
        if region["material"] != "silicon":
            continue
        model_outputs = {
            "electron_density": ("Electrons", "cm^-3", "node"),
            "hole_density": ("Holes", "cm^-3", "node"),
            "recombination_rate": ("USRH", "cm^-3/s", "node"),
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
        _append_field(fields, "net_doping", node_positions, doping, "cm^-3", "node")
        if drift_diffusion:
            electrons = list(
                get_node_model_values(device=device, region=name, name="Electrons")
            )
            holes = list(
                get_node_model_values(device=device, region=name, name="Holes")
            )
            if "charge_density" in requested:
                charge = float(
                    get_parameter(device=device, region=name, name="ElectronCharge")
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
                    mobility = float(
                        get_parameter(device=device, region=name, name=parameter)
                    )
                    _append_field(
                        fields,
                        output,
                        node_positions,
                        [mobility] * len(node_positions),
                        "cm^2/V/s",
                        "node",
                    )

    result = {
        "schema_version": "2.0",
        "simulator_version": devsim.__version__,
        "status": "completed",
        "terminals": [contact["id"] for contact in payload["contacts"]],
        "bias_points": points,
        "fields": fields,
    }
    Path("native_result.json").write_text(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
