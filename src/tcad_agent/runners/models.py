"""Typed simulator job and execution records."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from tcad_agent.domain.models import StrictModel


class CompiledJob(StrictModel):
    backend: Literal["devsim", "sentaurus"]
    entrypoint: Path
    arguments: tuple[str, ...] = ()
    environment: dict[str, str] = Field(default_factory=dict)
    input_files: tuple[Path, ...]
    input_digest: str
    runtime_digest: str
    compiler_version: str


class RunBudget(StrictModel):
    seconds: float = Field(gt=0, le=3600)


class NativeRunResult(StrictModel):
    backend: Literal["devsim", "sentaurus"]
    status: Literal["completed", "execution_failed", "timed_out", "malformed_result"]
    return_code: int | None
    stdout_path: Path
    stderr_path: Path
    result_path: Path | None = None
    elapsed_seconds: float = Field(ge=0)
    error: str | None = None
    audit_json_path: Path | None = None
    audit_log_path: Path | None = None

