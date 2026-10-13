"""Typed inputs and outputs for immutable experiment bundles."""

from pathlib import Path
from typing import Literal

from tcad_agent.domain.models import ExperimentSpec, StrictModel
from tcad_agent.recovery.proposals import RecoveryComparison
from tcad_agent.results.models import CanonicalResult
from tcad_agent.runners.models import CompiledJob, NativeRunResult
from tcad_agent.science.models import ScientificCompletenessReport
from tcad_agent.validation.models import ValidationReport


class BundleInputs(StrictModel):
    run_id: str
    spec: ExperimentSpec
    job: CompiledJob
    native: NativeRunResult
    result: CanonicalResult
    validation: ValidationReport
    events_path: Path
    completeness: ScientificCompletenessReport | None = None
    recovery_comparison: RecoveryComparison | None = None


class ArtifactRecord(StrictModel):
    sha256: str
    bytes: int


class BundleManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    state: Literal["failed", "completed"]
    execution_state: Literal["failed", "completed"] | None = None
    validation_state: Literal["passed", "needs_review", "failed"] | None = None
    backend: Literal["devsim", "sentaurus"]
    simulator_version: str | None
    compiler_version: str
    input_digest: str
    runtime_digest: str
    artifacts: dict[str, ArtifactRecord]


class ExperimentBundle(StrictModel):
    run_id: str
    state: Literal["failed", "completed"]
    execution_state: Literal["failed", "completed"] | None = None
    validation_state: Literal["passed", "needs_review", "failed"] | None = None
    root: Path
