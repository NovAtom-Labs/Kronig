"""Stable researcher-facing error envelopes."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from pydantic import Field

from tcad_agent.domain.models import StrictModel
from tcad_agent.ide.store import IDEStoreError
from tcad_agent.observability.diagnostics import redact_diagnostic


class ErrorCategory(StrEnum):
    DOMAIN = "domain"
    PROVIDER = "provider"
    SIMULATOR = "simulator"
    FILESYSTEM = "filesystem"
    NETWORK = "network"
    PERMISSION = "permission"
    LIFECYCLE = "lifecycle"
    VALIDATION = "validation"
    INTERNAL = "internal"


class ErrorEnvelope(StrictModel):
    schema_version: str = "1.0"
    category: ErrorCategory
    code: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    message: str
    operation: str
    retryable: bool = False
    recovery_actions: tuple[str, ...] = ()
    correlation_id: str
    diagnostic_id: str


@dataclass(frozen=True)
class MappedError:
    status_code: int
    envelope: ErrorEnvelope


def map_exception(error: Exception, *, operation: str) -> MappedError:
    diagnostic_id = f"diag-{uuid4().hex[:16]}"
    correlation_id = f"corr-{uuid4().hex[:16]}"
    actions: tuple[str, ...]
    if isinstance(error, sqlite3.IntegrityError):
        category = ErrorCategory.LIFECYCLE
        code = "lifecycle_persistence_conflict"
        message = (
            "Agent Kronig could not finish local session cleanup. "
            "Your project files were not deleted."
        )
        actions = ("Retry closing", "Open diagnostics", "Quit anyway")
        status = 409
    elif isinstance(error, IDEStoreError):
        category = ErrorCategory.LIFECYCLE
        code = "local_state_operation_failed"
        message = "Agent Kronig could not update its local session state."
        actions = ("Refresh the current view", "Retry the operation", "Open diagnostics")
        status = 409
    elif isinstance(error, PermissionError):
        category = ErrorCategory.PERMISSION
        code = "filesystem_permission_denied"
        message = "Agent Kronig does not have permission to access the requested location."
        actions = ("Choose a writable location", "Review file permissions")
        status = 403
    elif isinstance(error, OSError):
        category = ErrorCategory.FILESYSTEM
        code = "local_filesystem_failure"
        message = "A local file operation failed. Project files were left in place."
        actions = ("Retry the operation", "Open diagnostics")
        status = 500
    else:
        category = ErrorCategory.INTERNAL
        code = "unexpected_local_failure"
        message = "Agent Kronig encountered an unexpected local error."
        actions = ("Retry the operation", "Open diagnostics")
        status = 500
    redact_diagnostic(error)
    return MappedError(
        status_code=status,
        envelope=ErrorEnvelope(
            category=category,
            code=code,
            message=message,
            operation=operation,
            retryable=status in {409, 500},
            recovery_actions=actions,
            correlation_id=correlation_id,
            diagnostic_id=diagnostic_id,
        ),
    )
