"""Evidence-gated capability descriptors shared by planning and execution."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.domain.models import StrictModel


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


class CapabilityDescriptor(StrictModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9_.-]+$")
    category: CapabilityCategory
    summary: str = Field(min_length=1, max_length=800)
    maturity: CapabilityMaturity
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=16)
    requires: tuple[str, ...] = Field(default=(), max_length=32)
    conflicts: tuple[str, ...] = Field(default=(), max_length=32)
    required_inputs: tuple[CapabilityInputDescriptor, ...] = Field(
        default=(), max_length=32
    )
    produces: tuple[str, ...] = Field(default=(), max_length=64)

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
    produces: tuple[str, ...] = ()


class CapabilityCatalogView(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: str
    adapter_version: str
    execution_state: Literal["configured", "unconfigured"]
    capabilities: tuple[PublicCapabilityDescriptor, ...]
    limits: dict[str, int | float]
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CapabilityCatalog(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: str
    adapter_version: str
    execution_state: Literal["configured", "unconfigured"] = "configured"
    descriptors: tuple[CapabilityDescriptor, ...]
    limits: dict[str, int | float] = Field(default_factory=dict)

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
                    f"{descriptor.id} references unknown capability: "
                    + ", ".join(sorted(unknown))
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
                    produces=item.produces,
                )
                for item in reviewed
            ),
            limits=dict(sorted(self.limits.items())),
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
                descriptors.append(
                    CapabilityDescriptor(
                        id=identifier,
                        category=category,
                        summary=f"{manifest.backend} supports {category} {value}",
                        maturity=CapabilityMaturity.REVIEWED,
                        evidence_refs=(
                            f"adapter-manifest:{manifest.backend}:{manifest.adapter_version}",
                        ),
                        required_inputs=inputs,
                        produces=_legacy_outputs(category, str(value)),
                    )
                )
        return cls(
            backend=manifest.backend,
            adapter_version=manifest.adapter_version,
            execution_state=manifest.execution_state,
            descriptors=tuple(descriptors),
            limits=manifest.limits,
        )


def _legacy_required_inputs(
    category: CapabilityCategory, value: str
) -> tuple[CapabilityInputDescriptor, ...]:
    if category == "study":
        return (
            CapabilityInputDescriptor(
                path="study.temperature",
                description="Physical simulation temperature",
                authority=InputAuthority.RESEARCHER,
                required=True,
                unit="K",
            ),
        )
    if category == "material":
        return (
            CapabilityInputDescriptor(
                path="regions.material",
                description="Material assignment for every spatial region",
                authority=InputAuthority.RESEARCHER,
                required=True,
            ),
        )
    if category == "profile":
        return (
            CapabilityInputDescriptor(
                path="profiles.parameters",
                description="Profile location, species and physical parameters",
                authority=InputAuthority.RESEARCHER,
                required=True,
            ),
        )
    if category == "contact":
        return (
            CapabilityInputDescriptor(
                path="contacts.boundary_conditions",
                description="Contact locations, types and applied conditions",
                authority=InputAuthority.RESEARCHER,
                required=True,
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


def _legacy_outputs(category: CapabilityCategory, value: str) -> tuple[str, ...]:
    if category == "observable":
        return (value,)
    if category == "equation" and value == "poisson":
        return ("potential", "electric_field")
    return ()
