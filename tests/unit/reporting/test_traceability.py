from tcad_agent.domain.models import Observable
from tcad_agent.reporting.markdown import MarkdownReport
from tcad_agent.reporting.traceability import TraceabilityStatus, build_traceability
from tcad_agent.results.models import CanonicalResult, FieldSeries
from tcad_agent.validation.models import ValidationCheck, ValidationReport


def canonical_result() -> CanonicalResult:
    return CanonicalResult(
        backend="devsim",
        status="completed",
        fields={
            "potential": FieldSeries(
                positions_m=(0.0, 1e-6), values=(0.0, 0.7), unit="V"
            ),
            "electric_field": FieldSeries(
                positions_m=(0.0, 1e-6), values=(1.0, 2.0), unit="V/m"
            ),
        },
    )


def test_traceability_maps_requested_observables_to_canonical_evidence(
    valid_spec,
) -> None:
    spec = valid_spec.model_copy(
        update={"observables": (Observable.POTENTIAL, Observable.ELECTRIC_FIELD)}
    )

    matrix = build_traceability(spec, canonical_result())

    records = {record.deliverable: record for record in matrix.records}
    assert records["potential"].status is TraceabilityStatus.SATISFIED
    assert records["potential"].evidence_datasets == ("potential",)
    assert records["electric_field"].status is TraceabilityStatus.SATISFIED


def test_traceability_marks_missing_requested_observable_unmet(
    valid_spec,
) -> None:
    spec = valid_spec.model_copy(
        update={"observables": (Observable.CONDUCTION_BAND,)}
    )

    matrix = build_traceability(spec, canonical_result())

    assert matrix.records[0].status is TraceabilityStatus.UNMET


def test_report_humanizes_nonpassing_validation_without_claiming_failure(
    valid_spec,
) -> None:
    validation = ValidationReport(
        overall="warning",
        checks=(
            ValidationCheck(
                id="charge_balance",
                level="physical",
                status="warning",
                message="Review the boundary charge balance.",
            ),
        ),
    )

    report = MarkdownReport().render(valid_spec, canonical_result(), validation)

    assert "**Outcome:** Checks need attention" in report
    assert "**Outcome:** Failed" not in report
