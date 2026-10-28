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


def test_a_compiler_rejection_is_found_before_a_plan_exists(valid_spec: ExperimentSpec) -> None:
    from tcad_agent.experiments.errors import ExperimentCompileError

    def reject(spec, backend):
        raise ValueError("unsafe identifier rejected by the compiler")

    engine = ExperimentEngine(precompile=reject)
    with pytest.raises(ExperimentCompileError, match=r"could not be generated.*unsafe identifier"):
        engine.prepare(valid_spec, "devsim")

def test_one_more_halving_is_earned_only_by_clear_convergence():
    from tcad_agent.experiments.service import _clearly_converging

    def record(*ratios):
        return {"relative_tolerance": 0.03, "metrics": [{"relative_linf": r} for r in ratios]}

    assert _clearly_converging([record(0.3), record(0.14), record(0.05)])  # 0.05 < 0.06, shrinking
    assert not _clearly_converging([record(0.3), record(0.1)])  # still far from the criterion
    assert not _clearly_converging([record(0.06), record(0.055)])  # wobbling, not closing in
    assert not _clearly_converging([record(0.05)])  # one comparison is no trend
    assert not _clearly_converging([record(0.1), {"metrics": []}])

def test_a_steadily_contracting_error_earns_more_halvings_than_a_wobbling_one():
    from tcad_agent.experiments.service import _clearly_converging

    def record(value):
        return {"metrics": [{"relative_linf": value}], "relative_tolerance": 0.03}

    assert _clearly_converging([record(0.47), record(0.21), record(0.089)])  # 0.4x per halving
    assert not _clearly_converging([record(0.47), record(0.40), record(0.35)])  # too slow
    assert not _clearly_converging([record(0.2), record(0.3), record(0.12)])  # not steady

def test_cheap_levels_keep_halving_while_the_error_is_still_shrinking():
    from tcad_agent.experiments.service import _cheap_and_closing

    def record(worst):
        return {"metrics": [{"relative_linf": worst}], "relative_tolerance": 0.03}

    history = [record(0.38), record(0.44), record(0.35), record(0.20)]
    # 1D: two further levels cost 4x the last one; they fit in half of what remains.
    assert _cheap_and_closing(history, last_seconds=40.0, remaining=6000.0, dimension=1)
    # 2D levels cost 4x each, so the same level time no longer leaves room for two more.
    assert not _cheap_and_closing(history, last_seconds=2400.0, remaining=4000.0, dimension=2)
    # An error that grew is not a trend worth following, however cheap.
    assert not _cheap_and_closing([record(0.2), record(0.3)], 1.0, 6000.0, 1)
    assert not _cheap_and_closing([record(0.2)], 1.0, 6000.0, 1)
    assert not _cheap_and_closing([record(0.2), {"metrics": []}], 1.0, 6000.0, 1)
