"""Deterministic compiler for the reviewed Sentaurus Device subset."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from importlib.resources import files
from pathlib import Path
from typing import Literal

from jinja2 import Environment, StrictUndefined

from tcad_agent.adapters.sentaurus.mesh import (
    MESH_GENERATION,
    MESH_GENERATION_2D,
    build_run_script,
    build_sde_script,
    slab_height_um,
)
from tcad_agent.adapters.sentaurus.normalizer import SentaurusNormalizer
from tcad_agent.adapters.sentaurus.runtime import (
    ESCALATION_DECKS,
    MINIMUM_DIGITS,
    MINIMUM_ITERATIONS,
    NativeOperatingPoint,
    NativeReview,
    SentaurusJobManifest,
    SourceLocation,
)
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import _OBSERVABLE_MODELS, CapabilityService
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import (
    Contact,
    ContactKind,
    DCStudy,
    Equation,
    ExperimentSpec,
    Observable,
    SolverControls,
)
from tcad_agent.domain.studies import DCPointsStudy, expand_study_points
from tcad_agent.results.models import CanonicalResult
from tcad_agent.runners.models import CompiledJob, NativeRunResult

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_SAFE_LABEL = re.compile(r"[^\x00-\x1f\x7f/\\;`$|&<>\"']{1,300}")
_MODEL_LINES = {
    "boltzmann": (),
    "fermi": ("Fermi",),
    "constant_mobility": (),
    "klaassen_mobility": ("PhuMob",),
    "high_field_saturation": ("HighFieldSaturation",),
    "srh": (),
    "auger": (),
    "band_gap_narrowing": ("EffectiveIntrinsicDensity( OldSlotboom )",),
    "slotboom_bgn": ("EffectiveIntrinsicDensity( OldSlotboom )",),
}
_PLOT_FIELDS = {
    Observable.POTENTIAL: ("Potential",),
    Observable.ELECTRIC_FIELD: ("ElectricField/Vector",),
    Observable.ELECTRON_DENSITY: ("eDensity",),
    Observable.HOLE_DENSITY: ("hDensity",),
    Observable.CHARGE_DENSITY: ("SpaceCharge",),
    Observable.CONDUCTION_BAND: ("ConductionBandEnergy",),
    Observable.VALENCE_BAND: ("ValenceBandEnergy",),
    Observable.FERMI_LEVEL: ("eQuasiFermiEnergy", "hQuasiFermiEnergy"),
    Observable.ELECTRON_QUASI_FERMI_LEVEL: ("eQuasiFermiEnergy",),
    Observable.HOLE_QUASI_FERMI_LEVEL: ("hQuasiFermiEnergy",),
    Observable.ELECTRON_CURRENT_DENSITY: ("eCurrent/Vector",),
    Observable.HOLE_CURRENT_DENSITY: ("hCurrent/Vector",),
    Observable.ELECTRON_MOBILITY: ("eMobility",),
    Observable.HOLE_MOBILITY: ("hMobility",),
    Observable.RECOMBINATION_RATE: ("TotalRecombination",),
    Observable.SRH_RECOMBINATION_RATE: ("SRHRecombination",),
    Observable.AUGER_RECOMBINATION_RATE: ("AugerRecombination",),
    Observable.NET_DOPING: ("Doping",),
    Observable.DONOR_CONCENTRATION: ("DonorConcentration",),
    Observable.ACCEPTOR_CONCENTRATION: ("AcceptorConcentration",),
    Observable.BAND_GAP: ("BandGap",),
    Observable.BAND_GAP_NARROWING: ("BandGapNarrowing",),
    Observable.ELECTRON_AFFINITY: ("ElectronAffinity",),
    Observable.EFFECTIVE_INTRINSIC_CARRIER_CONCENTRATION: ("EffectiveIntrinsicDensity",),
    Observable.TOTAL_CURRENT_DENSITY: ("TotalCurrent/Vector",),
    Observable.LATTICE_TEMPERATURE: ("LatticeTemperature",),
    Observable.TERMINAL_CURRENT: (),
    Observable.TERMINAL_CURRENT_DENSITY: (),
    Observable.ABSOLUTE_TERMINAL_CURRENT: (),
    Observable.TERMINAL_CHARGE: (),
}


_ITERATIVE = ("Method=Blocked", "SubMethod=ILS")


class SentaurusCompilerSafetyError(ValueError):
    """Raised when normalized input cannot safely enter a native deck."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_number(value: float) -> str:
    if value == 0:
        return "0"
    return format(value, ".15g")


