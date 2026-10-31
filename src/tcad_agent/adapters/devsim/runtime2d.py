"""DEVSIM runtime for rectangular two-dimensional structures.

The payload comes from ``DevsimAdapter`` (``dimension`` 2). Coordinates follow the experiment:
``x`` is the stack (depth) axis and ``y`` the lateral axis, in cm. DEVSIM's own x axis is the
lateral one, so they are swapped on entering DEVSIM and nothing outside this file sees that.

The structure is a tensor-product mesh. DEVSIM only creates a contact on the boundary between a
region and a neighbouring region, so the device is wrapped in a thin inert ``air`` region that
carries no equations. Results are written in the same versioned table export the Sentaurus
adapter produces, so normalization, validation and display are shared.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

_PAD_CM = 2.0e-7
_BOLTZMANN_EV_PER_K = 8.617333262145e-5
_ELEMENTARY_CHARGE_C = 1.602176634e-19
_EDGE_TOLERANCE_CM = 1.0e-9
_MAX_BIAS_STEP_V = 0.1
_MIN_BIAS_STEP_V = 1.0e-4
_AIR = "air"
# A direct sparse solve of a coupled 2D system grows quickly; beyond this the run would take hours
# and several gigabytes, so the mesh-refinement ladder stops there instead.
_MAX_NODES = 250_000


# Measured: the coupled direct solve of this system peaks near 15 kB per mesh node; the reserve
# keeps the rest of the machine usable while a run is going.
_BYTES_PER_NODE = 20_000
_MEMORY_RESERVE_BYTES = 1_000_000_000


def _available_memory_bytes() -> int | None:
    """Memory that can be used without paging, or None when it cannot be read."""
    try:
        if sys.platform == "win32":
            import ctypes

            class Status(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong),
                ]

            status = Status()
            status.length = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available_physical)
            return None
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, AttributeError):
        return None
    return None


def _tag(value: float) -> float:
    return round(float(value), 14)


def _fine_spacing(region: dict[str, Any]) -> float:
    minimum = region.get("minimum_mesh_spacing_cm")
    return float(minimum if minimum is not None else region["mesh_spacing_cm"])


def _bulk_spacing(region: dict[str, Any]) -> float:
    maximum = region.get("maximum_mesh_spacing_cm")
    return float(maximum if maximum is not None else region["mesh_spacing_cm"])


def contact_box(contact: dict[str, Any], region: dict[str, Any]) -> tuple[float, float, float, float]:
    """(lateral low, lateral high, depth low, depth high) in DEVSIM x/y order for a contact."""
    side = contact["location"]
    if side in {"x_min", "x_max"}:
        low, high = contact.get("span_cm") or (region["y0_cm"], region["y1_cm"])
        depth = region["x0_cm"] if side == "x_min" else region["x1_cm"]
        return float(low), float(high), float(depth), float(depth)
    low, high = contact.get("span_cm") or (region["x0_cm"], region["x1_cm"])
    lateral = region["y0_cm"] if side == "y_min" else region["y1_cm"]
    return float(lateral), float(lateral), float(low), float(high)


def contact_length_cm(contact: dict[str, Any], region: dict[str, Any]) -> float:
    xl, xh, yl, yh = contact_box(contact, region)
    return (xh - xl) + (yh - yl)


def mesh_lines(payload: dict[str, Any]) -> tuple[dict[float, float], dict[float, float]]:
    """Mesh line positions and spacings: (lateral lines, depth lines), DEVSIM x then y."""
    regions = payload["regions"]
    by_id = {region["id"]: region for region in regions}
    lateral: dict[float, float] = {}
    depth: dict[float, float] = {}

    def note(lines: dict[float, float], position: float, spacing: float) -> None:
        key = _tag(position)
        lines[key] = min(lines.get(key, math.inf), float(spacing))

    contact_edges: set[tuple[str, float]] = set()
    for contact in payload["contacts"]:
        region = by_id[contact["region"]]
        xl, xh, yl, yh = contact_box(contact, region)
        fine = _fine_spacing(region)
        note(lateral, xl, fine)
        note(lateral, xh, fine)
        note(depth, yl, fine)
        note(depth, yh, fine)
        contact_edges.add(("lateral" if xl == xh else "depth", _tag(xl if xl == xh else yl)))
    doping_edges: set[tuple[str, float]] = set()
    for profile in payload["profiles"]:
        if profile["kind"] != "box":
            continue
        fine = _fine_spacing(by_id[profile["region"]])
        for position in (profile["y0_cm"], profile["y1_cm"]):
            note(lateral, position, fine)
            doping_edges.add(("lateral", _tag(position)))
        for position in (profile["x0_cm"], profile["x1_cm"]):
            note(depth, position, fine)
            doping_edges.add(("depth", _tag(position)))
    for cut in payload.get("profile_cuts", []):
        # A line on the cut depth makes the profile exact mesh nodes instead of an interpolation.
        spacing = min(_fine_spacing(region) for region in regions)
        note(depth, cut["depth_cm"], spacing)

    def shared(region: dict[str, Any], axis: str, position: float) -> bool:
        for other in regions:
            if other is region:
                continue
            if axis == "depth" and abs(other["x0_cm"] - position) < _EDGE_TOLERANCE_CM + 0.0:
                if min(region["y1_cm"], other["y1_cm"]) > max(region["y0_cm"], other["y0_cm"]):
                    return True
            if axis == "depth" and abs(other["x1_cm"] - position) < _EDGE_TOLERANCE_CM:
                if min(region["y1_cm"], other["y1_cm"]) > max(region["y0_cm"], other["y0_cm"]):
                    return True
            if axis == "lateral" and (
                abs(other["y0_cm"] - position) < _EDGE_TOLERANCE_CM
                or abs(other["y1_cm"] - position) < _EDGE_TOLERANCE_CM
            ):
                if min(region["x1_cm"], other["x1_cm"]) > max(region["x0_cm"], other["x0_cm"]):
                    return True
        return False

    for region in regions:
        fine, bulk = _fine_spacing(region), _bulk_spacing(region)
        for position in (region["y0_cm"], region["y1_cm"]):
            featured = ("lateral", _tag(position)) in contact_edges | doping_edges or shared(
                region, "lateral", position
            )
            note(lateral, position, fine if featured else bulk)
        for position in (region["x0_cm"], region["x1_cm"]):
            featured = ("depth", _tag(position)) in contact_edges | doping_edges or shared(
                region, "depth", position
            )
            note(depth, position, fine if featured else bulk)
    # An edge that touches a region of a finer mesh takes that spacing.
    for region in regions:
        fine = _fine_spacing(region)
        for position in list(lateral):
            if region["y0_cm"] - 1e-14 <= position <= region["y1_cm"] + 1e-14:
                if abs(position - region["y0_cm"]) < 1e-14 or abs(position - region["y1_cm"]) < 1e-14:
                    lateral[position] = min(lateral[position], fine)
        for position in list(depth):
            if region["x0_cm"] - 1e-14 <= position <= region["x1_cm"] + 1e-14:
                if abs(position - region["x0_cm"]) < 1e-14 or abs(position - region["x1_cm"]) < 1e-14:
                    depth[position] = min(depth[position], fine)
    # Away from a silicon/insulator interface the mesh grows geometrically from the interface
    # spacing, as thin inversion and accumulation layers need (a numerical choice, not physics).
    for semiconductor in regions:
        if semiconductor["material"] != "silicon":
            continue
        for insulator in regions:
            if insulator["material"] == "silicon":
                continue
            h0 = min(_fine_spacing(semiconductor), _fine_spacing(insulator))
            cap = _bulk_spacing(semiconductor)
            overlap_lateral = min(semiconductor["y1_cm"], insulator["y1_cm"]) > max(
                semiconductor["y0_cm"], insulator["y0_cm"]
            )
            overlap_depth = min(semiconductor["x1_cm"], insulator["x1_cm"]) > max(
                semiconductor["x0_cm"], insulator["x0_cm"]
            )
            if overlap_lateral and abs(insulator["x1_cm"] - semiconductor["x0_cm"]) < 1e-9:
                _grade(depth, semiconductor["x0_cm"], +1, h0, cap, semiconductor["x1_cm"])
            if overlap_lateral and abs(insulator["x0_cm"] - semiconductor["x1_cm"]) < 1e-9:
                _grade(depth, semiconductor["x1_cm"], -1, h0, cap, semiconductor["x0_cm"])
            if overlap_depth and abs(insulator["y1_cm"] - semiconductor["y0_cm"]) < 1e-9:
                _grade(lateral, semiconductor["y0_cm"], +1, h0, cap, semiconductor["y1_cm"])
            if overlap_depth and abs(insulator["y0_cm"] - semiconductor["y1_cm"]) < 1e-9:
                _grade(lateral, semiconductor["y1_cm"], -1, h0, cap, semiconductor["y0_cm"])
    low_l, high_l = min(lateral), max(lateral)
    low_d, high_d = min(depth), max(depth)
    outer = max(_bulk_spacing(region) for region in regions)
    # A tensor mesh carries every line across the whole device, so a fine line would otherwise
    # make everything between it and the next line fine too. Grow the spacing geometrically
    # away from each fine line (the same growth Sentaurus applies) to keep it local.
    for lines, low, high in ((lateral, low_l, high_l), (depth, low_d, high_d)):
        for position, spacing in list(lines.items()):
            if spacing < outer:
                _grade(lines, position, +1, spacing, outer, high)
                _grade(lines, position, -1, spacing, outer, low)
    note(lateral, low_l - _PAD_CM, outer)
    note(lateral, high_l + _PAD_CM, outer)
    note(depth, low_d - _PAD_CM, outer)
    note(depth, high_d + _PAD_CM, outer)
    return lateral, depth


_INTERFACE_GROWTH = 1.4


def _grade(
    lines: dict[float, float], start: float, direction: int, h0: float, cap: float, stop: float
) -> None:
    """Mesh lines whose spacing grows geometrically from ``start`` towards ``stop``."""
    position, spacing = float(start), float(h0)
    lines[_tag(position)] = min(lines.get(_tag(position), math.inf), spacing)
    while spacing < cap:
        position += direction * spacing
        spacing *= _INTERFACE_GROWTH
        if (position - stop) * direction >= -spacing:
            break
        key = _tag(position)
        lines[key] = min(lines.get(key, math.inf), min(spacing, cap))


def _statistics() -> Any:
    try:
        import devsim_statistics as statistics  # type: ignore[import-not-found]
    except ImportError:
        from tcad_agent.adapters.devsim import statistics
    return statistics


def net_doping_at(profiles: list[dict[str, Any]], lateral_cm: float, depth_cm: float) -> float:
    """Donors minus acceptors (cm^-3) at a point of a region."""
    total = 0.0
    for profile in profiles:
        if profile.get("species") not in {"donor", "acceptor"}:
            continue
        if profile["kind"] == "box":
            tolerance = 1.0e-9
            if not (
                profile["y0_cm"] - tolerance <= lateral_cm <= profile["y1_cm"] + tolerance
                and profile["x0_cm"] - tolerance <= depth_cm <= profile["x1_cm"] + tolerance
            ):
                continue
        total += (1.0 if profile["species"] == "donor" else -1.0) * float(profile["value_cm3"])
    return total


def fermi_contact_state(
    *,
    net_doping_cm3: float,
    conduction_density_cm3: float,
    valence_density_cm3: float,
    band_gap_ev: float,
    thermal_voltage_v: float,
) -> tuple[float, float, float]:
    """Neutral electron and hole densities and the potential of an ohmic boundary."""
    statistics = _statistics()
    gap = band_gap_ev / thermal_voltage_v

    def neutrality(eta_n: float) -> float:
        electrons = conduction_density_cm3 * statistics.fermi(eta_n)
        holes = valence_density_cm3 * statistics.fermi(-gap - eta_n)
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
    electrons = conduction_density_cm3 * statistics.fermi(eta_n)
    holes = valence_density_cm3 * statistics.fermi(-gap - eta_n)
    offset = 0.5 * band_gap_ev + 0.5 * thermal_voltage_v * math.log(
        conduction_density_cm3 / valence_density_cm3
    )
    return electrons, holes, offset + thermal_voltage_v * eta_n


def advance_blend(apply_blend: Any, try_solve: Any, events: list[str]) -> None:
    """Continuation from Boltzmann (0) to Fermi-Dirac (1) statistics, halving the step on failure."""
    current, step = 0.0, 1.0
    for _ in range(256):
        candidate = min(1.0, current + step)
        apply_blend(candidate)
        if try_solve():
            current = candidate
            if current >= 1.0:
                return
            step = min(1.0, step * 2.0)
        else:
            apply_blend(current)
            step /= 2.0
            events.append(f"statistics blend step reduced to {step:.4g}")
            if step < 1.0 / 1024:
                break
    raise RuntimeError("Fermi-Dirac statistics could not be introduced from the Boltzmann solution")


def _expression_box(profile: dict[str, Any]) -> str:
    eps = 1.0e-11
    # DEVSIM x is the experiment's lateral y; DEVSIM y is the experiment's depth x.
    return (
        f"{profile['value_cm3']:.12e}"
        f"*step(x-({profile['y0_cm'] - eps:.14e}))*step(({profile['y1_cm'] + eps:.14e})-x)"
        f"*step(y-({profile['x0_cm'] - eps:.14e}))*step(({profile['x1_cm'] + eps:.14e})-y)"
    )


def _doping_expression(profiles: list[dict[str, Any]], species: str) -> str:
    terms = []
    for profile in profiles:
        if profile.get("species") != species:
            continue
        terms.append(
            _expression_box(profile) if profile["kind"] == "box" else f"{profile['value_cm3']:.12e}"
        )
    return "+".join(terms) if terms else "0"


def main(payload_path: str = "input.json") -> int:
    started = time.time()
    import devsim  # type: ignore[import-untyped]
    from devsim import (
        add_2d_contact,
        add_2d_interface,
        add_2d_mesh_line,
        add_2d_region,
        contact_equation,
        create_2d_mesh,
        create_device,
        equation,
        finalize_mesh,
        get_contact_charge,
        get_contact_current,
        get_node_model_values,
        get_parameter,
        node_solution,
        set_node_values,
        set_parameter,
        solve,
    )
    from devsim.python_packages.model_create import (  # type: ignore[import-untyped]
        CreateContactNodeModel,
        CreateContactNodeModelDerivative,
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

    payload = json.loads(Path(payload_path).read_text())
    if payload.get("dimension") != 2:
        raise ValueError("the two-dimensional runtime needs a dimension 2 payload")
    device, mesh = "novatom_device", "novatom_mesh"
    regions: list[dict[str, Any]] = payload["regions"]
    by_id = {region["id"]: region for region in regions}
    contacts: list[dict[str, Any]] = payload["contacts"]
    physics = payload["physics"]
    models = set(physics["models"])
    temperature = float(physics["temperature_k"])
    solver_settings = payload["solver"]
    study = payload["study"]
    fermi = "fermi" in models
    if any(contact["kind"] == "metal_work_function" and by_id[contact["region"]]["material"] == "silicon"
           for contact in contacts):
        raise ValueError("a metal work-function contact on silicon is not supported in 2D")

    lateral_lines, depth_lines = mesh_lines(payload)
    create_2d_mesh(mesh=mesh)
    for position, spacing in sorted(lateral_lines.items()):
        add_2d_mesh_line(mesh=mesh, dir="x", pos=position, ps=spacing)
    for position, spacing in sorted(depth_lines.items()):
        add_2d_mesh_line(mesh=mesh, dir="y", pos=position, ps=spacing)
    add_2d_region(mesh=mesh, material="Air", region=_AIR)
    material_names = {"silicon": "Si", "silicon_dioxide": "Ox", "generic_dielectric": "Ox"}
    for region in regions:
        add_2d_region(
            mesh=mesh,
            material=material_names[region["material"]],
            region=region["id"],
            xl=region["y0_cm"],
            xh=region["y1_cm"],
            yl=region["x0_cm"],
            yh=region["x1_cm"],
        )
    backend_contact = {contact["id"]: f"contact_{index}" for index, contact in enumerate(contacts)}
    for contact in contacts:
        xl, xh, yl, yh = contact_box(contact, by_id[contact["region"]])
        add_2d_contact(
            mesh=mesh,
            name=backend_contact[contact["id"]],
            region=contact["region"],
            material="metal",
            xl=xl,
            xh=xh,
            yl=yl,
            yh=yh,
        )
    interfaces: list[str] = []
    for index, first in enumerate(regions):
        for second in regions[index + 1 :]:
            if {first["material"] == "silicon", second["material"] == "silicon"} == {True, False}:
                touching = (
                    min(first["y1_cm"], second["y1_cm"]) > max(first["y0_cm"], second["y0_cm"])
                    and (
                        abs(first["x1_cm"] - second["x0_cm"]) < _EDGE_TOLERANCE_CM
                        or abs(second["x1_cm"] - first["x0_cm"]) < _EDGE_TOLERANCE_CM
                    )
                ) or (
                    min(first["x1_cm"], second["x1_cm"]) > max(first["x0_cm"], second["x0_cm"])
                    and (
                        abs(first["y1_cm"] - second["y0_cm"]) < _EDGE_TOLERANCE_CM
                        or abs(second["y1_cm"] - first["y0_cm"]) < _EDGE_TOLERANCE_CM
                    )
                )
                if touching:
                    name = f"interface_{first['id']}_{second['id']}"
                    add_2d_interface(
                        mesh=mesh, name=name, region0=first["id"], region1=second["id"]
                    )
                    interfaces.append(name)
    finalize_mesh(mesh=mesh)
    create_device(mesh=mesh, device=device)
    node_count = sum(
        len(get_node_model_values(device=device, region=region["id"], name="x"))
        for region in regions
    )
    print(f"KRONIG 2D mesh: {node_count} nodes", flush=True)
    available = _available_memory_bytes()
    needed = node_count * _BYTES_PER_NODE
    if available is not None and available < needed + _MEMORY_RESERVE_BYTES:
        raise RuntimeError(
            f"a {node_count}-node mesh needs about {needed / 1e9:.1f} GB and only "
            f"{available / 1e9:.1f} GB of memory is free; close other programs or coarsen the mesh"
        )
    if node_count > _MAX_NODES:
        raise RuntimeError(
            f"the mesh has {node_count} nodes, above the {_MAX_NODES} this machine can solve; "
            "coarsen the requested mesh spacing"
        )

    silicon =[region for region in regions if region["material"] == "silicon"]
    insulators = [region for region in regions if region["material"] != "silicon"]
    thermal_voltage = _BOLTZMANN_EV_PER_K * temperature
    band_gap = 1.17 - 4.73e-4 * temperature * temperature / (temperature + 636.0)
    density_scale = (temperature / 300.0) ** 1.5
    conduction_density = float(physics["effective_density_conduction_cm3"]) * density_scale
    valence_density = float(physics["effective_density_valence_cm3"]) * density_scale
    intrinsic_density = math.sqrt(conduction_density * valence_density) * math.exp(
        -band_gap / (2.0 * thermal_voltage)
    )
    affinity = float(physics["electron_affinity_ev"])
    intrinsic_work_function = (
        affinity + 0.5 * band_gap + 0.5 * thermal_voltage * math.log(
            conduction_density / valence_density
        )
    )
    srh_on = "srh" in models
    set_parameter(device=device, name="FermiBlend", value=0.0)

    if fermi:
        statistics = _statistics()
        statistical_models = statistics.NativeStatistics(devsim)
        native_node_creator = CreateNodeModel
        native_edge_creator = CreateEdgeModel
        native_contact_creator = CreateContactNodeModel

        def CreateNodeModel(device: str, region: str, model: str, expression: str) -> None:  # noqa: N802
            native_node_creator(
                device, region, model, statistical_models.node_expression(device, region, expression)
            )

        def CreateNodeModelDerivative(  # noqa: N802
            device: str, region: str, model: str, expression: str, *variables: str
        ) -> None:
            for variable in variables:
                statistical_models.create_derivative(
                    "node", {"device": device, "region": region}, model, expression, variable
                )

        def CreateEdgeModel(device: str, region: str, model: str, expression: str) -> None:  # noqa: N802
            native_edge_creator(device, region, model, statistics.rewrite_inverse(expression))

        def CreateEdgeModelDerivatives(  # noqa: N802
            device: str, region: str, model: str, expression: str, variable: str
        ) -> None:
            for endpoint in ("n0", "n1"):
                statistical_models.create_derivative(
                    "edge",
                    {"device": device, "region": region},
                    model,
                    expression,
                    f"{variable}@{endpoint}",
                )

        def CreateContactNodeModel(device: str, contact: str, model: str, expression: str) -> None:  # noqa: N802
            region = devsim.get_region_list(device=device, contact=contact)[0]
            native_contact_creator(
                device, contact, model, statistical_models.node_expression(device, region, expression)
            )

    by_region: dict[str, list[dict[str, Any]]] = {region["id"]: [] for region in regions}
    for profile in payload["profiles"]:
        by_region[profile["region"]].append(profile)

    for region in silicon:
        name = region["id"]
        SetSiliconParameters(device, name, temperature)
        for parameter, value in (
            ("ElectronAffinity", affinity),
            ("BandGap", band_gap),
            ("EffectiveDensityConduction", conduction_density),
            ("EffectiveDensityValence", valence_density),
            ("taun", float(physics["electron_lifetime_s"]) if srh_on else 1.0e30),
            ("taup", float(physics["hole_lifetime_s"]) if srh_on else 1.0e30),
            ("n_i", intrinsic_density),
            ("n1", intrinsic_density),
            ("p1", intrinsic_density),
            ("mu_n", 400.0 * (temperature / 300.0) ** -2.42),
            ("mu_p", 200.0 * (temperature / 300.0) ** -2.20),
            ("vsat_e", 1.0e7),
            ("vsat_h", 1.0e7),
        ):
            set_parameter(device=device, region=name, name=parameter, value=value)
        CreateNodeModel(device, name, "PhysicalDonors", _doping_expression(by_region[name], "donor"))
        CreateNodeModel(
            device, name, "PhysicalAcceptors", _doping_expression(by_region[name], "acceptor")
        )
        if "klaassen_mobility" in models:
            CreateNodeModel(device, name, "Donors", "max(PhysicalDonors, 1)")
            CreateNodeModel(device, name, "Acceptors", "max(PhysicalAcceptors, 1)")
        else:
            CreateNodeModel(device, name, "Donors", "PhysicalDonors")
            CreateNodeModel(device, name, "Acceptors", "PhysicalAcceptors")
        CreateNodeModel(device, name, "NetDoping", "PhysicalDonors-PhysicalAcceptors")
        CreateSolution(device, name, "Potential")
        CreateSiliconPotentialOnly(device, name)
        CreateNodeModel(device, name, "BandGapNarrowing", "0")
        CreateNodeModel(device, name, "EffectiveIntrinsicDensity", "n_i")
        CreateNodeModel(device, name, "EffectiveBandGap", "BandGap-BandGapNarrowing")
        if fermi:
            electron_eta = (
                "(Potential-0.5*EffectiveBandGap-0.5*V_t*log(EffectiveDensityConduction/"
                "EffectiveDensityValence))/V_t"
            )
            hole_eta = (
                "(-Potential-0.5*EffectiveBandGap+0.5*V_t*log(EffectiveDensityConduction/"
                "EffectiveDensityValence))/V_t"
            )
            for model, expression in (
                (
                    "IntrinsicElectrons",
                    "(1-FermiBlend)*EffectiveIntrinsicDensity*exp(Potential/V_t)+"
                    f"FermiBlend*EffectiveDensityConduction*Fermi({electron_eta})",
                ),
                (
                    "IntrinsicHoles",
                    "(1-FermiBlend)*EffectiveIntrinsicDensity*exp(-Potential/V_t)+"
                    f"FermiBlend*EffectiveDensityValence*Fermi({hole_eta})",
                ),
            ):
                CreateNodeModel(device, name, model, expression)
                CreateNodeModelDerivative(device, name, model, expression, "Potential")
    for region in insulators:
        name = region["id"]
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

    contact_offsets = {contact["id"]: float(contact["voltage_offset_v"]) for contact in contacts}
    carrier_targets: dict[str, tuple[float, float]] = {}
    for contact in contacts:
        region = by_id[contact["region"]]
        native = backend_contact[contact["id"]]
        set_parameter(device=device, name=GetContactBiasName(native), value=0.0)
        if region["material"] == "silicon" and contact["kind"] == "ohmic" and fermi:
            region_name = region["id"]
            if not InEdgeModelList(device, region_name, "contactcharge_edge"):
                CreateEdgeModel(
                    device, region_name, "contactcharge_edge", "Permittivity*ElectricField"
                )
                CreateEdgeModelDerivatives(
                    device, region_name, "contactcharge_edge", "Permittivity*ElectricField", "Potential"
                )
            xl, xh, yl, yh = contact_box(contact, region)
            net = net_doping_at(by_region[region_name], 0.5 * (xl + xh), 0.5 * (yl + yh))
            electrons, holes, potential = fermi_contact_state(
                net_doping_cm3=net,
                conduction_density_cm3=conduction_density,
                valence_density_cm3=valence_density,
                band_gap_ev=band_gap,
                thermal_voltage_v=thermal_voltage,
            )
            if net >= 0:
                boltzmann_electrons = 0.5 * (
                    net + math.sqrt(net * net + 4.0 * intrinsic_density * intrinsic_density)
                )
            else:
                majority_holes = 0.5 * (
                    -net + math.sqrt(net * net + 4.0 * intrinsic_density * intrinsic_density)
                )
                boltzmann_electrons = intrinsic_density * intrinsic_density / majority_holes
            boltzmann_potential = thermal_voltage * math.log(boltzmann_electrons / intrinsic_density)
            carrier_targets[contact["id"]] = (electrons, holes)
            model_name = GetContactNodeModelName(native)
            model = (
                f"Potential-{GetContactBiasName(native)}-"
                f"((1-FermiBlend)*{boltzmann_potential:.17e}+FermiBlend*{potential:.17e})"
            )
            CreateContactNodeModel(device, native, model_name, model)
            CreateContactNodeModel(device, native, f"{model_name}:Potential", "1")
            contact_equation(
                device=device,
                contact=native,
                name="PotentialEquation",
                node_model=model_name,
                edge_charge_model="contactcharge_edge",
            )
        elif region["material"] == "silicon" and contact["kind"] == "ohmic":
            CreateSiliconPotentialOnlyContact(device, region["id"], native)
        elif region["material"] != "silicon" and contact["kind"] in {
            "ideal_gate",
            "metal_work_function",
        }:
            CreateOxideContact(device, region["id"], native)
            offset = 0.0
            if contact.get("work_function_ev") is not None:
                offset = intrinsic_work_function - float(contact["work_function_ev"])
            model_name = GetContactNodeModelName(native)
            model = f"Potential-{GetContactBiasName(native)}-({offset:.17g})"
            CreateContactNodeModel(device, native, model_name, model)
            CreateContactNodeModelDerivative(device, native, model_name, model, "Potential")
        else:
            raise ValueError("contact kind is incompatible with its adjacent material")
    for name in interfaces:
        CreateSiliconOxideInterface(device, name)

    events: list[str] = []

    def run_solve(absolute: float) -> bool:
        try:
            result = solve(
                type="dc",
                absolute_error=absolute,
                relative_error=min(float(solver_settings["relative_error"]), 1.0e-8),
                maximum_iterations=max(int(solver_settings["maximum_iterations"]), 100),
                info=True,
            )
        except devsim.error as exc:  # type: ignore[attr-defined]
            events.append(f"solve failed: {str(exc).splitlines()[0][:120]}")
            return False
        return bool(result["converged"])

    if not run_solve(float(solver_settings["electrostatic_absolute_error"])):
        raise RuntimeError("the initial electrostatic solve did not converge")
    if fermi:
        advance_blend(
            lambda blend: set_parameter(device=device, name="FermiBlend", value=blend),
            lambda: run_solve(float(solver_settings["electrostatic_absolute_error"])),
            events,
        )

    drift_diffusion = {"electron_continuity", "hole_continuity"} <= set(physics["equations"])
    carrier_error = float(solver_settings["carrier_absolute_error"])
    if drift_diffusion:
        if "klaassen_mobility" in models:
            from devsim.python_packages.Klaassen import (  # type: ignore[import-untyped]
                Klaassen_Mobility,
                Set_Mobility_Parameters,
            )
        for region in silicon:
            name = region["id"]
            CreateSolution(device, name, "Electrons")
            CreateSolution(device, name, "Holes")
            set_node_values(device=device, region=name, name="Electrons", init_from="IntrinsicElectrons")
            set_node_values(device=device, region=name, name="Holes", init_from="IntrinsicHoles")
            electron_mobility, hole_mobility = "mu_n", "mu_p"
            if "klaassen_mobility" in models:
                Set_Mobility_Parameters(device, name)
                Klaassen_Mobility(device, name)
                electron_mobility, hole_mobility = "mu_bulk_e", "mu_bulk_h"
            if "high_field_saturation" in models:
                CreateEdgeModel(
                    device,
                    name,
                    "HighFieldElectronMobility",
                    f"2*{electron_mobility}/(1+pow(1+4*pow({electron_mobility}*"
                    "abs(ElectricField)/vsat_e, 2), 0.5))",
                )
                CreateEdgeModel(
                    device,
                    name,
                    "HighFieldHoleMobility",
                    f"2*{hole_mobility}/(1+pow(1+4*pow({hole_mobility}*"
                    "abs(ElectricField)/vsat_h, 2), 0.5))",
                )
                electron_mobility, hole_mobility = (
                    "HighFieldElectronMobility",
                    "HighFieldHoleMobility",
                )
            CreateSiliconDriftDiffusion(device, name, electron_mobility, hole_mobility)
            if fermi:
                # The same degenerate statistics in transport and in recombination, so detailed
                # balance holds: currents follow the gradient of the quasi-Fermi energies.
                for model, expression in {
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
                    "RecombinationDriving": "Electrons*Holes*CarrierAffinity/B(-CarrierAffinity)",
                }.items():
                    CreateNodeModel(device, name, model, expression)
                    CreateNodeModelDerivative(device, name, model, expression, "Electrons", "Holes")
                srh = (
                    "RecombinationDriving/(taup*(Electrons+ElectronDegeneracy*"
                    "EffectiveIntrinsicDensity)+taun*(Holes+HoleDegeneracy*EffectiveIntrinsicDensity))"
                    if srh_on
                    else "0"
                )
                for model, expression in (
                    ("USRH", srh),
                    ("TotalRecombination", "USRH"),
                    ("ElectronGeneration", "-ElectronCharge*USRH"),
                    ("HoleGeneration", "ElectronCharge*USRH"),
                ):
                    CreateNodeModel(device, name, model, expression)
                    CreateNodeModelDerivative(device, name, model, expression, "Electrons", "Holes")
                energy_gap = "0.5*BandGap+0.5*V_t*log(EffectiveDensityConduction/EffectiveDensityValence)"
                electron_energy = {
                    side: (
                        f"(-Potential@{side}+{energy_gap}+V_t*InvFermi("
                        f"Electrons@{side}/EffectiveDensityConduction))"
                    )
                    for side in ("n0", "n1")
                }
                hole_energy = {
                    side: (
                        f"(-Potential@{side}-0.5*BandGap+0.5*V_t*log(EffectiveDensityConduction/"
                        f"EffectiveDensityValence)-V_t*InvFermi(Holes@{side}/EffectiveDensityValence))"
                    )
                    for side in ("n0", "n1")
                }
                for model, mobility, density, energy in (
                    ("ElectronCurrent", electron_mobility, "Electrons", electron_energy),
                    ("HoleCurrent", hole_mobility, "Holes", hole_energy),
                ):
                    expression = (
                        f"ElectronCharge*{mobility}*0.5*({density}@n0+{density}@n1)*"
                        f"EdgeInverseLength*(({energy['n1']})-({energy['n0']}))"
                    )
                    CreateEdgeModel(device, name, model, expression)
                    for variable in ("Potential", "Electrons", "Holes"):
                        CreateEdgeModelDerivatives(device, name, model, expression, variable)
        for contact in contacts:
            region = by_id[contact["region"]]
            if region["material"] != "silicon":
                continue
            native = backend_contact[contact["id"]]
            if not fermi:
                CreateSiliconDriftDiffusionAtContact(device, region["id"], native)
                continue
            electrons, holes = carrier_targets[contact["id"]]
            for variable, equation_name, target, current in (
                ("Electrons", "ElectronContinuityEquation", electrons, "ElectronCurrent"),
                ("Holes", "HoleContinuityEquation", holes, "HoleCurrent"),
            ):
                model_name = f"{native}_{variable.lower()}_fermi"
                CreateContactNodeModel(device, native, model_name, f"{variable}-{target:.17e}")
                CreateContactNodeModel(device, native, f"{model_name}:{variable}", "1")
                contact_equation(
                    device=device,
                    contact=native,
                    name=equation_name,
                    node_model=model_name,
                    edge_current_model=current,
                )
        if not run_solve(carrier_error):
            raise RuntimeError("the equilibrium drift-diffusion solve did not converge")

    # Band edges and quasi-Fermi levels as node models (energies in eV).
    for region in silicon:
        name = region["id"]
        for model, expression in (
            ("IntrinsicEnergy", "-Potential"),
            (
                "ConductionBandEnergy",
                "IntrinsicEnergy+0.5*BandGap+0.5*V_t*log(EffectiveDensityConduction/EffectiveDensityValence)",
            ),
            (
                "ValenceBandEnergy",
                "IntrinsicEnergy-0.5*BandGap+0.5*V_t*log(EffectiveDensityConduction/EffectiveDensityValence)",
            ),
        ):
            CreateNodeModel(device, name, model, expression)
        if drift_diffusion:
            CreateNodeModel(
                device,
                name,
                "ElectronQuasiFermiEnergy",
                "ConductionBandEnergy+V_t*"
                + (
                    "InvFermi(Electrons/EffectiveDensityConduction)"
                    if fermi
                    else "log(Electrons/EffectiveDensityConduction)"
                ),
            )
            CreateNodeModel(
                device,
                name,
                "HoleQuasiFermiEnergy",
                "ValenceBandEnergy-V_t*"
                + (
                    "InvFermi(Holes/EffectiveDensityValence)"
                    if fermi
                    else "log(Holes/EffectiveDensityValence)"
                ),
            )
            CreateNodeModel(
                device,
                name,
                "SpaceChargeDensity",
                "ElectronCharge*(Holes-Electrons+NetDoping)",
            )
        else:
            CreateNodeModel(
                device, name, "SpaceChargeDensity", "ElectronCharge*(IntrinsicHoles-IntrinsicElectrons+NetDoping)"
            )

    def bias_name(contact: dict[str, Any]) -> str:
        return GetContactBiasName(backend_contact[contact["id"]])

    def current_bias(contact: dict[str, Any]) -> float:
        return float(get_parameter(device=device, name=bias_name(contact)))

    def snapshot() -> dict[tuple[str, str], list[float]]:
        state: dict[tuple[str, str], list[float]] = {}
        for region in regions:
            names = ["Potential"]
            if region["material"] == "silicon" and drift_diffusion:
                names += ["Electrons", "Holes"]
            for variable in names:
                state[(region["id"], variable)] = list(
                    get_node_model_values(device=device, region=region["id"], name=variable)
                )
        return state

    def restore(state: dict[tuple[str, str], list[float]]) -> None:
        for (region_id, variable), values in state.items():
            set_node_values(device=device, region=region_id, name=variable, values=values)

    def ramp(targets: dict[str, float]) -> bool:
        """Move contact biases to ``targets`` in adaptive steps; False if a step cannot be made."""
        by_contact = {contact["id"]: contact for contact in contacts}
        start = {cid: current_bias(by_contact[cid]) for cid in targets}
        span = max((abs(targets[cid] - start[cid]) for cid in targets), default=0.0)
        if span < 1.0e-12:
            return True
        done, step = 0.0, min(_MAX_BIAS_STEP_V, span)
        absolute = carrier_error if drift_diffusion else float(
            solver_settings["electrostatic_absolute_error"]
        )
        while done < span - 1.0e-12:
            take = min(step, span - done)
            saved = snapshot()
            fraction = (done + take) / span
            for cid, target in targets.items():
                set_parameter(
                    device=device,
                    name=bias_name(by_contact[cid]),
                    value=start[cid] + (target - start[cid]) * fraction,
                )
            if run_solve(absolute):
                done += take
                step = min(_MAX_BIAS_STEP_V, step * 1.5)
                continue
            restore(saved)
            for cid in targets:
                set_parameter(
                    device=device,
                    name=bias_name(by_contact[cid]),
                    value=start[cid] + (targets[cid] - start[cid]) * done / span,
                )
            step = take / 2.0
            if step < _MIN_BIAS_STEP_V:
                return False
        return True

    driven = next((contact for contact in contacts if contact["id"] == study.get("contact")), None)
    # Static contact voltages first, then the swept contact from zero.
    static_targets = {
        contact["id"]: contact_offsets[contact["id"]]
        for contact in contacts
        if contact is not driven and abs(contact_offsets[contact["id"]]) > 0.0
    }
    if static_targets and not ramp(static_targets):
        raise RuntimeError("the static contact voltages could not be applied")

    bias_values: list[float] = [float(value) for value in study["points_v"]]
    cuts = payload.get("profile_cuts", [])
    quantity_nodes = {
        "potential": ("Potential", "V", 1.0),
        "electron_density": ("Electrons", "cm^-3", 1.0),
        "hole_density": ("Holes", "cm^-3", 1.0),
        "conduction_band": ("ConductionBandEnergy", "eV", 1.0),
        "valence_band": ("ValenceBandEnergy", "eV", 1.0),
        "electron_quasi_fermi_level": ("ElectronQuasiFermiEnergy", "eV", 1.0),
        "hole_quasi_fermi_level": ("HoleQuasiFermiEnergy", "eV", 1.0),
        "charge_density": ("SpaceChargeDensity", "C/cm^3", 1.0),
        "net_doping": ("NetDoping", "cm^-3", 1.0),
        "donor_concentration": ("PhysicalDonors", "cm^-3", 1.0),
        "acceptor_concentration": ("PhysicalAcceptors", "cm^-3", 1.0),
    }
    labels = {
        "potential": "Electrostatic potential",
        "electron_density": "Electron density",
        "hole_density": "Hole density",
        "conduction_band": "Conduction band energy",
        "valence_band": "Valence band energy",
        "electron_quasi_fermi_level": "Electron quasi-Fermi level",
        "hole_quasi_fermi_level": "Hole quasi-Fermi level",
        "charge_density": "Space charge density",
        "net_doping": "Net doping (donors minus acceptors)",
        "donor_concentration": "Donor concentration",
        "acceptor_concentration": "Acceptor concentration",
        "lattice_temperature": "Lattice temperature",
    }
    requested = set(payload.get("observables", []))
    only_when_requested = {"net_doping", "donor_concentration", "acceptor_concentration"}
    if not drift_diffusion:
        for dropped in ("electron_quasi_fermi_level", "hole_quasi_fermi_level"):
            quantity_nodes.pop(dropped, None)

    grid_um: list[float] = []
    cut_nodes: dict[int, list[int]] = {}

    def cut_positions(depth_cm: float) -> list[tuple[float, int, str]]:
        found: list[tuple[float, int, str]] = []
        for region in silicon:
            xs = list(get_node_model_values(device=device, region=region["id"], name="x"))
            ys = list(get_node_model_values(device=device, region=region["id"], name="y"))
            for index, (px, py) in enumerate(zip(xs, ys, strict=True)):
                if abs(py - depth_cm) < _EDGE_TOLERANCE_CM:
                    found.append((px, index, region["id"]))
        found.sort()
        return found

    cut_layout = [cut_positions(cut["depth_cm"]) for cut in cuts]
    if cut_layout:
        merged = sorted({_tag(item[0]) for layout in cut_layout for item in layout})
        grid_um = [value * 1.0e4 for value in merged]
    operating_points: list[dict[str, Any]] = []
    profiles: dict[str, list[float]] = {}
    validity: dict[str, list[bool]] = {}
    lengths = {
        contact["id"]: contact_length_cm(contact, by_id[contact["region"]]) for contact in contacts
    }

    def record(index: int, bias: float, converged: bool) -> None:
        currents: dict[str, float] = {}
        electron_currents: dict[str, float] = {}
        hole_currents: dict[str, float] = {}
        charges: dict[str, float] = {}
        for contact in contacts:
            region = by_id[contact["region"]]
            native = backend_contact[contact["id"]]
            electron = hole = 0.0
            if drift_diffusion and region["material"] == "silicon":
                electron = get_contact_current(
                    device=device, contact=native, equation="ElectronContinuityEquation"
                )
                hole = get_contact_current(
                    device=device, contact=native, equation="HoleContinuityEquation"
                )
            length = lengths[contact["id"]]
            # A per cm of device depth over the contact length in cm is A/cm^2; x1e4 is A/m^2.
            currents[contact["id"]] = (electron + hole) / length * 1.0e4
            electron_currents[contact["id"]] = electron / length * 1.0e4
            hole_currents[contact["id"]] = hole / length * 1.0e4
            charges[contact["id"]] = (
                get_contact_charge(device=device, contact=native, equation="PotentialEquation")
                / length
                * 1.0e4
            )
        operating_points.append(
            {
                "index": index,
                "state": "converged" if converged else "failed",
                **({} if converged else {"message": "the solver could not reach this bias"}),
                "coordinates": {"bias": float(bias)},
                "terminal_currents_a_per_m2": currents,
                "terminal_electron_currents_a_per_m2": electron_currents,
                "terminal_hole_currents_a_per_m2": hole_currents,
                "terminal_charges_c_per_m2": charges,
            }
        )
        for cut_index, layout in enumerate(cut_layout):
            if not layout:
                continue
            suffix = "" if cut_index == 0 else f"__{cuts[cut_index]['id']}"
            for quantity, (node_model, _unit, scale) in quantity_nodes.items():
                if quantity in only_when_requested and quantity not in requested:
                    continue
                values_by_region = {
                    region["id"]: list(
                        get_node_model_values(device=device, region=region["id"], name=node_model)
                    )
                    for region in silicon
                }
                by_position = {
                    _tag(position): values_by_region[region_id][node_index] * scale
                    for position, node_index, region_id in layout
                }
                profiles.setdefault(quantity + suffix, []).extend(
                    by_position.get(_tag(value / 1.0e4), 0.0) for value in grid_um
                )
                validity.setdefault(quantity + suffix, []).extend(
                    _tag(value / 1.0e4) in by_position for value in grid_um
                )
            temperature_name = "lattice_temperature" + suffix
            profiles.setdefault(temperature_name, []).extend(temperature for _ in grid_um)
            validity.setdefault(temperature_name, []).extend(True for _ in grid_um)

    if study["kind"] == "equilibrium" or driven is None:
        ok = True
        record(0, 0.0, ok)
    else:
        index = 0
        healthy = True
        for bias in bias_values:
            if healthy:
                healthy = ramp({driven["id"]: contact_offsets[driven["id"]] + bias})
            record(index, bias, healthy)
            index += 1

    export_points = [point["coordinates"]["bias"] for point in operating_points]
    datasets: dict[str, Any] = {}
    quantity_meta = {name: (unit, labels[name]) for name, (_m, unit, _s) in quantity_nodes.items()}
    quantity_meta["lattice_temperature"] = ("K", labels["lattice_temperature"])
    for key, flat in profiles.items():
        base = key.split("__", 1)[0]
        unit, label = quantity_meta[base]
        datasets[key] = {
            "id": key,
            "quantity": base,
            "label": label,
            "unit": unit,
            "axes": ["bias", "position"],
            "shape": [len(export_points), len(grid_um)],
            "centering": "node",
            "values": flat,
            **({} if all(validity[key]) else {"validity": validity[key]}),
        }
    width_m = payload.get("width_m")
    for contact in contacts:
        if width_m is None:
            continue
        area = lengths[contact["id"]] * 1.0e-2 * float(width_m)
        for prefix, field in (
            ("absolute_terminal_current", "terminal_currents_a_per_m2"),
            ("absolute_terminal_charge", "terminal_charges_c_per_m2"),
        ):
            name = f"{prefix}__{contact['id']}"
            datasets[name] = {
                "id": name,
                "quantity": prefix,
                "label": f"{prefix.replace('_', ' ').capitalize()} at {contact['id']}",
                "unit": "A" if "current" in prefix else "C",
                "axes": ["bias"],
                "shape": [len(export_points)],
                "centering": "operating_point",
                "values": [point[field][contact["id"]] * area for point in operating_points],
            }
    if not datasets:
        for contact in contacts:
            name = f"terminal_current_density__{contact['id']}"
            datasets[name] = {
                "id": name,
                "quantity": "terminal_current_density",
                "label": f"Terminal current density at {contact['id']}",
                "unit": "A/m^2",
                "axes": ["bias"],
                "shape": [len(export_points)],
                "centering": "operating_point",
                "values": [
                    point["terminal_currents_a_per_m2"][contact["id"]] for point in operating_points
                ],
            }
    axes: dict[str, Any] = {
        "bias": {
            "id": "bias",
            "kind": "bias",
            "label": "Drive voltage",
            "unit": "V",
            "values": [float(value) for value in export_points],
        }
    }
    if grid_um:
        axes["position"] = {
            "id": "position",
            "kind": "position",
            "label": "Position",
            "unit": "um",
            "values": grid_um,
        }
    else:
        for dataset in datasets.values():
            dataset["axes"] = ["bias"]
    input_digest = hashlib.sha256(Path(payload_path).read_bytes()).hexdigest()
    mesh_digest = hashlib.sha256(
        json.dumps([sorted(lateral_lines.items()), sorted(depth_lines.items())]).encode()
    ).hexdigest()
    result = {
        "schema_version": "2.0",
        "simulator_version": f"DEVSIM {devsim.__version__}",
        "status": "completed",
        "terminals": [contact["id"] for contact in contacts],
        "physics_models": sorted(models),
        "native_defaults": [
            "silicon material constants (permittivity, band gap, densities of states)",
            "constant mobility values"
            if "klaassen_mobility" not in models
            else "Klaassen mobility parameters",
        ],
        "provenance": {
            "compiler_version": payload.get("compiler_version", "devsim-2d"),
            "experiment_sha256": input_digest,
            "mesh_sha256": mesh_digest,
        },
        "sign_convention": {
            "terminal_current": "positive_into_device",
            "terminal_charge": "outward_displacement_flux",
        },
        "axes": axes,
        "datasets": datasets,
        "operating_points": operating_points,
    }
    Path("native_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(
        f"KRONIG 2D run finished in {time.time() - started:.1f} s; "
        f"{len(events)} solver retries: {events[:5]}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "input.json"))
