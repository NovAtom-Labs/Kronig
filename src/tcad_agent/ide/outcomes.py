"""Derive honest run outcomes from researcher-facing project evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict
from uuid import UUID

from pydantic import ValidationError

from tcad_agent.reporting.traceability import TraceabilityMatrix, TraceabilityStatus
from tcad_agent.validation.models import ValidationReport


class RunOutcomeValues(TypedDict):
    run_id: UUID
    execution_state: Literal["failed", "completed"]
    validation_state: Literal["passed", "needs_review", "failed"]
    deliverable_state: Literal["complete", "incomplete"]
    report_state: Literal["complete", "missing", "failed"]
    overall_state: Literal["completed", "needs_attention", "failed"]
    failed_check_count: int
    unmet_deliverables: tuple[str, ...]
    project_root: Path


def outcome_evidence_summary(project_root: Path, *, max_failures: int = 3) -> str:
    """One researcher-facing sentence on the validation evidence, or empty text."""

    try:
        report = ValidationReport.model_validate_json(
            (project_root / "validation.json").read_text()
        )
    except (OSError, UnicodeDecodeError, ValidationError):
        return ""
    failed = [check for check in report.checks if check.status == "failed"]
    passed = sum(check.status == "passed" for check in report.checks)
    summary = f"Validation: {passed} checks passed, {len(failed)} failed."
    for check in failed[:max_failures]:
        summary += f" Failed: {check.id} - {check.message.strip()}"
        if not summary.endswith("."):
            summary += "."
    if len(failed) > max_failures:
        summary += f" (+{len(failed) - max_failures} more in the validation report.)"
    return summary


def derive_run_outcome(
    *,
    run_id: UUID,
    project_root: Path,
    execution_state: Literal["failed", "completed"],
    validation_state: Literal["passed", "needs_review", "failed"],
) -> RunOutcomeValues:
    project = project_root.resolve()
    report_state: Literal["complete", "missing", "failed"] = (
        "complete" if (project / "REPORT.md").is_file() else "missing"
    )
    failed_check_count = 0
    validation_path = project / "validation.json"
    try:
        validation = ValidationReport.model_validate_json(validation_path.read_text())
    except (OSError, UnicodeDecodeError, ValidationError):
        if validation_state == "passed":
            validation_state = "failed"
    else:
        failed_check_count = sum(
            check.status == "failed" for check in validation.checks
        )
    unmet: tuple[str, ...] = ()
    traceability_path = project / "traceability.json"
    try:
        traceability = TraceabilityMatrix.model_validate_json(
            traceability_path.read_text()
        )
    except (OSError, UnicodeDecodeError, ValidationError):
        deliverable_state: Literal["complete", "incomplete"] = "incomplete"
    else:
        unmet = tuple(
            record.deliverable
            for record in traceability.records
            if record.status is TraceabilityStatus.UNMET
        )
        deliverable_state = "complete" if not unmet else "incomplete"
    if execution_state == "failed":
        overall_state: Literal["completed", "needs_attention", "failed"] = "failed"
    elif (
        validation_state != "passed"
        or deliverable_state != "complete"
        or report_state != "complete"
    ):
        overall_state = "needs_attention"
    else:
        overall_state = "completed"
    return {
        "run_id": run_id,
        "execution_state": execution_state,
        "validation_state": validation_state,
        "deliverable_state": deliverable_state,
        "report_state": report_state,
        "overall_state": overall_state,
        "failed_check_count": failed_check_count,
        "unmet_deliverables": unmet,
        "project_root": project,
    }
