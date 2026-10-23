"""Positive carrier coordinates and equivalent finite-volume conditioning.

No device identities or physical values select an equation. The integrated
row is assembled from the active native generation and boundary models, not
from a rounded sum of large transport entries in the exported double matrix.
"""

from __future__ import annotations

import array
import math
import shlex
import tempfile
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

COORDINATES = {"Electrons": "ElectronDensityPotential", "Holes": "HoleDensityPotential"}
CARRIER_EQUATIONS = {"Electrons": "ElectronContinuityEquation", "Holes": "HoleContinuityEquation"}
VERSION = "kronig.positive-density.conservative-dc.v2"


def replace_conservation_rows(
    ap: Any, ai: Any, ax: Any, rows: dict[int, dict[int, float]]
) -> tuple[Any, Any, Any]:
    size = len(ap) - 1
    if size < 1 or ap[0] != 0 or ap[-1] != len(ai) or len(ai) != len(ax):
        raise ValueError("Invalid sparse matrix dimensions")
    for row, columns in rows.items():
        if not isinstance(row, int) or isinstance(row, bool) or not 0 <= row < size:
            raise ValueError("Invalid conservation row")
        for column, value in columns.items():
            if (
                not isinstance(column, int)
                or isinstance(column, bool)
                or not 0 <= column < size
                or not math.isfinite(value)
            ):
                raise ValueError("Invalid conservation column or coefficient")
    pointers, indices, values = [0], [], []
    for column in range(size):
        if not 0 <= ap[column] <= ap[column + 1] <= len(ai):
            raise ValueError("Invalid sparse matrix column pointer")
        entries: dict[int, list[float]] = {}
        for index in range(ap[column], ap[column + 1]):
            row, value = ai[index], ax[index]
            if not 0 <= row < size or not math.isfinite(value):
                raise ValueError("Invalid sparse matrix entry")
            if row not in rows:
                entries.setdefault(row, []).append(value)
        for row, coefficients in rows.items():
            if column in coefficients:
                entries[row] = [coefficients[column]]
        for row, terms in sorted(entries.items()):
            indices.append(row)
            values.append(math.fsum(terms))
        pointers.append(len(indices))
    return array.array("i", pointers), array.array("i", indices), array.array("d", values)


def conservation_pivot(ap: Any, ai: Any, ax: Any, eligible: Any) -> int:
    candidates = []
    for column in eligible:
        terms = [ax[j] for j in range(ap[column], ap[column + 1]) if ai[j] == column]
        diagonal = abs(math.fsum(terms))
        if math.isfinite(diagonal) and diagonal > 0:
            candidates.append((diagonal, column))
    if not candidates:
        raise ValueError("No finite nonzero physical conservation pivot")
    return max(candidates)[1]


