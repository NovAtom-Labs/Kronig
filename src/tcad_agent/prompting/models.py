"""Typed contracts for generic request preparation and compilation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, JsonValue, field_validator, model_validator

from tcad_agent.domain.models import StrictModel


class IntentOrigin(StrEnum):
    RESEARCHER = "researcher"
    REPOSITORY = "repository"
    EVIDENCE = "evidence"
    PLATFORM_DEFAULT = "platform_default"


class IntentField(StrictModel):
    path: str = Field(min_length=1, max_length=240, pattern=r"^[a-z][a-z0-9_.-]*$")
    value: JsonValue
    origin: IntentOrigin
    rationale: str | None = Field(default=None, min_length=1, max_length=1200)
    source_reference: str | None = Field(default=None, min_length=1, max_length=500)
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_origin_evidence(self) -> Self:
        if self.origin is IntentOrigin.REPOSITORY and self.source_reference is None:
            raise ValueError("repository origin requires a source reference")
        if self.origin is IntentOrigin.EVIDENCE:
            if not self.rationale or not self.evidence_refs:
                raise ValueError("evidence origin requires a rationale and evidence references")
        if self.origin is IntentOrigin.RESEARCHER and self.evidence_refs:
            raise ValueError("researcher intent cannot be attributed to evidence")
        return self


class ClarificationQuestion(StrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    field_path: str = Field(min_length=1, max_length=240, pattern=r"^[a-z][a-z0-9_.-]*$")
    prompt: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)
    required: bool = True
    reason_kind: Literal[
        "unspecified", "missing", "invalid", "ambiguous", "conflict", "dependency_changed"
    ] = "unspecified"
    evidence_quotes: tuple[str, ...] = Field(default=(), max_length=4)
    dependency_fields: tuple[str, ...] = Field(default=(), max_length=8)


class ClarificationAnswer(StrictModel):
    question_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_-]*$")
    answer: str = Field(min_length=1, max_length=10_000)
    field_path: str | None = Field(default=None, max_length=240, pattern=r"^[a-z][a-z0-9_.-]*$")
    question_prompt: str | None = Field(default=None, min_length=1, max_length=1000)
    question_revision: int | None = Field(default=None, ge=0)


class ResolvedResearchIntent(StrictModel):
    task_kind: Literal["repository_change", "simulation", "analysis", "explanation", "mixed"]
    objective: str = Field(min_length=1, max_length=4000)
    selected_capabilities: tuple[str, ...] = Field(default=(), max_length=64)
    fields: tuple[IntentField, ...] = Field(default=(), max_length=256)
    exclusions: tuple[str, ...] = Field(default=(), max_length=64)
    deliverables: tuple[str, ...] = Field(default=(), max_length=64)
    validation_expectations: tuple[str, ...] = Field(default=(), max_length=64)
    unresolved_noncritical: tuple[str, ...] = Field(default=(), max_length=64)
    unresolved_critical: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("fields")
    @classmethod
    def unique_field_paths(cls, fields: tuple[IntentField, ...]) -> tuple[IntentField, ...]:
        paths = [field.path for field in fields]
        if len(paths) != len(set(paths)):
            raise ValueError("resolved intent field paths must be unique")
        return fields


class PreparationDecision(StrictModel):
    status: Literal["clarification", "ready", "blocked"]
    summary: str = Field(min_length=1, max_length=4000)
    questions: tuple[ClarificationQuestion, ...] = Field(default=(), max_length=7)
    intent: ResolvedResearchIntent | None = None
    unresolved_critical: tuple[str, ...] = Field(default=(), max_length=64)
    warnings: tuple[str, ...] = Field(default=(), max_length=64)
    runtime_research_needed: bool = False
    runtime_research_reason: str | None = Field(default=None, min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        ids = [question.id for question in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("clarification requires unique question ids within a revision")
        if self.status == "clarification":
            if not self.questions:
                raise ValueError("clarification requires at least one question")
            if len(self.questions) > 7:
                raise ValueError("clarification allows at most 7 questions")
            if not self.unresolved_critical:
                raise ValueError("clarification requires unresolved critical fields")
        elif self.status == "ready":
            if self.questions:
                raise ValueError("ready decision cannot contain questions")
            if self.intent is None:
                raise ValueError("ready decision requires resolved intent")
            if self.unresolved_critical or self.intent.unresolved_critical:
                raise ValueError("ready decision cannot contain unresolved critical intent")
        elif self.intent is not None or self.questions:
            raise ValueError("blocked decision cannot contain intent or questions")
        if self.runtime_research_needed and not self.runtime_research_reason:
            raise ValueError("runtime research requires a reason")
        return self


class WorkspaceFileContext(StrictModel):
    path: str = Field(min_length=1, max_length=1000)
    size: int = Field(ge=0)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    text_excerpt: str | None = Field(default=None, max_length=16000)


class WorkspaceContext(StrictModel):
    display_name: str = Field(min_length=1, max_length=500)
    git_available: bool
    git_branch: str | None = Field(default=None, max_length=500)
    git_dirty: bool
    files: tuple[WorkspaceFileContext, ...] = Field(default=(), max_length=500)
    inventory_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    inventory_truncated: bool = False


class EvidenceExcerpt(StrictModel):
    id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=1000)
    url: str = Field(min_length=1, max_length=4000)
    version: str = Field(min_length=1, max_length=500)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed: bool
    content: str = Field(min_length=1, max_length=2000)


class CompiledAgentRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    compiler_version: str
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiled_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    compiled_prompt: str = Field(min_length=1)
    decision: PreparationDecision
    workspace: WorkspaceContext
    evidence: tuple[EvidenceExcerpt, ...]
    answers: tuple[ClarificationAnswer, ...]
    capability_hashes: dict[str, str]


class PromptPreparationRecord(StrictModel):
    run_id: UUID
    original_prompt: str = Field(min_length=1, max_length=100_000)
    answers: tuple[ClarificationAnswer, ...] = ()
    decision: PreparationDecision | None = None
    compiled_request: CompiledAgentRequest | None = None
    revision: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime
