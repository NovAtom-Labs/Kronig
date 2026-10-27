"""Independent deterministic execution, scientific, and requested-output status."""

from tcad_agent.domain.models import ExperimentSpec, StrictModel
from tcad_agent.reporting.traceability import TraceabilityMatrix, build_traceability
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.engine import ValidationEngine
from tcad_agent.validation.models import ValidationReport, ValidationStatus


class AssessmentDimension(StrictModel):
    status: ValidationStatus
    message: str
    check_ids: tuple[str, ...] = ()
    failed_check_ids: tuple[str, ...] = ()


class ResultAssessment(StrictModel):
    execution: AssessmentDimension
    numerical: AssessmentDimension
    output_coverage: AssessmentDimension


def assess_result(
    result: CanonicalResult,
    *,
    spec: ExperimentSpec | None = None,
    validation: ValidationReport | None = None,
    traceability: TraceabilityMatrix | None = None,
) -> ResultAssessment:
    """Derive dimensions from canonical evidence, never from narrative summaries."""
    report = validation or ValidationEngine.for_backend(result.backend).validate(
        result, spec=spec
    )
    scientific = tuple(check for check in report.checks if check.level in {"numerical", "physical"})
    applicable = tuple(check for check in scientific if check.status != "not_applicable")
    failures = tuple(check.id for check in applicable if check.status == "failed")
    scientific_status: ValidationStatus = (
        "not_applicable"
        if not applicable
        else "failed"
        if failures
        else "warning"
        if any(check.status == "warning" for check in applicable)
        else "passed"
    )
    output = traceability or (build_traceability(spec, result) if spec else None)
    unmet = (
        tuple(record.deliverable for record in output.records if record.status == "unmet")
        if output
        else ()
    )
    output_status: ValidationStatus = (
        "not_applicable"
        if output is None or not output.records
        else "failed"
        if unmet
        else "passed"
    )
    completed = result.status == "completed"
    return ResultAssessment(
        execution=AssessmentDimension(
            status="passed" if completed else "failed",
            message="Simulator execution completed."
            if completed
            else f"Simulator execution ended with {result.status}.",
            check_ids=("execution-status",),
            failed_check_ids=() if completed else ("execution-status",),
        ),
        numerical=AssessmentDimension(
            status=scientific_status,
            message=f"{len(failures)} failed of {len(applicable)} applicable scientific checks."
            if applicable
            else "No applicable scientific checks are available.",
            check_ids=tuple(check.id for check in scientific),
            failed_check_ids=failures,
        ),
        output_coverage=AssessmentDimension(
            status=output_status,
            message="Requested output coverage is unavailable without reviewed requests."
            if output_status == "not_applicable"
            else f"{len(unmet)} requested outputs are missing, invalid, or incomplete."
            if unmet
            else "Every requested output has valid canonical evidence.",
            check_ids=tuple(record.deliverable for record in output.records) if output else (),
            failed_check_ids=unmet,
        ),
    )
