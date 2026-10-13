from pathlib import Path

import pytest
import yaml

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.recovery import proposals
from tcad_agent.recovery.models import FailureKind, FailureRecord, RecoveryAction
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationCheck, ValidationReport
from tcad_agent.validation.policy import validation_policy_digest


def original_spec() -> ExperimentSpec:
    payload = yaml.safe_load(Path("examples/al-pn-al-equilibrium-devsim.yaml").read_text())
    payload["study"] = {"kind": "dc_points", "contact": "anode", "values": ["0 V", "0.1 V"]}
    return ExperimentSpec.model_validate(payload)


@pytest.mark.parametrize(
    "action,path,value",
    [
        (RecoveryAction.INCREASE_ITERATION_LIMIT, "solver.maximum_iterations", 160),
        (RecoveryAction.REFINE_MESH, "regions[0].mesh_spacing", 1e-8),
        (RecoveryAction.REDUCE_BIAS_STEP, "study.minimum_step", 0.05),
    ],
)
def test_proposals_preserve_physics_outputs_limits_and_original_spec(action, path, value) -> None:
    spec = original_spec()
    before = spec.model_dump_json()
    proposal = proposals.RecoveryProposalService().propose(
        spec,
        action=action,
        failure=FailureRecord(
            kind=FailureKind.NON_CONVERGENCE, evidence="One requested point failed."
        ),
        original_bundle_id="run-original",
        validation_limits={"current_atol": 1e-6, "current_rtol": 1e-4},
    )
    assert spec.model_dump_json() == before
    assert proposal.candidate_spec.physics == spec.physics
    assert proposal.candidate_spec.observables == spec.observables
    assert proposal.candidate_spec.study.values == spec.study.values
    assert len(proposal.original_spec_digest) == 64
    assert proposal.original_spec_digest != proposal.candidate_spec_digest
    assert proposal.original_bundle_id == "run-original"
    assert proposal.requires_review and not proposal.automatic_execution
    assert {entry.name: entry.value for entry in proposal.validation_limits} == {
        "current_atol": 1e-6,
        "current_rtol": 1e-4,
    }
    assert path in {change.path for change in proposal.changes}
    if action is RecoveryAction.INCREASE_ITERATION_LIMIT:
        assert proposal.candidate_spec.solver.maximum_iterations == value
        assert proposal.candidate_spec.solver.relative_error == spec.solver.relative_error
    elif action is RecoveryAction.REFINE_MESH:
        assert proposal.candidate_spec.regions[0].mesh_spacing.to("m") == pytest.approx(value)
    else:
        assert proposal.candidate_spec.study.minimum_step.to("V") == pytest.approx(value)
        assert proposal.candidate_spec.study.strategy == "adaptive"


def test_conservation_does_not_offer_relaxed_solver_or_validation_limits() -> None:
    with pytest.raises(ValueError, match="supported"):
        proposals.RecoveryProposalService().propose(
            original_spec(),
            action=RecoveryAction.INCREASE_ITERATION_LIMIT,
            failure=FailureRecord(
                kind=FailureKind.CONSERVATION, evidence="Residual exceeds bound."
            ),
            original_bundle_id="run-original",
            validation_limits={"current_atol": 1e-6},
        )


def test_comparison_refuses_unreviewed_candidate_and_preserves_both_bundle_identities() -> None:
    service = proposals.RecoveryProposalService()
    proposal = service.propose(
        original_spec(),
        action=RecoveryAction.REFINE_MESH,
        failure=FailureRecord(kind=FailureKind.CONSERVATION, evidence="Residual exceeds bound."),
        original_bundle_id="run-original",
        validation_limits={"current_atol": 1e-6},
        validation_policy_digest=validation_policy_digest(),
    )
    with pytest.raises(ValueError, match="reviewed"):
        service.record_comparison(proposal, reviewed_spec=original_spec(), new_bundle_id="run-new")
    comparison = service.record_comparison(
        proposal, reviewed_spec=proposal.candidate_spec, new_bundle_id="run-new"
    )
    assert comparison.original_bundle_id == "run-original"
    assert comparison.new_bundle_id == "run-new"
    assert comparison.original_spec_digest == proposal.original_spec_digest
    assert comparison.candidate_spec_digest == proposal.candidate_spec_digest
    assert comparison.validation_policy_digest == proposal.validation_policy_digest
    with pytest.raises(ValueError, match="distinct"):
        service.record_comparison(
            proposal, reviewed_spec=proposal.candidate_spec, new_bundle_id="run-original"
        )


def test_recovery_failures_are_selected_from_stored_validation_only() -> None:
    result = CanonicalResult(backend="devsim", status="completed")
    report = ValidationReport(
        overall="failed",
        checks=(
            ValidationCheck(
                id="terminal-current-conservation",
                level="physical",
                status="failed",
                measured_value=2e-6,
                limit=1e-6,
                message="Original configured bound exceeded.",
            ),
        ),
    )
    failures = proposals.recovery_failures_from_report(result, report)
    assert len(failures) == 1
    assert failures[0].kind is FailureKind.CONSERVATION
    assert "terminal-current-conservation" in failures[0].evidence
    passed = report.model_copy(update={"overall": "passed", "checks": ()})
    assert proposals.recovery_failures_from_report(result, passed) == ()


def test_execution_comparison_refuses_missing_recorded_validation_policy() -> None:
    service = proposals.RecoveryProposalService()
    proposal = service.propose(
        original_spec(),
        action=RecoveryAction.REFINE_MESH,
        failure=FailureRecord(kind=FailureKind.CONSERVATION, evidence="Current residual"),
        original_bundle_id="run-original",
        validation_limits={"current_atol": 1e-6},
    )
    with pytest.raises(ValueError, match="validation policy"):
        service.record_comparison(
            proposal, reviewed_spec=proposal.candidate_spec, new_bundle_id="run-new"
        )


def test_execution_comparison_refuses_changed_validation_policy(monkeypatch) -> None:
    service = proposals.RecoveryProposalService()
    proposal = service.propose(
        original_spec(),
        action=RecoveryAction.REFINE_MESH,
        failure=FailureRecord(kind=FailureKind.CONSERVATION, evidence="Current residual"),
        original_bundle_id="run-original",
        validation_limits={"current_atol": 1e-6},
        validation_policy_digest=validation_policy_digest(),
    )
    monkeypatch.setattr(proposals, "current_validation_policy_digest", lambda: "0" * 64)
    with pytest.raises(ValueError, match="validation policy"):
        service.record_comparison(
            proposal, reviewed_spec=proposal.candidate_spec, new_bundle_id="run-new"
        )
