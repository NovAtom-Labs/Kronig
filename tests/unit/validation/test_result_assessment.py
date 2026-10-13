from tcad_agent.reporting.traceability import DeliverableTrace, TraceabilityMatrix
from tcad_agent.results.models import BiasPoint, CanonicalResult
from tcad_agent.validation import assessment
from tcad_agent.validation.engine import ValidationEngine


def test_completed_execution_can_have_failed_science_and_complete_outputs() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("a", "b"),
        bias_points=(
            BiasPoint(bias_v=0, converged=True, terminal_currents_a_per_m2={"a": 2.0, "b": 0.0}),
        ),
    )
    output = TraceabilityMatrix(
        records=(
            DeliverableTrace(
                deliverable="terminal_current",
                status="satisfied",
                evidence_datasets=("bias_points",),
                rationale="Both terminal currents recorded.",
            ),
        )
    )
    status = assessment.assess_result(result, traceability=output)
    assert status.execution.status == "passed"
    assert status.numerical.status == "failed"
    assert "terminal-current-conservation" in status.numerical.failed_check_ids
    assert status.output_coverage.status == "passed"


def test_unrequested_output_coverage_is_not_a_vacuous_pass() -> None:
    result = CanonicalResult(backend="devsim", status="execution_failed")
    status = assessment.assess_result(result, validation=ValidationEngine().validate(result))
    assert status.execution.status == "failed"
    assert status.output_coverage.status == "not_applicable"
    assert status == assessment.assess_result(result)


def test_missing_outputs_do_not_change_execution_status() -> None:
    result = CanonicalResult(backend="devsim", status="completed")
    output = TraceabilityMatrix(
        records=(
            DeliverableTrace(
                deliverable="potential", status="unmet", rationale="Potential missing."
            ),
        )
    )
    status = assessment.assess_result(result, traceability=output)
    assert status.execution.status == "passed"
    assert status.output_coverage.status == "failed"
    assert status.output_coverage.failed_check_ids == ("potential",)
