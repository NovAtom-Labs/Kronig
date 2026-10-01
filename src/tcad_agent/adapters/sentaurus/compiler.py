"""Deterministic compiler for the reviewed Sentaurus Device subset."""

from __future__ import annotations

import hashlib
import json
import re
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from tcad_agent.adapters.sentaurus.normalizer import SentaurusNormalizer
from tcad_agent.adapters.sentaurus.runtime import (
    SentaurusJobManifest,
    SourceLocation,
)
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import (
    Contact,
    ContactKind,
    DCStudy,
    ExperimentSpec,
    Observable,
)
from tcad_agent.results.models import CanonicalResult
from tcad_agent.runners.models import CompiledJob, NativeRunResult

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_MODEL_LINES = {
    "boltzmann": (),
    "fermi": ("Fermi",),
    "constant_mobility": ("Mobility",),
    "srh": (),
    "auger": (),
    "band_gap_narrowing": ("EffectiveIntrinsicDensity( OldSlotboom )",),
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
    Observable.ELECTRON_CURRENT_DENSITY: ("eCurrent/Vector",),
    Observable.HOLE_CURRENT_DENSITY: ("hCurrent/Vector",),
    Observable.ELECTRON_MOBILITY: ("eMobility",),
    Observable.HOLE_MOBILITY: ("hMobility",),
    Observable.RECOMBINATION_RATE: ("TotalRecombination",),
    Observable.TERMINAL_CURRENT: (),
    Observable.TERMINAL_CURRENT_DENSITY: (),
    Observable.ABSOLUTE_TERMINAL_CURRENT: (),
    Observable.TERMINAL_CHARGE: (),
}
_EXPECTED_OUTPUTS = ("sdevice.log", "sdevice.plt", "sdevice.tdr")


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
    compiler_version = "0.1.0"

    def __init__(self, manifest: CapabilityManifest) -> None:
        self._manifest = manifest

    @property
    def manifest(self) -> CapabilityManifest:
        return self._manifest

    @classmethod
    def from_defaults(cls) -> SentaurusAdapter:
        return cls(CapabilityManifest.from_backend("sentaurus"))

    def compile(self, spec: ExperimentSpec, workspace: Path) -> CompiledJob:
        decision = CapabilityService().check(spec, self.manifest)
        if decision.status is not CapabilityStatus.SUPPORTED:
            details = "; ".join(
                f"{issue.path}: {issue.message}" for issue in decision.issues
            )
            raise CapabilityError(details)
        self._validate_safe_subset(spec)

        template_bytes = (
            files("tcad_agent.adapters.sentaurus")
            .joinpath("templates/sdevice.cmd.j2")
            .read_bytes()
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
        experiment_bytes = (
            json.dumps(spec.normalized(), sort_keys=True, indent=2) + "\n"
        ).encode()

        source_map = self._source_map(spec, command_text)
        manifest = SentaurusJobManifest(
            compiler_version=self.compiler_version,
            expected_outputs=_EXPECTED_OUTPUTS,
            inputs={
                "experiment.json": _sha256(experiment_bytes),
                "sdevice.cmd": _sha256(command_bytes),
            },
            source_map=source_map,
        )
        manifest_bytes = (
            json.dumps(manifest.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
        ).encode()
        generated = {
            "experiment.json": experiment_bytes,
            "job-manifest.json": manifest_bytes,
            "sdevice.cmd": command_bytes,
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
                        "plots": {
                            str(key): value for key, value in _PLOT_FIELDS.items()
                        },
                    },
                    sort_keys=True,
                ).encode(),
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

    def normalize(self, native: NativeRunResult) -> CanonicalResult:
        return SentaurusNormalizer().normalize(native)

    def _validate_safe_subset(self, spec: ExperimentSpec) -> None:
        identifiers = [spec.name]
        identifiers.extend(region.id for region in spec.regions)
        identifiers.extend(profile.region for profile in spec.profiles)
        identifiers.extend(contact.id for contact in spec.contacts)
        for value in identifiers:
            if not _SAFE_IDENTIFIER.fullmatch(value):
                raise SentaurusCompilerSafetyError(
                    f"unsafe identifier rejected by Sentaurus compiler: {value!r}"
                )
        unknown_models = set(spec.physics.models) - set(_MODEL_LINES)
        if unknown_models:
            raise SentaurusCompilerSafetyError(
                f"unknown model mapping: {sorted(unknown_models)}"
            )
        if {"boltzmann", "fermi"}.issubset(spec.physics.models):
            raise SentaurusCompilerSafetyError(
                "boltzmann and fermi statistics cannot both be selected"
            )
        if len(spec.regions) != 2:
            raise SentaurusCompilerSafetyError(
                "the reviewed Sentaurus compiler currently requires exactly two regions"
            )
        if len(spec.contacts) != 2:
            raise SentaurusCompilerSafetyError(
                "the reviewed Sentaurus compiler currently requires exactly two contacts"
            )

    def _context(self, spec: ExperimentSpec) -> dict[str, object]:
        physics_lines: list[str] = []
        if "fermi" in spec.physics.models:
            physics_lines.append("Fermi")
        if "constant_mobility" in spec.physics.models:
            physics_lines.append("Mobility")
        recombination = [
            native
            for model, native in (("srh", "SRH"), ("auger", "Auger"))
            if model in spec.physics.models
        ]
        if recombination:
            physics_lines.append(f"Recombination( {' '.join(recombination)} )")
        if "band_gap_narrowing" in spec.physics.models:
            physics_lines.append("EffectiveIntrinsicDensity( OldSlotboom )")

        plot_fields: list[str] = []
        for observable in spec.observables:
            for field in _PLOT_FIELDS[observable]:
                if field not in plot_fields:
                    plot_fields.append(field)

        study: dict[str, str] = {"kind": spec.study.kind}
        if isinstance(spec.study, DCStudy):
            study.update(
                {
                    "contact": spec.study.contact,
                    "start": _stable_number(spec.study.start.to("V")),
                    "stop": _stable_number(spec.study.stop.to("V")),
                    "step": _stable_number(spec.study.step.to("V")),
                }
            )
        return {
            "compiler_version": self.compiler_version,
            "contacts": [self._contact_context(contact) for contact in spec.contacts],
            "temperature": _stable_number(spec.physics.temperature.to("K")),
            "physics_lines": physics_lines,
            "plot_fields": plot_fields,
            "study": study,
        }

    @staticmethod
    def _contact_context(contact: Contact) -> dict[str, str | None]:
        work_function = None
        if contact.kind is ContactKind.METAL_WORK_FUNCTION:
            assert contact.work_function is not None
            work_function = _stable_number(contact.work_function.to("eV"))
        return {"id": contact.id, "work_function": work_function}

    @staticmethod
    def _source_map(
        spec: ExperimentSpec, command_text: str
    ) -> dict[str, SourceLocation]:
        lines = command_text.splitlines()
        source_map: dict[str, SourceLocation] = {}
        for index, contact in enumerate(spec.contacts):
            needle = f'Name="{contact.id}"'
            line = next(number for number, value in enumerate(lines, 1) if needle in value)
            source_map[f"contacts[{index}]"] = SourceLocation(
                file="sdevice.cmd", line=line
            )
        physics_line = next(
            number for number, value in enumerate(lines, 1) if value == "Physics {"
        )
        source_map["physics"] = SourceLocation(file="sdevice.cmd", line=physics_line)
        solve_line = next(
            number for number, value in enumerate(lines, 1) if value == "Solve {"
        )
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
