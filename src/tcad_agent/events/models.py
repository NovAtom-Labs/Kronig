"""Typed event schema used by deterministic experiment evidence bundles."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, JsonValue

from tcad_agent.domain.models import StrictModel


class RunEventKind(StrEnum):
    REQUESTED = "requested"
    CLARIFICATION_REQUIRED = "clarification_required"
    SPEC_DRAFTED = "spec_drafted"
    VALIDATED = "validated"
    APPROVED = "approved"
    COMPILED = "compiled"
    STARTED = "started"
    RECOVERY_ATTEMPTED = "recovery_attempted"
    COMPLETED = "completed"
    FAILED = "failed"


class RunEvent(StrictModel):
    sequence: int = Field(ge=1)
    occurred_at: datetime
    kind: RunEventKind
    payload: dict[str, JsonValue]
    previous_hash: str | None
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
