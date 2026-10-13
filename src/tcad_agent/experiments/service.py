"""One deterministic preparation-to-bundle execution engine."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from tcad_agent.adapters.registry import BackendBinding, get_backend
from tcad_agent.bundles.models import BundleInputs, ExperimentBundle
from tcad_agent.bundles.writer import BundleWriter
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.events.ledger import EventLedger
from tcad_agent.events.models import RunEventKind
from tcad_agent.experiments.errors import (
    ExperimentCapabilityError,
    ExperimentExecutionError,
    PlanDigestMismatchError,
)
from tcad_agent.experiments.models import PreparedExperiment
from tcad_agent.experiments.planning import (
    build_plan,
    digest_capability,
    digest_plan,
    expected_bias_points,
)
from tcad_agent.recovery.proposals import RecoveryProposal, RecoveryProposalService
from tcad_agent.runners.models import RunBudget
from tcad_agent.science.completeness import ScientificCompletenessEngine
from tcad_agent.validation.engine import ValidationEngine


class ExperimentEngine:
    """Prepare and execute typed experiments without interpreting prompts."""

    def __init__(
        self,
        *,
        backend_resolver: Callable[[str], BackendBinding] = get_backend,
    ) -> None:
        self.backend_resolver = backend_resolver

    def prepare(
        self,
        spec: ExperimentSpec,
        backend: str,
        *,
        warnings: tuple[str, ...] = (),
        recovery_proposal: RecoveryProposal | None = None,
    ) -> PreparedExperiment:
        manifest = CapabilityManifest.from_backend(backend)
        decision = CapabilityService().check(spec, manifest)
        if decision.status is not CapabilityStatus.SUPPORTED:
            raise ExperimentCapabilityError(decision)
        completeness = ScientificCompletenessEngine().evaluate(spec, backend)
        plan = build_plan(spec, backend, warnings, completeness)
        if recovery_proposal is not None:
            # Check the reviewed candidate before including its comparison in approval.
            RecoveryProposalService().record_comparison(
                recovery_proposal, reviewed_spec=spec, new_bundle_id="pending-recovery-review"
            )
            plan["recovery_proposal"] = recovery_proposal.model_dump(mode="json")
        return PreparedExperiment(
            backend=backend,
            spec=spec,
            plan=plan,
            plan_digest=digest_plan(plan),
            capability_digest=digest_capability(manifest),
            completeness=completeness,
            warnings=warnings,
            recovery_proposal=recovery_proposal,
        )

    def execute(
        self,
        prepared: PreparedExperiment,
        *,
        approved_plan_digest: str,
        output_root: Path,
        budget: RunBudget,
        run_id: str | None = None,
    ) -> ExperimentBundle:
        if approved_plan_digest != prepared.plan_digest:
            raise PlanDigestMismatchError("approval does not match the prepared experiment plan")
        if digest_plan(prepared.plan) != prepared.plan_digest:
            raise PlanDigestMismatchError("prepared experiment plan was modified")
        expected = self.prepare(
            prepared.spec,
            prepared.backend,
            warnings=prepared.warnings,
            recovery_proposal=prepared.recovery_proposal,
        )
        if expected != prepared:
            raise PlanDigestMismatchError(
                "prepared experiment no longer matches backend capabilities"
            )

        validation_engine = ValidationEngine()
        if prepared.recovery_proposal is not None:
            limits = {
                limit.name: limit.value for limit in prepared.recovery_proposal.validation_limits
            }
            if (
                len(limits) != len(prepared.recovery_proposal.validation_limits)
                or limits.keys() != validation_engine.acceptance_limits().keys()
            ):
                raise ValueError("Recovery requires a complete recorded acceptance limit mapping")
            validation_engine = ValidationEngine(**limits)

        selected_run_id = run_id or f"run-{uuid4().hex[:12]}"
        root = output_root.resolve()
        work = root / ".work" / selected_run_id
        staging = root / f".{selected_run_id}.staging"
        ledger = EventLedger(work / "events.jsonl")
        try:
            binding = self.backend_resolver(prepared.backend)
            ledger.append(
                RunEventKind.REQUESTED,
                {"backend": prepared.backend, "plan_digest": prepared.plan_digest},
            )
            ledger.append(
                RunEventKind.VALIDATED,
                {"capability_digest": prepared.capability_digest},
            )
            ledger.append(
                RunEventKind.APPROVED,
                {"plan_digest": approved_plan_digest},
            )
            job = binding.adapter.compile(prepared.spec, work / "compiled")
            ledger.append(RunEventKind.COMPILED, {"backend": prepared.backend})
            ledger.append(
                RunEventKind.STARTED,
                {"backend": prepared.backend, "timeout_seconds": budget.seconds},
            )
            native = binding.runner.run(job, budget)
            result = binding.adapter.normalize(native)
            validation = validation_engine.validate(
                result,
                expected_bias_points=expected_bias_points(prepared.spec),
                spec=prepared.spec,
            )
            terminal = (
                RunEventKind.COMPLETED
                if native.status == "completed" and validation.overall == "passed"
                else RunEventKind.FAILED
            )
            ledger.append(
                terminal,
                {
                    "execution_status": native.status,
                    "validation_status": validation.overall,
                },
            )
            return BundleWriter(root).write(
                BundleInputs(
                    run_id=selected_run_id,
                    spec=prepared.spec,
                    job=job,
                    native=native,
                    result=result,
                    validation=validation,
                    events_path=ledger.path,
                    completeness=prepared.completeness,
                    recovery_comparison=RecoveryProposalService().record_comparison(
                        prepared.recovery_proposal,
                        reviewed_spec=prepared.spec,
                        new_bundle_id=selected_run_id,
                    )
                    if prepared.recovery_proposal is not None
                    else None,
                )
            )
        except PlanDigestMismatchError:
            raise
        except Exception as exc:
            raise ExperimentExecutionError(f"Simulator execution failed: {exc}") from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)
            shutil.rmtree(staging, ignore_errors=True)
