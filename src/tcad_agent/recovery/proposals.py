"""Reviewable numerical alternatives; this module never executes a simulation."""

import hashlib
import json
from collections.abc import Mapping
from itertools import pairwise
from typing import Literal

from pydantic import Field, JsonValue

from tcad_agent.domain.models import ExperimentSpec, StrictModel
from tcad_agent.domain.studies import DCPointsStudy, DCStudy, expand_study_points
from tcad_agent.domain.units import QuantityValue
from tcad_agent.recovery.models import FailureKind, FailureRecord, RecoveryAction
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationReport
from tcad_agent.validation.policy import (
    validation_policy_digest as current_validation_policy_digest,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def spec_digest(spec: ExperimentSpec) -> str:
    return _digest(spec.model_dump(mode="json"))


def recovery_failures_from_report(
    result: CanonicalResult,
    validation: ValidationReport,
) -> tuple[FailureRecord, ...]:
    """Use recorded validation evidence without re-evaluating acceptance thresholds."""
    execution_kinds = {
        "execution_failed": FailureKind.EXECUTION,
        "timed_out": FailureKind.TIMEOUT,
        "malformed_result": FailureKind.MALFORMED_OUTPUT,
    }
    if result.status in execution_kinds:
        return (
            FailureRecord(
                kind=execution_kinds[result.status], evidence=result.error or result.status
            ),
        )
    kinds_by_check = {
        "execution-status": FailureKind.EXECUTION,
        "all-points-converged": FailureKind.NON_CONVERGENCE,
        "operating-points-converged": FailureKind.NON_CONVERGENCE,
        "small-signal-grid-complete": FailureKind.NON_CONVERGENCE,
        "finite-values": FailureKind.NONFINITE_RESULT,
        "terminal-current-conservation": FailureKind.CONSERVATION,
        "contact-charge-balance": FailureKind.CONSERVATION,
        "requested-observables-present": FailureKind.MALFORMED_OUTPUT,
        "bias-points-present": FailureKind.MALFORMED_OUTPUT,
        "expected-point-count": FailureKind.MALFORMED_OUTPUT,
    }
    failures = []
    for check in validation.checks:
        if check.status != "failed":
            continue
        kind = kinds_by_check.get(check.id)
        if kind is None and check.level == "physical":
            kind = FailureKind.PHYSICAL_SANITY
        if kind is not None:
            failures.append(
                FailureRecord(
                    kind=kind,
                    evidence=f"{check.id}: {check.message} "
                    f"(measured={check.measured_value!r}, bound={check.limit!r})",
                )
            )
    return tuple(failures)


class NumericChange(StrictModel):
    path: str
    before: JsonValue
    after: JsonValue


class AcceptanceLimit(StrictModel):
    name: str = Field(min_length=1)
    value: float = Field(ge=0, allow_inf_nan=False)


class RecoveryProposal(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    action: RecoveryAction
    failure: FailureRecord
    original_bundle_id: str = Field(min_length=1)
    original_spec_digest: str
    candidate_spec_digest: str
    preserved_physics_digest: str
    candidate_spec: ExperimentSpec
    changes: tuple[NumericChange, ...]
    validation_limits: tuple[AcceptanceLimit, ...]
    validation_policy_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    requires_review: Literal[True] = True
    automatic_execution: Literal[False] = False


class RecoveryComparison(StrictModel):
    original_bundle_id: str
    new_bundle_id: str
    original_spec_digest: str
    candidate_spec_digest: str
    preserved_physics_digest: str
    action: RecoveryAction
    changes: tuple[NumericChange, ...]
    validation_limits: tuple[AcceptanceLimit, ...]
    validation_policy_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class RecoveryProposalService:
    def propose(
        self,
        spec: ExperimentSpec,
        *,
        action: RecoveryAction,
        failure: FailureRecord,
        original_bundle_id: str,
        validation_limits: Mapping[str, float],
        validation_policy_digest: str | None = None,
    ) -> RecoveryProposal:
        """Propose one bounded change with preserved requests and acceptance limits."""
        allowed = {
            FailureKind.NON_CONVERGENCE: {
                RecoveryAction.INCREASE_ITERATION_LIMIT,
                RecoveryAction.REFINE_MESH,
                RecoveryAction.REDUCE_BIAS_STEP,
            },
            FailureKind.CONSERVATION: {RecoveryAction.REFINE_MESH},
        }
        if action is not RecoveryAction.STOP_AND_REPORT and action not in allowed.get(
            failure.kind, set()
        ):
            raise ValueError("action is not supported for this scientific failure")
        if not validation_limits:
            raise ValueError("reviewed validation limits are required")
        limits = tuple(
            AcceptanceLimit(name=name, value=value)
            for name, value in sorted(validation_limits.items())
        )
        payload = spec.model_dump(mode="json")
        changes: list[NumericChange] = []

        def change(target: dict[str, JsonValue], key: str, after: JsonValue, path: str) -> None:
            before = target.get(key)
            if before != after:
                changes.append(NumericChange(path=path, before=before, after=after))
                target[key] = after

        if action is RecoveryAction.INCREASE_ITERATION_LIMIT:
            iterations = min(1000, spec.solver.maximum_iterations * 2)
            change(payload["solver"], "maximum_iterations", iterations, "solver.maximum_iterations")
        elif action is RecoveryAction.REFINE_MESH:
            for index, region in enumerate(payload["regions"]):
                for key in ("mesh_spacing", "minimum_mesh_spacing", "maximum_mesh_spacing"):
                    if region.get(key) is not None:
                        quantity = dict(region[key])
                        quantity["magnitude_si"] /= 2
                        change(region, key, quantity, f"regions[{index}].{key}")
            for index, anchor in enumerate(payload["mesh_anchors"]):
                quantity = dict(anchor["spacing"])
                quantity["magnitude_si"] /= 2
                change(anchor, "spacing", quantity, f"mesh_anchors[{index}].spacing")
        elif action is RecoveryAction.REDUCE_BIAS_STEP:
            schedule = getattr(spec.study, "bias_schedule", None) or spec.study
            if not isinstance(schedule, DCStudy | DCPointsStudy):
                raise ValueError("reduced continuation steps require an approved DC schedule")
            values = tuple(value.to("V") for value in expand_study_points(schedule))
            steps = tuple(abs(right - left) for left, right in pairwise(values) if right != left)
            if not steps:
                raise ValueError("reduced continuation steps require distinct approved voltages")
            minimum = schedule.minimum_step.to("V") if schedule.minimum_step else min(steps)
            target = payload["study"].get("bias_schedule") or payload["study"]
            path = "study.bias_schedule" if getattr(spec.study, "bias_schedule", None) else "study"
            change(target, "strategy", "adaptive", f"{path}.strategy")
            quantity = QuantityValue.model_validate(f"{minimum / 2:.15g} V").model_dump(mode="json")
            change(target, "minimum_step", quantity, f"{path}.minimum_step")
        if not changes and action is not RecoveryAction.STOP_AND_REPORT:
            raise ValueError("no supported numerical change remains within the configured bounds")
        candidate = ExperimentSpec.model_validate(payload)
        return RecoveryProposal(
            action=action,
            failure=failure,
            original_bundle_id=original_bundle_id,
            original_spec_digest=spec_digest(spec),
            candidate_spec_digest=spec_digest(candidate),
            preserved_physics_digest=_digest(spec.physics.model_dump(mode="json")),
            candidate_spec=candidate,
            changes=tuple(changes),
            validation_limits=limits,
            validation_policy_digest=validation_policy_digest,
        )

    def record_comparison(
        self,
        proposal: RecoveryProposal,
        *,
        reviewed_spec: ExperimentSpec,
        new_bundle_id: str,
    ) -> RecoveryComparison:
        """Record identities after a separately reviewed and executed new experiment."""
        if spec_digest(reviewed_spec) != proposal.candidate_spec_digest:
            raise ValueError("reviewed experiment does not match the proposed candidate digest")
        physics_digest = _digest(reviewed_spec.physics.model_dump(mode="json"))
        if physics_digest != proposal.preserved_physics_digest:
            raise ValueError("reviewed physics differs from the original experiment")
        if not new_bundle_id or new_bundle_id == proposal.original_bundle_id:
            raise ValueError("new and original result bundle identities must be distinct")
        if proposal.validation_policy_digest is None:
            raise ValueError("the original recorded validation policy digest is missing")
        if proposal.validation_policy_digest != current_validation_policy_digest():
            raise ValueError("the current validation policy differs from the recorded policy")
        return RecoveryComparison(
            original_bundle_id=proposal.original_bundle_id,
            new_bundle_id=new_bundle_id,
            original_spec_digest=proposal.original_spec_digest,
            candidate_spec_digest=proposal.candidate_spec_digest,
            preserved_physics_digest=proposal.preserved_physics_digest,
            action=proposal.action,
            changes=proposal.changes,
            validation_limits=proposal.validation_limits,
            validation_policy_digest=proposal.validation_policy_digest,
        )
