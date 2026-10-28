"""Evidence-gated capability descriptors shared by planning and execution."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.domain.models import StrictModel

_CURRENT_DECOMPOSITION_OBSERVABLES = frozenset(
    {
        "electron_drift_current_density",
        "electron_diffusion_current_density",
        "hole_drift_current_density",
        "hole_diffusion_current_density",
        "current_decomposition_residual",
    }
)


class CapabilityMaturity(StrEnum):
    REVIEWED = "reviewed"
    EXPERIMENTAL = "experimental"
    DISABLED = "disabled"


class InputAuthority(StrEnum):
    RESEARCHER = "researcher"
    EXPERT = "expert"
    PLATFORM = "platform"


CapabilityCategory = Literal[
    "dimension",
    "equation",
    "model",
    "material",
    "profile",
    "interface",
    "contact",
    "study",
    "observable",
]


class CapabilityInputDescriptor(StrictModel):
    path: str = Field(min_length=1, max_length=240, pattern=r"^[a-z][a-z0-9_.-]*$")
    description: str = Field(min_length=1, max_length=600)
    authority: InputAuthority
    required: bool = True
    unit: str | None = Field(default=None, min_length=1, max_length=80)
    question_hint: str | None = Field(default=None, min_length=1, max_length=600)
    completeness_check: Literal["value", "structured"] = "value"


class CapabilityDescriptor(StrictModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9_.-]+$")
    category: CapabilityCategory
    summary: str = Field(min_length=1, max_length=800)
    maturity: CapabilityMaturity
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=16)
    requires: tuple[str, ...] = Field(default=(), max_length=32)
    conflicts: tuple[str, ...] = Field(default=(), max_length=32)
    required_inputs: tuple[CapabilityInputDescriptor, ...] = Field(default=(), max_length=32)
    optional_inputs: tuple[CapabilityInputDescriptor, ...] = Field(default=(), max_length=32)
    produces: tuple[str, ...] = Field(default=(), max_length=64)
    supported_materials: tuple[str, ...] = Field(default=(), max_length=32)
    supported_regions: tuple[str, ...] = Field(default=(), max_length=32)
    supported_interfaces: tuple[str, ...] = Field(default=(), max_length=32)
    supported_studies: tuple[str, ...] = Field(default=(), max_length=32)
    available_observables: tuple[str, ...] = Field(default=(), max_length=64)
    required_validators: tuple[str, ...] = Field(default=(), max_length=32)
    parameter_sources: tuple[str, ...] = Field(default=(), max_length=32)
    execution_limits: dict[str, int | float] = Field(default_factory=dict)
    backend_compatibility: dict[str, str] = Field(default_factory=dict)
    sentaurus_mapping: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def validate_reviewed_entry(self) -> Self:
        if self.maturity is CapabilityMaturity.REVIEWED and not self.evidence_refs:
            raise ValueError("reviewed capability requires at least one evidence reference")
        if self.id in self.requires or self.id in self.conflicts:
            raise ValueError("capability cannot require or conflict with itself")
        if set(self.requires) & set(self.conflicts):
            raise ValueError("capability dependency cannot also be a conflict")
        return self


class PublicCapabilityDescriptor(StrictModel):
    id: str
    category: CapabilityCategory
    summary: str
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    required_inputs: tuple[CapabilityInputDescriptor, ...] = ()
    optional_inputs: tuple[CapabilityInputDescriptor, ...] = ()
    produces: tuple[str, ...] = ()
    supported_materials: tuple[str, ...] = ()
    supported_regions: tuple[str, ...] = ()
    supported_interfaces: tuple[str, ...] = ()
    supported_studies: tuple[str, ...] = ()
    available_observables: tuple[str, ...] = ()
    required_validators: tuple[str, ...] = ()
    parameter_sources: tuple[str, ...] = ()
    execution_limits: dict[str, int | float] = Field(default_factory=dict)
    backend_compatibility: dict[str, str] = Field(default_factory=dict)
    sentaurus_mapping: str | None = None


class CapabilityCatalogView(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: str
    adapter_version: str
    execution_state: Literal["configured", "unconfigured"]
    capabilities: tuple[PublicCapabilityDescriptor, ...]
    limits: dict[str, int | float]
    guide: str = ""
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CapabilityCatalog(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: str
    adapter_version: str
    execution_state: Literal["configured", "unconfigured"] = "configured"
    descriptors: tuple[CapabilityDescriptor, ...]
    limits: dict[str, int | float] = Field(default_factory=dict)
    guide: str = ""

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        ids = [descriptor.id for descriptor in self.descriptors]
        if len(ids) != len(set(ids)):
            raise ValueError("capability descriptor ids must be unique")
        known = set(ids)
        for descriptor in self.descriptors:
            unknown = (set(descriptor.requires) | set(descriptor.conflicts)) - known
            if unknown:
                raise ValueError(
                    f"{descriptor.id} references unknown capability: " + ", ".join(sorted(unknown))
                )
        self._validate_dependency_cycles()
        return self

    def _validate_dependency_cycles(self) -> None:
        graph = {item.id: item.requires for item in self.descriptors}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(identifier: str) -> None:
            if identifier in visiting:
                raise ValueError("capability dependency graph contains a cycle")
            if identifier in visited:
                return
            visiting.add(identifier)
            for dependency in graph[identifier]:
                visit(dependency)
            visiting.remove(identifier)
            visited.add(identifier)

        for identifier in graph:
            visit(identifier)

    @property
    def digest(self) -> str:
        payload = self.model_dump(mode="json", exclude_none=True)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def public_view(self, *, max_capabilities: int = 128) -> CapabilityCatalogView:
        reviewed = sorted(
            (
                descriptor
                for descriptor in self.descriptors
                if descriptor.maturity is CapabilityMaturity.REVIEWED
                # Retain the legacy ABI in the full catalog, but do not teach
                # new requests an ambiguous old name for current density.
                and descriptor.id != "observable.terminal_current"
            ),
            key=lambda item: item.id,
        )[:max_capabilities]
        return CapabilityCatalogView(
            backend=self.backend,
            adapter_version=self.adapter_version,
            execution_state=self.execution_state,
            capabilities=tuple(
                PublicCapabilityDescriptor(
                    id=item.id,
                    category=item.category,
                    summary=item.summary,
                    requires=item.requires,
                    conflicts=item.conflicts,
                    required_inputs=item.required_inputs,
                    optional_inputs=item.optional_inputs,
                    produces=item.produces,
                    supported_materials=item.supported_materials,
                    supported_regions=item.supported_regions,
                    supported_interfaces=item.supported_interfaces,
                    supported_studies=item.supported_studies,
                    available_observables=item.available_observables,
                    required_validators=item.required_validators,
                    parameter_sources=item.parameter_sources,
                    execution_limits=item.execution_limits,
                    backend_compatibility=item.backend_compatibility,
                    sentaurus_mapping=item.sentaurus_mapping,
                )
                for item in reviewed
            ),
            limits=dict(sorted(self.limits.items())),
            guide=self.guide,
            digest=self.digest,
        )

    @classmethod
    def from_manifest(cls, manifest: CapabilityManifest) -> CapabilityCatalog:
        groups: tuple[tuple[CapabilityCategory, tuple[str | int, ...]], ...] = (
            ("dimension", manifest.dimensions),
            ("equation", manifest.equations),
            ("model", manifest.models),
            ("material", manifest.materials),
            ("profile", manifest.profiles),
            ("interface", manifest.interfaces),
            ("contact", manifest.contacts),
            ("study", manifest.studies),
            ("observable", manifest.observables),
        )
        descriptors: list[CapabilityDescriptor] = []
        for category, values in groups:
            for value in values:
                identifier = f"{category}.{value}"
                inputs = _legacy_required_inputs(category, str(value))
                optional_inputs = _legacy_optional_inputs(category, str(value))
                descriptors.append(
                    CapabilityDescriptor(
                        id=identifier,
                        category=category,
                        summary=(
                            f"{manifest.backend} supports {category} {value}"
                            + (
                                " (rectangular regions on a stack axis and a lateral axis, box "
                                "doping windows, contacts on region sides; results are terminal "
                                "currents and lateral line-cut profiles)"
                                if category == "dimension" and str(value) == "2"
                                else ""
                            )
                            + (
                                "; optional bias_schedule executes small-signal analysis at each "
                                "scheduled DC operating point on the same contact"
                                if category == "study"
                                and value in {"ac", "frequency"}
                                and manifest.backend == "devsim"
                                else ""
                            )
                            + (
                                "; with Fermi statistics, current decomposition is supported for "
                                "equilibrium, DC, temperature and parameter studies; AC, frequency "
                                "and transient diagnostics require separate benchmarks"
                                if manifest.backend == "devsim"
                                and category == "observable"
                                and value in _CURRENT_DECOMPOSITION_OBSERVABLES
                                else ""
                            )
                        ),
                        maturity=CapabilityMaturity.REVIEWED,
                        evidence_refs=_legacy_evidence_refs(
                            manifest.backend,
                            manifest.adapter_version,
                            category,
                            str(value),
                        ),
                        conflicts=_legacy_conflicts(manifest.backend, category, str(value)),
                        required_inputs=inputs,
                        optional_inputs=optional_inputs,
                        produces=_legacy_outputs(category, str(value)),
                        supported_materials=_supported_materials(category, str(value), manifest),
                        supported_interfaces=(
                            manifest.interfaces
                            if category in {"equation", "model", "study"}
                            else ()
                        ),
                        supported_studies=(
                            manifest.studies
                            if category in {"equation", "model", "observable"}
                            else ()
                        ),
                        available_observables=(
                            manifest.observables
                            if category in {"equation", "model", "study"}
                            else _legacy_outputs(category, str(value))
                        ),
                        required_validators=_required_validators(category),
                        parameter_sources=(
                            (
                                f"adapter-parameter-registry:{manifest.backend}:{manifest.adapter_version}",
                            )
                            if category in {"material", "model"}
                            else ()
                        ),
                        execution_limits=dict(manifest.limits),
                        backend_compatibility={
                            manifest.backend: (
                                "2.9.1" if manifest.backend == "devsim" else "deployment-specific"
                            )
                        },
                        sentaurus_mapping=(
                            "pending-reviewed-mapping" if manifest.backend == "devsim" else None
                        ),
                    )
                )
        if manifest.backend == "devsim":
            descriptors.append(
                CapabilityDescriptor(
                    id="profile.prescribed_temperature",
                    category="profile",
                    summary=(
                        "DEVSIM supports positive constant, linear, piecewise-constant, "
                        "and linearly interpolated tabulated lattice-temperature profiles "
                        "on one-dimensional silicon for equilibrium and DC transport. "
                        "This is prescribed temperature, not heat flow or self-heating."
                    ),
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=(
                        f"adapter-manifest:{manifest.backend}:{manifest.adapter_version}",
                        "knowledge-sources/curated/devsim-spatial-temperature.md",
                    ),
                    requires=("model.boltzmann", "model.constant_mobility"),
                    conflicts=(
                        "model.fermi",
                        "model.klaassen_mobility",
                        "model.high_field_saturation",
                        "contact.metal_work_function",
                        "study.ac",
                        "study.frequency",
                        "study.transient",
                        "study.temperature",
                    ),
                    required_inputs=(
                        CapabilityInputDescriptor(
                            path="physics.temperature_profiles",
                            description=(
                                "Region assignment and every prescribed spatial "
                                "temperature value and coordinate"
                            ),
                            authority=InputAuthority.RESEARCHER,
                            required=True,
                            unit="K and m",
                        ),
                    ),
                    produces=("lattice_temperature",),
                    supported_materials=("silicon",),
                    supported_studies=("equilibrium", "dc", "dc_points"),
                    available_observables=("lattice_temperature",),
                    required_validators=(
                        "canonical-datasets-structural",
                        "operating-points-converged",
                    ),
                    parameter_sources=("novatom.spatial-temperature.2026-09-29.v1",),
                    execution_limits=dict(manifest.limits),
                    backend_compatibility={"devsim": "2.9.1"},
                    sentaurus_mapping="pending-reviewed-mapping",
                )
            )
        return cls(
            backend=manifest.backend,
            adapter_version=manifest.adapter_version,
            execution_state=manifest.execution_state,
            descriptors=tuple(descriptors),
            limits=manifest.limits,
            guide=manifest.guide,
        )


def _legacy_conflicts(backend: str, category: CapabilityCategory, value: str) -> tuple[str, ...]:
    if backend != "devsim":
        return ()
    conflicts: dict[tuple[CapabilityCategory, str], tuple[str, ...]] = {
        ("model", "fermi"): (
            "profile.prescribed_temperature",
        ),
        ("model", "klaassen_mobility"): ("profile.prescribed_temperature",),
        ("model", "high_field_saturation"): ("profile.prescribed_temperature",),
        ("contact", "metal_work_function"): (
            "profile.prescribed_temperature",
        ),
        ("study", "ac"): ("profile.prescribed_temperature",),
        ("study", "frequency"): ("profile.prescribed_temperature",),
        ("study", "transient"): ("profile.prescribed_temperature",),
        ("study", "temperature"): ("profile.prescribed_temperature",),
    }
    return conflicts.get((category, value), ())


def _legacy_required_inputs(
    category: CapabilityCategory, value: str
) -> tuple[CapabilityInputDescriptor, ...]:
    if category == "dimension":
        if value != "2":
            return ()
        return (
            CapabilityInputDescriptor(
                path="regions.extents",
                description=(
                    "Rectangular extent of every region along the stack (depth) axis and the "
                    "lateral axis, with its material"
                ),
                authority=InputAuthority.RESEARCHER,
                completeness_check="structured",
            ),
            CapabilityInputDescriptor(
                path="profiles.windows",
                description=(
                    "Position, size, species and concentration of each doped window, for "
                    "example a source or drain implant"
                ),
                authority=InputAuthority.RESEARCHER,
                completeness_check="structured",
            ),
            CapabilityInputDescriptor(
                path="contacts.placement",
                description="Which region side, and which span along it, each contact occupies",
                authority=InputAuthority.RESEARCHER,
                completeness_check="structured",
            ),
            CapabilityInputDescriptor(
                path="profile_cuts.depth",
                description=(
                    "Depth of each lateral line along which profiles such as the horizontal "
                    "band diagram are taken"
                ),
                authority=InputAuthority.RESEARCHER,
                required=False,
                unit="m",
                question_hint=(
                    "How far below the surface should the horizontal profile be taken? "
                    "A channel is a few nanometres below the oxide interface."
                ),
            ),
        )
    if category == "study":
        common = (
            _researcher_input("physics.temperature", "Physical simulation temperature", unit="K"),
        )
        schedules: dict[str, tuple[CapabilityInputDescriptor, ...]] = {
            "equilibrium": (),
            "dc": (
                _researcher_input("study.contact", "Driven contact"),
                _researcher_input("study.start", "Sweep start voltage", unit="V"),
                _researcher_input("study.stop", "Sweep stop voltage", unit="V"),
                _researcher_input("study.step", "Sweep voltage step", unit="V"),
            ),
            "dc_points": (
                _researcher_input("study.contact", "Driven contact"),
                _researcher_input("study.values", "Exact requested voltage points", unit="V"),
            ),
            "ac": (
                _researcher_input("study.contact", "Small-signal driven contact"),
                _researcher_input("study.frequency", "Small-signal frequency", unit="Hz"),
                _researcher_input("study.amplitude", "Small-signal amplitude", unit="V"),
            ),
            "frequency": (
                _researcher_input("study.contact", "Small-signal driven contact"),
                _researcher_input("study.start", "Frequency sweep start", unit="Hz"),
                _researcher_input("study.stop", "Frequency sweep stop", unit="Hz"),
                _researcher_input("study.points", "Frequency point count"),
                _researcher_input("study.amplitude", "Small-signal amplitude", unit="V"),
            ),
            "transient": (
                _researcher_input("study.contact", "Driven contact"),
                _researcher_input("study.waveform", "Step, ramp, or pulse waveform"),
                _researcher_input("study.initial_voltage", "Initial voltage", unit="V"),
                _researcher_input("study.final_voltage", "Final voltage", unit="V"),
                _researcher_input("study.stop", "Transient stop time", unit="s"),
            ),
            "temperature": (_researcher_input("study.values", "Requested temperatures", unit="K"),),
            "parameter": (
                _researcher_input("study.parameter_path", "Registered parameter to sweep"),
                _researcher_input("study.values", "Requested parameter values"),
            ),
        }
        return common + schedules.get(value, ())
    if category == "material":
        inputs: tuple[CapabilityInputDescriptor, ...] = (
            _researcher_input(
                "regions.material",
                "Material assignment for every spatial region",
                question_hint=(
                    "Which material is each region made of (for example silicon, silicon "
                    "dioxide, or a named high-k dielectric)?"
                ),
            ),
        )
        if value == "generic_dielectric":
            inputs += (
                _researcher_input(
                    "regions.relative_permittivity",
                    "Researcher-specified relative permittivity",
                    unit="1",
                ),
            )
        return inputs
    if category == "profile":
        return (
            CapabilityInputDescriptor(
                path="profiles.parameters",
                description="Profile location, species and physical parameters",
                authority=InputAuthority.RESEARCHER,
                required=True,
                completeness_check="structured",
            ),
        )
    if category == "contact":
        inputs = (
            CapabilityInputDescriptor(
                path="contacts.boundary_conditions",
                description="Contact locations, types and applied conditions",
                authority=InputAuthority.RESEARCHER,
                completeness_check="structured",
            ),
        )
        if value == "metal_work_function":
            inputs += (
                _researcher_input("contacts.work_function", "Metal work function", unit="eV"),
            )
        return inputs
    if category == "interface":
        interface_inputs: dict[str, tuple[CapabilityInputDescriptor, ...]] = {
            "surface_srh": (
                _researcher_input(
                    "interfaces.surface_electron_velocity",
                    "Electron surface capture velocity",
                    unit="m/s",
                ),
                _researcher_input(
                    "interfaces.surface_hole_velocity",
                    "Hole surface capture velocity",
                    unit="m/s",
                ),
            ),
            "interface_trap": (
                _researcher_input(
                    "interfaces.trap_density", "Interface trap sheet density", unit="m^-2"
                ),
                _researcher_input(
                    "interfaces.trap_energy", "Trap energy relative to intrinsic level", unit="eV"
                ),
                _researcher_input("interfaces.trap_type", "Donor or acceptor trap type"),
            ),
        }
        return interface_inputs.get(value, ())
    if category == "observable" and value == "absolute_terminal_current":
        return (
            _researcher_input(
                "contacts.area",
                "Physical contact cross-sectional area for conversion from current density",
                unit="m^2",
            ),
        )
    if category in {"equation", "model"}:
        return (
            CapabilityInputDescriptor(
                path=f"physics.{category}s",
                description=f"Reviewed expert selection for {value}",
                authority=InputAuthority.EXPERT,
                required=True,
            ),
        )
    return ()


def _legacy_optional_inputs(
    category: CapabilityCategory, value: str
) -> tuple[CapabilityInputDescriptor, ...]:
    if category == "study" and value in {"dc", "dc_points", "ac", "frequency"}:
        return (
            CapabilityInputDescriptor(
                path="profile_sampling.bias_values",
                description="Explicit spatial profile extraction voltages",
                authority=InputAuthority.RESEARCHER,
                required=False,
                unit="V",
                question_hint="Which operating voltages should be used for the spatial profiles?",
            ),
        )
    if category == "contact" and value == "metal_work_function":
        return (
            CapabilityInputDescriptor(
                path="contacts.electron_richardson_constant",
                description="Optional electron thermionic Richardson constant",
                authority=InputAuthority.RESEARCHER,
                required=False,
                unit="A/cm^2/K^2",
            ),
            CapabilityInputDescriptor(
                path="contacts.hole_richardson_constant",
                description="Optional hole thermionic Richardson constant",
                authority=InputAuthority.RESEARCHER,
                required=False,
                unit="A/cm^2/K^2",
            ),
        )
    if category != "study" or value != "transient":
        return ()
    pulse_hint = "Ask only when the researcher selects a pulse waveform."
    return (
        CapabilityInputDescriptor(
            path="study.pulse_delay",
            description="Pulse delay from transient start",
            authority=InputAuthority.RESEARCHER,
            required=False,
            unit="s",
            question_hint=pulse_hint,
        ),
        CapabilityInputDescriptor(
            path="study.rise_time",
            description="Pulse rise time",
            authority=InputAuthority.RESEARCHER,
            required=False,
            unit="s",
            question_hint=pulse_hint,
        ),
        CapabilityInputDescriptor(
            path="study.pulse_width",
            description="Pulse high-state duration",
            authority=InputAuthority.RESEARCHER,
            required=False,
            unit="s",
            question_hint=pulse_hint,
        ),
        CapabilityInputDescriptor(
            path="study.fall_time",
            description="Pulse fall time",
            authority=InputAuthority.RESEARCHER,
            required=False,
            unit="s",
            question_hint=pulse_hint,
        ),
        CapabilityInputDescriptor(
            path="study.minimum_step",
            description="Optional minimum timestep for bounded recovery",
            authority=InputAuthority.EXPERT,
            required=False,
            unit="s",
        ),
        CapabilityInputDescriptor(
            path="study.maximum_retries",
            description="Optional bounded retry count after a failed transient step",
            authority=InputAuthority.EXPERT,
            required=False,
        ),
    )


def _researcher_input(
    path: str,
    description: str,
    *,
    unit: str | None = None,
    question_hint: str | None = None,
) -> CapabilityInputDescriptor:
    return CapabilityInputDescriptor(
        path=path,
        description=description,
        authority=InputAuthority.RESEARCHER,
        required=True,
        unit=unit,
        question_hint=question_hint,
    )


def _legacy_evidence_refs(
    backend: str,
    adapter_version: str,
    category: CapabilityCategory,
    value: str,
) -> tuple[str, ...]:
    base = (f"adapter-manifest:{backend}:{adapter_version}",)
    if backend != "devsim":
        return base
    if category == "observable" and value in _CURRENT_DECOMPOSITION_OBSERVABLES:
        return (*base, "knowledge-sources/curated/devsim-current-decomposition.md")
    curated = {
        ("model", "fermi"): "knowledge-sources/curated/devsim-fermi-transport.md",
        ("contact", "metal_work_function"): (
            "knowledge-sources/curated/devsim-schottky-transport.md"
        ),
        ("interface", "surface_srh"): ("knowledge-sources/curated/devsim-surface-physics.md"),
        ("interface", "interface_trap"): ("knowledge-sources/curated/devsim-surface-physics.md"),
        ("observable", "current_decomposition_residual"): (
            "knowledge-sources/curated/devsim-current-decomposition.md"
        ),
        ("observable", "lattice_temperature"): (
            "knowledge-sources/curated/devsim-spatial-temperature.md"
        ),
    }.get((category, value))
    return base if curated is None else (*base, curated)


def _legacy_outputs(category: CapabilityCategory, value: str) -> tuple[str, ...]:
    if category == "observable":
        return (value,)
    if category == "equation" and value == "poisson":
        return ("potential", "electric_field")
    return ()


def _supported_materials(
    category: CapabilityCategory,
    value: str,
    manifest: CapabilityManifest,
) -> tuple[str, ...]:
    if category == "material":
        return (value,)
    if category == "profile" and value != "fixed_charge":
        return tuple(item for item in manifest.materials if item == "silicon")
    if category in {"equation", "model", "study", "observable"}:
        return manifest.materials
    return ()


def _required_validators(category: CapabilityCategory) -> tuple[str, ...]:
    common = ("canonical-datasets-structural",)
    if category == "study":
        return (*common, "operating-points-converged")
    if category in {"equation", "model"}:
        return (*common, "requested-observables-present")
    return common
