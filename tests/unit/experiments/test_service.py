import json
from pathlib import Path

import pytest

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.errors import (
    ExperimentCapabilityError,
    PlanDigestMismatchError,
)
from tcad_agent.experiments.models import PreparedExperiment
from tcad_agent.experiments.planning import expected_bias_points
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.policy import validation_policy_digest


def test_prepare_returns_stable_typed_plan_without_writing_files(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
) -> None:
    engine = ExperimentEngine()

    first = engine.prepare(valid_spec, "devsim", warnings=("local-only",))
    second = engine.prepare(valid_spec, "devsim", warnings=("local-only",))

    assert isinstance(first, PreparedExperiment)
    assert first == second
    assert first.schema_version == "1.0"
    assert first.backend == "devsim"
    assert first.spec == valid_spec
    assert first.plan["spec"] == valid_spec.normalized()
    assert first.plan["backend"] == "devsim"
    assert first.plan["warnings"] == ["local-only"]
    assert first.completeness.ready
    assert first.plan["scientific_input_ledger"]
    assert len(first.plan_digest) == 64
    assert len(first.capability_digest) == 64
    assert tuple(tmp_path.iterdir()) == ()


def test_recovery_review_is_part_of_exact_approved_plan(valid_spec):
    from tcad_agent.recovery.models import FailureKind, FailureRecord, RecoveryAction
    from tcad_agent.recovery.proposals import RecoveryProposalService

    proposal = RecoveryProposalService().propose(
        valid_spec,
        action=RecoveryAction.REFINE_MESH,
        failure=FailureRecord(kind=FailureKind.NON_CONVERGENCE, evidence="Convergence failed"),
        original_bundle_id="original-run",
        validation_limits={"current_atol": 1e-6},
        validation_policy_digest=validation_policy_digest(),
    )
    engine = ExperimentEngine()
    prepared = engine.prepare(proposal.candidate_spec, "devsim", recovery_proposal=proposal)

    assert prepared.recovery_proposal == proposal
    assert prepared.plan["recovery_proposal"]["original_bundle_id"] == "original-run"
    assert prepared.plan_digest != engine.prepare(proposal.candidate_spec, "devsim").plan_digest


def test_prepare_digest_changes_with_scientific_intent_or_backend(
    valid_spec: ExperimentSpec,
) -> None:
    engine = ExperimentEngine()
    changed = valid_spec.model_copy(update={"name": "same-structure-different-study-identity"})

    baseline = engine.prepare(valid_spec, "devsim")
    changed_spec = engine.prepare(changed, "devsim")
    changed_backend = engine.prepare(valid_spec, "sentaurus")

    assert baseline.plan_digest != changed_spec.plan_digest
    assert baseline.plan_digest != changed_backend.plan_digest


def test_prepare_refuses_unsupported_physics(
    unsupported_spec: ExperimentSpec,
) -> None:
    with pytest.raises(ExperimentCapabilityError) as captured:
        ExperimentEngine().prepare(unsupported_spec, "devsim")

    assert captured.value.decision.backend == "devsim"
    assert captured.value.decision.status == "backend_unsupported"
    assert captured.value.decision.issues


def test_execute_rejects_digest_before_creating_output(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
) -> None:
    engine = ExperimentEngine()
    prepared = engine.prepare(valid_spec, "devsim")

    with pytest.raises(PlanDigestMismatchError):
        engine.execute(
            prepared,
            approved_plan_digest="0" * 64,
            output_root=tmp_path / "runs",
            budget=RunBudget(seconds=30),
        )

    assert not (tmp_path / "runs").exists()


def test_expected_point_count_uses_all_explicit_dc_points() -> None:
    payload = json.loads(
        Path("tests/fixtures/workflows/compensated_gaussian_three_point.json").read_text()
    )
    spec = ExperimentSpec.model_validate(payload)

    assert expected_bias_points(spec) == 3


def test_recovery_refuses_partial_acceptance_before_simulator(tmp_path, valid_spec):
    from tcad_agent.recovery.models import FailureKind, FailureRecord, RecoveryAction
    from tcad_agent.recovery.proposals import RecoveryProposalService

    proposal = RecoveryProposalService().propose(
        valid_spec,
        action=RecoveryAction.REFINE_MESH,
        failure=FailureRecord(kind=FailureKind.CONSERVATION, evidence="residual"),
        original_bundle_id="original",
        validation_limits={"current_atol": 1e-6},
        validation_policy_digest=validation_policy_digest(),
    )
    engine = ExperimentEngine(backend_resolver=lambda _: pytest.fail("solver must not run"))
    prepared = engine.prepare(proposal.candidate_spec, "devsim", recovery_proposal=proposal)
    with pytest.raises(ValueError, match=r"complete.*acceptance"):
        engine.execute(
            prepared,
            approved_plan_digest=prepared.plan_digest,
            output_root=tmp_path / "runs",
            budget=RunBudget(seconds=30),
        )
    assert not (tmp_path / "runs").exists()
