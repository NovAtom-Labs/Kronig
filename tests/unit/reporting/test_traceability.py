from tcad_agent.domain.models import Observable
from tcad_agent.reporting.markdown import MarkdownReport
from tcad_agent.reporting.traceability import TraceabilityStatus, build_traceability
from tcad_agent.results.models import CanonicalResult, FieldSeries
from tcad_agent.validation.models import ValidationCheck, ValidationReport


def test_nonfinite_terminal_evidence_is_not_delivered(valid_spec):
    from tcad_agent.results.models import BiasPoint

    spec = valid_spec.model_copy(update={"observables": (Observable.TERMINAL_CURRENT_DENSITY,)})
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        bias_points=(
            BiasPoint(
                bias_v=0,
                converged=True,
                terminal_currents_a_per_m2={contact.id: float("inf") for contact in spec.contacts},
            ),
        ),
    )
    assert not build_traceability(spec, result).complete


def test_incomplete_or_wrong_terminal_bias_schedule_is_not_delivered(valid_spec):
    from tcad_agent.domain.studies import DCPointsStudy
    from tcad_agent.results.models import BiasPoint

    spec = valid_spec.model_copy(
        update={
            "observables": (Observable.TERMINAL_CURRENT_DENSITY,),
            "study": DCPointsStudy(
                kind="dc_points", contact=valid_spec.contacts[0].id, values=("0 V", "0.1 V")
            ),
        }
    )
    point = BiasPoint(
        bias_v=0,
        converged=True,
        terminal_currents_a_per_m2={contact.id: 0 for contact in spec.contacts},
    )
    incomplete = CanonicalResult(backend="devsim", status="completed", bias_points=(point,))
    wrong = incomplete.model_copy(update={"bias_points": (point, point)})
    assert not build_traceability(spec, incomplete).complete
    assert not build_traceability(spec, wrong).complete


def test_empty_bias_currents_cannot_satisfy_charge_or_absolute_current(valid_spec):
    from tcad_agent.results.models import BiasPoint

    spec = valid_spec.model_copy(
        update={"observables": (Observable.ABSOLUTE_TERMINAL_CURRENT, Observable.TERMINAL_CHARGE)}
    )
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        bias_points=(BiasPoint(bias_v=0, converged=True, terminal_currents_a_per_m2={}),),
    )
    assert not build_traceability(spec, result).complete


def test_all_masked_dataset_is_not_delivered(valid_spec):
    result = canonical_result()
    dataset = result.datasets["potential"].model_copy(update={"validity": (False, False)})
    result = result.model_copy(update={"datasets": {"potential": dataset}})
    spec = valid_spec.model_copy(update={"observables": (Observable.POTENTIAL,)})
    assert not build_traceability(spec, result).complete


def test_ac_request_without_small_signal_evidence_is_unmet(valid_spec):
    from tcad_agent.domain.studies import ACStudy

    spec = valid_spec.model_copy(
        update={
            "study": ACStudy(kind="ac", contact="left", frequency="1 MHz", amplitude="10 mV"),
            "observables": (Observable.POTENTIAL,),
        }
    )
    matrix = build_traceability(spec, canonical_result())
    assert not matrix.complete
    assert any(
        record.deliverable == "study.ac" and record.status is TraceabilityStatus.UNMET
        for record in matrix.records
    )


def test_missing_requested_spatial_point_is_not_delivered(valid_spec):
    from tcad_agent.domain.models import ProfileSampling
    from tcad_agent.results.models import BiasPoint

    spec = valid_spec.model_copy(
        update={
            "observables": (Observable.POTENTIAL,),
            "profile_sampling": ProfileSampling(mode="explicit", bias_values=("0.1 V",)),
        }
    )
    result = canonical_result().model_copy(
        update={
            "bias_points": (BiasPoint(bias_v=0, converged=True, terminal_currents_a_per_m2={}),),
        }
    )
    assert not build_traceability(spec, result).complete


def canonical_result() -> CanonicalResult:
    return CanonicalResult(
        backend="devsim",
        status="completed",
        fields={
            "potential": FieldSeries(positions_m=(0.0, 1e-6), values=(0.0, 0.7), unit="V"),
            "electric_field": FieldSeries(positions_m=(0.0, 1e-6), values=(1.0, 2.0), unit="V/m"),
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
    spec = valid_spec.model_copy(update={"observables": (Observable.CONDUCTION_BAND,)})

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