def _combined_digest(files_by_name: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(files_by_name):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(files_by_name[name])
        digest.update(b"\0")
    return digest.hexdigest()


class SentaurusAdapter:
    compiler_version = "0.2.0"

    def __init__(
        self, manifest: CapabilityManifest, mesh_mode: Literal["external", "sde"] = "external"
    ) -> None:
        self._manifest = manifest
        self._mesh_mode = mesh_mode

    @property
    def manifest(self) -> CapabilityManifest:
        return self._manifest

    @classmethod
    def from_defaults(cls, mesh_mode: Literal["external", "sde"] = "external") -> SentaurusAdapter:
        return cls(CapabilityManifest.from_backend("sentaurus"), mesh_mode)

    def compile(self, spec: ExperimentSpec, workspace: Path) -> CompiledJob:
        decision = CapabilityService().check(spec, self.manifest)
        if decision.status is not CapabilityStatus.SUPPORTED:
            details = "; ".join(f"{issue.path}: {issue.message}" for issue in decision.issues)
            raise CapabilityError(details)
        self._validate_safe_subset(spec)

        template_bytes = (
            files("tcad_agent.adapters.sentaurus").joinpath("templates/sdevice.cmd.j2").read_bytes()
        )
        template_text = template_bytes.decode()
        context = self._context(spec)
        environment = Environment(
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
            newline_sequence="\n",
        )
        command_text = environment.from_string(template_text).render(**context)
        self._lint_generated(command_text)
        command_bytes = command_text.encode()
        experiment_bytes = (json.dumps(spec.normalized(), sort_keys=True, indent=2) + "\n").encode()

        source_map = self._source_map(spec, command_text)
        point_count = max(1, len(expand_study_points(spec.study)))
        inputs = {
            "experiment.json": _sha256(experiment_bytes),
            "sdevice.cmd": _sha256(command_bytes),
        }
        extra: dict[str, bytes] = {}
        mesh_fields: dict[str, object] = {}
        if self._mesh_mode == "sde":
            version = os.getenv("TCAD_SENTAURUS_VERSION", "").strip()
            if not version:
                raise CapabilityError(
                    "TCAD_SENTAURUS_VERSION must name the exact Sentaurus release for this host"
                )
            extra = {
                "mesh.scm": build_sde_script(spec).encode(),
                "run.sh": build_run_script().encode(),
            }
            for deck_name, variant in zip(
                ESCALATION_DECKS, self._escalations(context), strict=True
            ):
                deck_text = environment.from_string(template_text).render(**variant)
                self._lint_generated(deck_text)
                extra[deck_name] = deck_text.encode()
            parameter_file = self._parameter_file(spec)
            if parameter_file is not None:
                extra["sdevice.par"] = parameter_file.encode()
            inputs.update({name: _sha256(content) for name, content in extra.items()})
            mesh_fields = {
                "mesh_generation": MESH_GENERATION_2D if spec.dimension == 2 else MESH_GENERATION,
                "required_runtime_inputs": (),
                "slab_height_um": None if spec.dimension == 2 else slab_height_um(spec),
                "expected_outputs": tuple(
                    f"point_{index:04d}_des.tdr" for index in range(point_count)
                ),
                "native_review": NativeReview(
                    simulator_version=version,
                    reference="automatic structure-editor unit-slab mesh; not human-reviewed",
                ),
            }
        else:
            mesh_fields = {"expected_outputs": ("sdevice.log", "sdevice.plt", "sdevice.tdr")}
        manifest = SentaurusJobManifest(
            compiler_version=self.compiler_version,
            inputs=inputs,
            source_map=source_map,
            **mesh_fields,
            operating_points=tuple(
                NativeOperatingPoint(
                    index=index,
                    bias_v=point.to("V"),
                    contact=spec.study.contact,
                    profile_prefix=f"point_{index:04d}",
                )
                for index, point in enumerate(expand_study_points(spec.study))
            ),
        )
        manifest_bytes = (
            json.dumps(manifest.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
        ).encode()
        generated = {
            "experiment.json": experiment_bytes,
            "job-manifest.json": manifest_bytes,
            "sdevice.cmd": command_bytes,
            **extra,
        }

        workspace = workspace.resolve()
        workspace.mkdir(parents=True, exist_ok=False)
        for name, content in generated.items():
            (workspace / name).write_bytes(content)
        runtime_digest = _combined_digest(
            {
                "compiler-version": self.compiler_version.encode(),
                "sdevice.cmd.j2": template_bytes,
                "registry": json.dumps(
                    {
                        "models": _MODEL_LINES,
                        "plots": {str(key): value for key, value in _PLOT_FIELDS.items()},
                    },
                    sort_keys=True,
                ).encode(),
                "mesh-mode": self._mesh_mode.encode(),
                "run-script": build_run_script().encode(),
            }
        )
        return CompiledJob(
            backend="sentaurus",
            entrypoint=workspace / "sdevice.cmd",
            arguments=(),
            environment={},
            input_files=tuple(workspace / name for name in sorted(generated)),
            input_digest=_combined_digest(generated),
            runtime_digest=runtime_digest,
            compiler_version=self.compiler_version,
        )

    @staticmethod
    def _escalations(context: dict[str, object]) -> list[dict[str, object]]:
        """The same experiment with the next numerical strategies, tried only if a ramp stalls."""
        iterative = list(_ITERATIVE)
        iterations = max(int(context["iterations"]), 300)  # type: ignore[call-overload]
        if context["math_lines"]:
            # Already iterative (two-dimensional): continue ramps without the restart solve,
            # loosen precision, and finally try the direct solver.
            first = {**context, "skip_start_solve": True}
            return [first, {**first, "digits": 6}, {**first, "math_lines": []}]
        first = {**context, "math_lines": iterative, "iterations": iterations}
        # A ramp restarts by re-solving its converged starting point; on a fine mesh that
        # re-solve can fail by itself, so the next strategy simply continues from the state.
        second = {**first, "skip_start_solve": True}
        return [first, second, {**second, "digits": 6}]

    def normalize(self, native: NativeRunResult) -> CanonicalResult:
        return SentaurusNormalizer().normalize(native)

    def _validate_safe_subset(self, spec: ExperimentSpec) -> None:
        # The experiment name is a free-text label that never reaches a native file, so spaces and
        # punctuation are fine; only characters that could act as a path or shell syntax are not.
        if not _SAFE_LABEL.fullmatch(spec.name) or ".." in spec.name:
            raise SentaurusCompilerSafetyError(
                f"unsafe identifier rejected by Sentaurus compiler: {spec.name!r}"
            )
        identifiers = [region.id for region in spec.regions]
        identifiers.extend(profile.region for profile in spec.profiles)
        identifiers.extend(contact.id for contact in spec.contacts)
        for value in identifiers:
            if not _SAFE_IDENTIFIER.fullmatch(value):
                raise SentaurusCompilerSafetyError(
                    f"unsafe identifier rejected by Sentaurus compiler: {value!r}"
                )
        shared = sorted({region.id for region in spec.regions} & {c.id for c in spec.contacts})
        if shared:
            # The structure editor keeps regions and contact sets in one namespace and aborts
            # (core dump) when they collide, so name the clash before spending a remote run.
            raise SentaurusCompilerSafetyError(
                f"a contact and a region share the name {shared[0]!r}; the Sentaurus structure "
                "editor needs distinct names, so rename the contact (for example "
                f"'{shared[0]}_contact')"
            )
        unknown_models = set(spec.physics.models) - set(_MODEL_LINES)
        if unknown_models:
            raise SentaurusCompilerSafetyError(f"unknown model mapping: {sorted(unknown_models)}")
        if {"boltzmann", "fermi"}.issubset(spec.physics.models):
            raise SentaurusCompilerSafetyError(
                "boltzmann and fermi statistics cannot both be selected"
            )
        mapped = {"electron_lifetime", "hole_lifetime"} if self._mesh_mode == "sde" else set()
        overrides = {
            name
            for name, value in spec.physics.parameters.model_dump().items()
            if value is not None and name not in mapped
        }
        if overrides:
            raise SentaurusCompilerSafetyError(
                "physics.parameters overrides need native parameter-file mappings: "
                + ", ".join(sorted(overrides))
            )
        parameters = spec.physics.parameters
        if (parameters.electron_lifetime is None) != (parameters.hole_lifetime is None):
            raise SentaurusCompilerSafetyError(
                "SRH lifetimes must be given for both electrons and holes, or for neither"
            )
        if spec.physics.temperature_profiles:
            raise SentaurusCompilerSafetyError("spatial temperature profiles are not mapped")
        if any(interface.fixed_charge_density is not None for interface in spec.interfaces):
            raise SentaurusCompilerSafetyError("interface fixed charge is not mapped")
        if any(
            contact.electron_richardson_constant is not None
            or contact.hole_richardson_constant is not None
            for contact in spec.contacts
        ):
            raise SentaurusCompilerSafetyError("contact Richardson constants are not mapped")
        if spec.profile_sampling is not None and self._mesh_mode != "sde":
            # Selecting profile biases happens when results are exported, which only the
            # generated-mesh pipeline does; an external-mesh bundle would drop the request.
            raise SentaurusCompilerSafetyError(
                "profile_sampling is not mapped to native output selection"
            )
        if isinstance(spec.study, DCStudy | DCPointsStudy) and spec.study.strategy != "fixed":
            raise SentaurusCompilerSafetyError("adaptive study recovery controls are not mapped")
        defaults = SolverControls()
        if spec.dimension == 2:
            vector = sorted(
                str(observable)
                for observable in spec.observables
                if str(observable)
                in {
                    "electric_field",
                    "electron_current_density",
                    "hole_current_density",
                    "total_current_density",
                }
            )
            if vector:
                raise SentaurusCompilerSafetyError(
                    "vector fields are not defined along a two-dimensional line cut: "
                    + ", ".join(vector)
                )
        for observable in spec.observables:
            needed = _OBSERVABLE_MODELS.get(str(observable))
            if needed and not set(needed) & set(spec.physics.models):
                raise SentaurusCompilerSafetyError(
                    f"{observable} needs the {' or '.join(needed)} model in the physics"
                )
        unmapped = [
            "electrostatic_absolute_error",
            "carrier_absolute_error",
            "transient_initial_relative_error",
            "transient_step_relative_error",
        ]
        if self._mesh_mode != "sde":
            # The generated mesh already follows the (halved) region spacing that a
            # refinement level stands for; an external mesh cannot honor it.
            unmapped.append("mesh_refinement_level")
        for key in unmapped:
            if getattr(spec.solver, key) != getattr(defaults, key):
                raise SentaurusCompilerSafetyError(f"solver.{key} is not mapped")
        digits = -math.log10(spec.solver.relative_error)
        if not math.isclose(digits, round(digits), abs_tol=1e-12):
            raise SentaurusCompilerSafetyError(
                "solver.relative_error must be a power of ten for the native Digits mapping"
            )

    def _context(self, spec: ExperimentSpec) -> dict[str, object]:
        physics_lines: list[str] = []
        if "fermi" in spec.physics.models:
            physics_lines.append("Fermi")
        # Constant mobility is the native default; a bare ``Mobility`` keyword is a syntax error.
        mobility_terms = [
            term
            for model in ("klaassen_mobility", "high_field_saturation")
            if model in spec.physics.models
            for term in _MODEL_LINES[model]
        ]
        if "HighFieldSaturation" in mobility_terms and any(
            str(region.material) == "silicon_dioxide" for region in spec.regions
        ):
            # Next to an insulator the field along the channel is the driving force. The
            # simulator's default form stalled the Newton solve of a two-dimensional MOSFET
            # at its first bias point; this standard channel form converged in minutes.
            mobility_terms[mobility_terms.index("HighFieldSaturation")] = (
                "HighFieldSaturation( EparallelToInterface )"
            )
        if mobility_terms:
            physics_lines.append(f"Mobility( {' '.join(mobility_terms)} )")
        recombination = [
            native
            for model, native in (("srh", "SRH"), ("auger", "Auger"))
            if model in spec.physics.models
        ]
        if recombination:
            physics_lines.append(f"Recombination( {' '.join(recombination)} )")
        if {"band_gap_narrowing", "slotboom_bgn"} & set(spec.physics.models):
            physics_lines.append("EffectiveIntrinsicDensity( OldSlotboom )")

        plot_fields: list[str] = []
        for observable in spec.observables:
            for field in _PLOT_FIELDS[observable]:
                if field not in plot_fields:
                    plot_fields.append(field)
        if "boltzmann" in spec.physics.models:
            # Evidence that carrier densities stay in the nondegenerate Boltzmann domain.
            for field in ("eEffectiveStateDensity", "hEffectiveStateDensity"):
                if field not in plot_fields:
                    plot_fields.append(field)

        ramps = []
        if isinstance(spec.study, DCStudy | DCPointsStudy):
            offset = next(
                contact.voltage_offset.to("V")
                for contact in spec.contacts
                if contact.id == spec.study.contact
            )
            ramps = [
                {
                    "contact": spec.study.contact,
                    "target": _stable_number(point.to("V") + offset),
                    "prefix": f"point_{index:04d}",
                }
                for index, point in enumerate(expand_study_points(spec.study))
            ]
        equations = {
            "poisson": "Poisson",
            "electron_continuity": "Electron",
            "hole_continuity": "Hole",
        }
        reduced = self._equilibrium_reducible(spec)
        return {
            "equilibrium_reduced": reduced,
            "compiler_version": self.compiler_version,
            "contacts": [self._contact_context(contact, spec) for contact in spec.contacts],
            "parameter_file": (
                "sdevice.par" if self._mesh_mode == "sde" and self._parameter_file(spec) else None
            ),
            "temperature": _stable_number(spec.physics.temperature.to("K")),
            "physics_lines": physics_lines,
            "plot_fields": plot_fields,
            "ramps": ramps,
            "equations": (
                "Poisson"
                if reduced
                else " ".join(equations[item] for item in spec.physics.equations)
            ),
            "iterations": max(spec.solver.maximum_iterations, MINIMUM_ITERATIONS, 300 if spec.dimension == 2 else 0),
            "digits": max(round(-math.log10(spec.solver.relative_error)), MINIMUM_DIGITS),
            "math_lines": list(_ITERATIVE) if spec.dimension == 2 else [],
            "skip_start_solve": False,
        }

    @staticmethod
    def _equilibrium_reducible(spec: ExperimentSpec) -> bool:
        """Whether every bias point is thermal equilibrium, so Poisson alone is exact.

        With only an insulated gate swept and every contact on the semiconductor held at one
        potential, no current can flow at any steady state: the electron and hole quasi-Fermi
        levels stay at that potential and the continuity equations add nothing but a
        stiff inversion-layer solve. Anything else (a biased drain, a Schottky or diode
        junction, a swept ohmic contact) carries current and keeps the full system.
        """
        if not isinstance(spec.study, DCStudy | DCPointsStudy):
            return False
        wanted = {Equation.ELECTRON_CONTINUITY, Equation.HOLE_CONTINUITY}
        if not wanted <= set(spec.physics.equations):
            return False

        def edge_material(contact: Contact) -> str:
            if spec.dimension == 2:
                return next(r for r in spec.regions if r.id == contact.region).material
            if str(contact.location) == "x_min":
                return min(spec.regions, key=lambda region: region.x0.to("m")).material
            return max(spec.regions, key=lambda region: region.x1.to("m")).material

        gates = {
            contact.id
            for contact in spec.contacts
            if contact.kind in {ContactKind.METAL_WORK_FUNCTION, ContactKind.IDEAL_GATE}
            and edge_material(contact) != "silicon"
        }
        if spec.study.contact not in gates:
            return False
        bulk = [contact for contact in spec.contacts if contact.id not in gates]
        if not bulk or any(contact.kind is not ContactKind.OHMIC for contact in bulk):
            return False
        return len({round(contact.voltage_offset.to("V"), 12) for contact in bulk}) == 1

    @staticmethod
    def _parameter_file(spec: ExperimentSpec) -> str | None:
        """Native parameter overrides for the quantities the experiment states explicitly."""
        parameters = spec.physics.parameters
        if parameters.electron_lifetime is None or parameters.hole_lifetime is None:
            return None
        electron = _stable_number(parameters.electron_lifetime.to("s"))
        hole = _stable_number(parameters.hole_lifetime.to("s"))
        return (
            "# Generated by NovAtom TCAD Agent: constant SRH lifetimes stated in the experiment.\n"
            'Material = "Silicon" {\n'
            "  Scharfetter {\n"
            f"    taumax = {electron} , {hole}\n"
            "  }\n"
            "}\n"
        )

    @staticmethod
    def _contact_context(contact: Contact, spec: ExperimentSpec) -> dict[str, object]:
        work_function = None
        schottky = False
        if contact.kind is ContactKind.METAL_WORK_FUNCTION:
            assert contact.work_function is not None
            work_function = _stable_number(contact.work_function.to("eV"))
            if spec.dimension == 2:
                edge = next(region for region in spec.regions if region.id == contact.region)
            else:
                edge = (
                    min(spec.regions, key=lambda region: region.x0.to("m"))
                    if str(contact.location) == "x_min"
                    else max(spec.regions, key=lambda region: region.x1.to("m"))
                )
            # A metal on silicon is a Schottky contact; on an insulator it is a gate, which
            # takes a work function but no Schottky barrier model.
            schottky = edge.material == "silicon"
        return {
            "id": contact.id,
            "work_function": work_function,
            "schottky": schottky,
            "voltage": _stable_number(contact.voltage_offset.to("V")),
        }

    @staticmethod
    def _source_map(spec: ExperimentSpec, command_text: str) -> dict[str, SourceLocation]:
        lines = command_text.splitlines()
        source_map: dict[str, SourceLocation] = {}
        for index, contact in enumerate(spec.contacts):
            needle = f'Name="{contact.id}"'
            line = next(number for number, value in enumerate(lines, 1) if needle in value)
            source_map[f"contacts[{index}]"] = SourceLocation(file="sdevice.cmd", line=line)
        physics_line = next(number for number, value in enumerate(lines, 1) if value == "Physics {")
        source_map["physics"] = SourceLocation(file="sdevice.cmd", line=physics_line)
        solve_line = next(number for number, value in enumerate(lines, 1) if value == "Solve {")
        source_map["study"] = SourceLocation(file="sdevice.cmd", line=solve_line)
        return source_map

    @staticmethod
    def _lint_generated(command_text: str) -> None:
        if "{{" in command_text or "{%" in command_text or "{#" in command_text:
            raise SentaurusCompilerSafetyError("undeclared template placeholder remains")
        if re.search(r'(?m)=\s*"/', command_text):
            raise SentaurusCompilerSafetyError("absolute paths are forbidden")
        if any(token in command_text for token in ("`", "$(`", "$(", "\x00")):
            raise SentaurusCompilerSafetyError("shell metacharacters are forbidden")
