"""Typed records for resolving consequential scientific inputs."""

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from tcad_agent.domain.models import StrictModel


class InputAuthority(StrEnum):
    RESEARCHER = "researcher_owned"
    PLATFORM = "platform_reviewed_default"
    DERIVED = "deterministically_derived"
    EXPERT = "evidence_backed_expert_suggestion"
    ADAPTER = "simulator_implementation_detail"
    UNKNOWN = "unsupported_or_unknown"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"


class ProvenanceReference(StrictModel):
    id: str = Field(min_length=1, max_length=240)
    kind: Literal["researcher", "platform", "derived", "evidence", "adapter"]
    digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class InputResolutionRecord(StrictModel):
    path: str = Field(min_length=1, max_length=320)
    quantity: str = Field(min_length=1, max_length=240)
    value: JsonValue | None = None
    authority: InputAuthority
    source: ProvenanceReference | None = None
    derivation: str | None = Field(default=None, max_length=1000)
    required_by: tuple[str, ...] = Field(min_length=1, max_length=32)
    status: ResolutionStatus
    rationale: str = Field(min_length=1, max_length=1200)
    consequence: str | None = Field(default=None, max_length=1200)


class ModelDiscoveredRequirement(StrictModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-z][a-z0-9_.-]*$")
    path: str = Field(min_length=1, max_length=320)
    rationale: str = Field(min_length=1, max_length=1200)
    consequence: str = Field(min_length=1, max_length=1200)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=16)
    confidence: float = Field(ge=0, le=1)


class ScientificCompletenessReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: str
    records: tuple[InputResolutionRecord, ...]
    model_discoveries: tuple[ModelDiscoveredRequirement, ...] = ()

    @property
    def unresolved(self) -> tuple[InputResolutionRecord, ...]:
        return tuple(
            record
            for record in self.records
            if record.status is not ResolutionStatus.RESOLVED
        )

    @property
    def ready(self) -> bool:
        return not self.unresolved