class NativeDensitySolver:
    """DC-only numerical coordinates with unchanged final physical acceptance."""

    def __init__(
        self,
        backend: Any,
        device: str,
        payload: dict[str, Any],
        certificate: Callable[..., dict[str, Any]],
    ) -> None:
        self.backend, self.device, self.payload, self.certificate = (
            backend,
            device,
            payload,
            certificate,
        )
        self.regions = [r["id"] for r in payload["regions"] if r["material"] == "silicon"]
        self.last_scale = 1.0
        if "solver_callback" in backend.get_parameter_list():
            self.original_callback = backend.get_parameter(name="solver_callback")
        else:
            # MKL builds do not install a Python callback automatically. Use the
            # same bundled sparse solver that backs conditioned POSIX solves.
            self.original_callback = import_module("devsim.umfpack.umfshim").local_solver_callback
        self.original_solve = backend.solve
        self.balances: dict[int, float] = {}
        self.eligible: dict[str, list[tuple[str, int]]] = {}
        self.last_certificate: dict[str, Any] | None = None

    def _kw(self, region: str) -> dict[str, str]:
        return {"device": self.device, "region": region}

    def prepare(self) -> None:
        d = self.backend
        # Generic native serialization supplies actual interface expressions.
        # It is diagnostic syntax, never model-generated executable code.
        with tempfile.TemporaryDirectory(prefix="kronig-native-coordinates-") as directory:
            source = Path(directory) / "models.devsim"
            d.write_devices(file=str(source), type="devsim")
            interface_expressions = {}
            for line in source.read_text().splitlines():
                if not line.startswith("COMMAND interface_model "):
                    continue
                words = shlex.split(line)[2:]
                options = dict(zip((v.lstrip("-") for v in words[::2]), words[1::2], strict=True))
                if options["device"] == self.device:
                    interface_expressions[(options["interface"], options["name"])] = options[
                        "equation"
                    ].rstrip(";")
        for region in self.regions:
            kw = self._kw(region)
            nodes, edges = list(d.get_node_model_list(**kw)), list(d.get_edge_model_list(**kw))
            for density, variable in COORDINATES.items():
                dos = (
                    "EffectiveDensityConduction"
                    if density == "Electrons"
                    else "EffectiveDensityValence"
                )
                d.node_model(**kw, name="Initial" + variable, equation=f"V_t*log({density}/{dos})")
                d.node_solution(**kw, name=variable)
                d.set_node_values(**kw, name=variable, init_from="Initial" + variable)
                d.node_model(**kw, name=density, equation=f"{dos}*exp({variable}/V_t)")
                d.node_model(
                    **kw,
                    name="EquilibriumReset" + variable,
                    equation=f"V_t*log(Intrinsic{density}/{dos})",
                )
                d.node_model(**kw, name=f"{density}:{variable}", equation=f"{density}/V_t")
                for name in nodes:
                    if name.endswith(":" + density):
                        d.node_model(
                            **kw,
                            name=name[: -len(density)] + variable,
                            equation=f"{name}*{density}/V_t",
                        )
                for name in edges:
                    for endpoint in ("n0", "n1"):
                        suffix = f":{density}@{endpoint}"
                        if name.endswith(suffix):
                            d.edge_model(
                                **kw,
                                name=name[: -len(suffix)] + f":{variable}@{endpoint}",
                                equation=f"{name}*{density}@{endpoint}/V_t",
                            )
                name = CARRIER_EQUATIONS[density]
                command = d.get_equation_command(**kw, name=name)
                command.update(variable_name=variable, variable_update="default")
                d.delete_equation(**kw, name=name)
                d.equation(**command)
                d.node_solution(**kw, name="PhysicalPrevious" + density)
                d.node_model(
                    **kw,
                    name="PhysicalAbsoluteUpdate" + density,
                    equation=f"abs({density}-PhysicalPrevious{density})",
                )
                d.node_model(
                    **kw,
                    name="PhysicalRelativeUpdate" + density,
                    equation=f"PhysicalAbsoluteUpdate{density}/(abs({density})+1e-10)",
                )
            command = d.get_equation_command(**kw, name="PotentialEquation")
            command["variable_update"] = "default"
            d.equation(**command)
        for interface in d.get_interface_list(device=self.device):
            kw = {"device": self.device, "interface": interface}
            for name in list(d.get_interface_model_list(**kw)):
                for density, variable in COORDINATES.items():
                    for side in ("r0", "r1"):
                        suffix = f":{density}@{side}"
                        if name.endswith(suffix):
                            base = name[: -len(suffix)]
                            expression = interface_expressions[(interface, base)]
                            d.interface_model(
                                **kw,
                                name=base + f":{variable}@{side}",
                                equation=f"diff({expression},{variable}@{side})",
                            )
            for name in d.get_interface_equation_list(**kw):
                command = d.get_interface_equation_command(**kw, name=name)
                d.delete_interface_equation(**kw, name=name)
                d.interface_equation(**command)
        for contact in d.get_contact_list(device=self.device):
            kw = {"device": self.device, "contact": contact}
            for name in d.get_contact_equation_list(**kw):
                command = d.get_contact_equation_command(**kw, name=name)
                d.delete_contact_equation(**kw, name=name)
                d.contact_equation(**command)
        self._prepare_balance_eligibility()
        self._prepare_predictor()
        d.set_parameter(name="solver_callback", value=self._callback)
        d.set_parameter(name="direct_solver", value="custom")

    def _prepare_balance_eligibility(self) -> None:
        d = self.backend
        # Sum physical continuity rows, never Dirichlet carrier constraints.
        # Insulating contacts have no carrier equation or terminal flux.
        self.dirichlet_nodes: dict[str, set[int]] = {region: set() for region in self.regions}
        flux_boundary = False
        for interface in d.get_interface_list(device=self.device):
            kw = {"device": self.device, "interface": interface}
            for name in d.get_interface_equation_list(**kw):
                if (
                    name in CARRIER_EQUATIONS.values()
                    and d.get_interface_equation_command(**kw, name=name)["type"] != "continuous"
                ):
                    return
        for contact in self.payload["contacts"]:
            for name in CARRIER_EQUATIONS.values():
                if name not in d.get_contact_equation_list(
                    device=self.device, contact=contact["backend_id"]
                ):
                    continue
                command = d.get_contact_equation_command(
                    device=self.device, contact=contact["backend_id"], name=name
                )
                if (
                    not (command["edge_model"] or command["edge_current_model"])
                    or command["edge_volume_model"]
                    or command["element_model"]
                    or command["circuit_node"]
                ):
                    return
                if command["node_model"]:
                    if contact["kind"] != "ohmic":
                        return
                    region = d.get_region_list(
                        device=self.device, contact=contact["backend_id"]
                    )[0]
                    count = len(d.get_node_model_values(**self._kw(region), name="NodeVolume"))
                    self.dirichlet_nodes[region].add(
                        0 if contact["location"] == "x_min" else count - 1
                    )
                else:
                    flux_boundary = True
        original_flux_scope = len(self.regions) == len(self.payload["regions"]) and all(
            contact["kind"] == "metal_work_function" for contact in self.payload["contacts"]
        )
        single_reservoir_scope = (
            len(self.regions) == 1
            and sum(map(len, self.dirichlet_nodes.values())) == 1
            and not flux_boundary
        )
        # Mixed flux/Dirichlet boundaries retain ordinary assembly. Their
        # contact-source conventions are not the single-reservoir balance.
        if not (original_flux_scope or single_reservoir_scope):
            return
        assembled = d.get_matrix_and_rhs(format="csc")
        for equation in CARRIER_EQUATIONS.values():
            eligible = [
                (region, index)
                for region in self.regions
                for index, number in enumerate(
                    d.get_equation_numbers(**self._kw(region), equation=equation)
                )
                if assembled["permutation"]["row"][number] == number
                and index not in self.dirichlet_nodes[region]
            ]
            if eligible:
                self.eligible[equation] = eligible

    def _unknowns(self) -> dict[str, dict[str, list[int]]]:
        d = self.backend
        return {
            region: {
                d.get_equation_command(**self._kw(region), name=name)["variable_name"]: list(
                    d.get_equation_numbers(**self._kw(region), equation=name)
                )
                for name in d.get_equation_list(**self._kw(region))
            }
            for region in self.regions
        }

    def _balance(
        self, equation: str, unknowns: dict[str, dict[str, list[int]]]
    ) -> tuple[float, dict[int, float]]:
        d, terms, derivatives = self.backend, [], {}

        def add(column: int, value: float) -> None:
            if not math.isfinite(value):
                raise ValueError("Nonfinite integrated physical source")
            derivatives.setdefault(column, []).append(value)

        for region in self.regions:
            kw = self._kw(region)
            command = d.get_equation_command(**kw, name=equation)
            if command["edge_volume_model"] or command["element_model"]:
                raise ValueError("Unbenchmarked source semantics for integrated balance")
            model, volume = (
                command["node_model"],
                list(d.get_node_model_values(**kw, name="NodeVolume")),
            )
            for index in self.dirichlet_nodes[region]:
                volume[index] = 0
            if model:
                values = d.get_node_model_values(**kw, name=model)
                terms.extend(a * b for a, b in zip(values, volume, strict=True))
                known = set(d.get_node_model_list(**kw))
                for variable, numbers in unknowns[region].items():
                    derivative = model + ":" + variable
                    if derivative in known:
                        values = d.get_node_model_values(**kw, name=derivative)
                        for column, a, b in zip(numbers, values, volume, strict=True):
                            add(column, a * b)
        for contact in self.payload["contacts"]:
            if equation not in d.get_contact_equation_list(
                device=self.device, contact=contact["backend_id"]
            ):
                continue
            region = d.get_region_list(device=self.device, contact=contact["backend_id"])[0]
            kw = self._kw(region)
            command = d.get_contact_equation_command(
                device=self.device, contact=contact["backend_id"], name=equation
            )
            model = command["edge_model"] or command["edge_current_model"]
            count = len(next(iter(unknowns[region].values())))
            edge, sign = (0, 1) if contact["location"] == "x_min" else (count - 2, -1)
            couple = sign * d.get_edge_model_values(**kw, name="EdgeCouple")[edge]
            terms.append(couple * d.get_edge_model_values(**kw, name=model)[edge])
            known = set(d.get_edge_model_list(**kw))
            for variable, numbers in unknowns[region].items():
                for side, index in (("n0", edge), ("n1", edge + 1)):
                    derivative = f"{model}:{variable}@{side}"
                    if derivative in known:
                        add(
                            numbers[index],
                            couple * d.get_edge_model_values(**kw, name=derivative)[edge],
                        )
        residual = math.fsum(terms)
        if not math.isfinite(residual):
            raise ValueError("Nonfinite integrated carrier residual")
        return residual, {column: math.fsum(values) for column, values in derivatives.items()}

    def _callback(self, **arguments: Any) -> dict[str, Any]:
        d = self.backend
        if arguments["action"] in {"factor", "solve"} and not self.carriers_active():
            return self.original_callback(**arguments)
        if not arguments.get("is_complex", False) and arguments["action"] == "factor":
            unknowns, rows = self._unknowns(), {}
            self.balances.clear()
            for equation, eligible in self.eligible.items():
                numbers = {
                    region: list(d.get_equation_numbers(**self._kw(region), equation=equation))
                    for region in self.regions
                }
                pivot = conservation_pivot(
                    arguments["Ap"],
                    arguments["Ai"],
                    arguments["Ax"],
                    [numbers[region][index] for region, index in eligible],
                )
                residual, derivatives = self._balance(equation, unknowns)
                self.balances[pivot], rows[pivot] = -residual, derivatives
            if rows:
                pointers, indices, values = replace_conservation_rows(
                    arguments["Ap"], arguments["Ai"], arguments["Ax"], rows
                )
                arguments.update(Ap=pointers, Ai=indices, Ax=values, is_same_symbolic=False)
        elif not arguments.get("is_complex", False) and arguments["action"] == "solve":
            rhs = array.array("d", arguments["b"])
            for row, value in self.balances.items():
                rhs[row] = value
            arguments["b"] = rhs
            for region in self.regions:
                for density in COORDINATES:
                    d.set_node_values(
                        **self._kw(region), name="PhysicalPrevious" + density, init_from=density
                    )
        result = self.original_callback(**arguments)
        if arguments["action"] == "solve" and not arguments["is_complex"]:
            step = result["x"]
            if not all(math.isfinite(value) for value in step):
                raise ValueError("Nonfinite Newton direction")
            maximum = max(abs(value) for value in step)
            thermal = min(
                d.get_parameter(**self._kw(region), name="V_t") for region in self.regions
            )
            self.last_scale = min(1.0, 4 * thermal / maximum) if maximum else 1.0
            if self.last_scale < 1:
                result["x"] = array.array("d", (value * self.last_scale for value in step))
        return result

    def carriers_active(self) -> bool:
        return all(
            set(CARRIER_EQUATIONS.values())
            <= set(self.backend.get_equation_list(**self._kw(region)))
            for region in self.regions
        )

    def reset_equilibrium_densities(self) -> None:
        for region in self.regions:
            for variable in COORDINATES.values():
                self.backend.set_node_values(
                    **self._kw(region), name=variable, init_from="EquilibriumReset" + variable
                )

    def _evidence(self) -> tuple[dict[str, Any], dict[str, Any]]:
        d, states, updates = self.backend, {}, {}
        for region in self.regions:
            kw, state, update = self._kw(region), {}, {}
            for density, field in (
                ("Electrons", "electron_density_max"),
                ("Holes", "hole_density_max"),
            ):
                values = d.get_node_model_values(**kw, name=density)
                if not values or not all(math.isfinite(value) and value > 0 for value in values):
                    raise ValueError("Invalid native carrier density evidence")
                state[field] = max(values)
                errors = {}
                for model, label in (
                    ("PhysicalAbsoluteUpdate", "absolute_error"),
                    ("PhysicalRelativeUpdate", "relative_error"),
                ):
                    values = d.get_node_model_values(**kw, name=model + density)
                    if not values or not all(
                        math.isfinite(value) and value >= 0 for value in values
                    ):
                        raise ValueError("Invalid native density update evidence")
                    errors[label] = max(values)
                update[CARRIER_EQUATIONS[density]] = errors
            state["thermal_voltage_min"] = d.get_parameter(**kw, name="V_t")
            states[region], updates[region] = state, update
        return states, updates

    def solve(self, **arguments: Any) -> dict[str, Any] | None:
        if arguments.get("type") != "dc":
            raise ValueError("Positive-density conditioning is benchmarked for DC only")
        absolute, relative = float(arguments["absolute_error"]), float(arguments["relative_error"])
        remaining = int(arguments["maximum_iterations"])
        thermal = min(
            self.backend.get_parameter(**self._kw(region), name="V_t") for region in self.regions
        )
        coordinate_limit = thermal * math.log1p(relative / (2 * len(self.regions)))
        want_info = bool(arguments.get("info", False))
        while remaining > 0:
            options = dict(
                arguments,
                info=True,
                absolute_error=coordinate_limit,
                relative_error=1e100,
                maximum_iterations=remaining,
            )
            info = self.original_solve(**options)
            iterations = info.get("iterations", ())
            if not iterations or not info.get("converged"):
                raise RuntimeError("Native positive-density Newton solve did not converge")
            remaining -= len(iterations)
            states, updates = self._evidence()
            audit = self.certificate(
                iterations[-1],
                states,
                density_updates=updates,
                absolute_limit=absolute,
                relative_limit=relative,
            )
            self.last_certificate = dict(audit, final_step_scale=self.last_scale)
            if audit["passed"] and self.last_scale == 1.0:
                return info if want_info else None
            coordinate_limit *= min(
                0.5,
                0.5 * absolute / max(audit["absolute_error_bound"], 1e-300),
                0.5 * relative / max(audit["relative_error_bound"], 1e-300),
            )
        raise RuntimeError("Original physical-density convergence allowance exhausted")

    def _prepare_predictor(self) -> None:
        d = self.backend
        regions = self.payload["regions"]
        resistances = [
            (r["x1_cm"] - r["x0_cm"]) / d.get_parameter(**self._kw(r["id"]), name="Permittivity")
            for r in regions
        ]
        total, before = math.fsum(resistances), 0.0
        if total <= 0 or not math.isfinite(total):
            raise ValueError("Invalid native electrostatic predictor geometry")
        d.set_parameter(device=self.device, name="NumericalPredictorDelta", value=0.0)
        d.set_parameter(device=self.device, name="NumericalPredictorLeft", value=1.0)
        for region, resistance in zip(regions, resistances, strict=True):
            length = region["x1_cm"] - region["x0_cm"]
            fraction = (
                f"({before:.17g}+{resistance:.17g}*(x-{region['x0_cm']:.17g})"
                f"/{length:.17g})/{total:.17g}"
            )
            d.node_model(
                **self._kw(region["id"]),
                name="NumericalPredictedPotential",
                equation=f"Potential+NumericalPredictorDelta*ifelse(NumericalPredictorLeft,1-({fraction}),({fraction}))",
            )
            before += resistance

    def predict_voltage(self, delta: float, location: str) -> None:
        if not math.isfinite(delta) or location not in {"x_min", "x_max"}:
            raise ValueError("Invalid numerical voltage predictor")
        d = self.backend
        d.set_parameter(device=self.device, name="NumericalPredictorDelta", value=delta)
        d.set_parameter(
            device=self.device, name="NumericalPredictorLeft", value=float(location == "x_min")
        )
        for region in self.payload["regions"]:
            d.set_node_values(
                **self._kw(region["id"]), name="Potential", init_from="NumericalPredictedPotential"
            )
