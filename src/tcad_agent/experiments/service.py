"""One deterministic preparation-to-bundle execution engine."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from tcad_agent.adapters.registry import BackendBinding, get_backend
from tcad_agent.bundles.models import BundleInputs, ExperimentBundle, require_run_id
from tcad_agent.bundles.writer import BundleWriter
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.events.ledger import EventLedger
from tcad_agent.events.models import RunEventKind
from tcad_agent.experiments.errors import (
    ExperimentCapabilityError,
    ExperimentCompileError,
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
from tcad_agent.runners.process import ExecutionCancelled, raise_if_cancelled
from tcad_agent.science.completeness import ScientificCompletenessEngine
from tcad_agent.validation.engine import ValidationEngine
from tcad_agent.validation.refinement import mesh_comparison, refined_spec


def _clearly_converging(history: list[dict]) -> bool:
    """Whether one more halving is justified: the last two comparisons are closing in.

    The response must already be within twice the criterion and have shrunk by at least 40%
    since the comparison before, so a result that merely wobbles never earns extra solves.
    """

    def worst(record: dict) -> float | None:
        values = [m["relative_linf"] for m in record.get("metrics", []) if "relative_linf" in m]
        return max(values) if values else None

    if len(history) < 2:
        return False
    previous, last = worst(history[-2]), worst(history[-1])
    if previous is None or last is None or previous <= 0:
        return False
    tolerance = history[-1].get("relative_tolerance", 0.03)
    if last <= 2 * tolerance and last <= 0.6 * previous:
        return True
    # A response still above twice the criterion earns another halving only when it has
    # contracted twice running and, at that rate, two more halvings would bring it inside.
    if len(history) < 3:
        return False
    earlier = worst(history[-3])
    ratio = last / previous
    return (
        earlier is not None
        and previous <= 0.6 * earlier
        and ratio <= 0.6
        and last * ratio * ratio <= tolerance
    )


def _precompile(spec: ExperimentSpec, backend: str) -> None:
    binding = get_backend(backend)
    with tempfile.TemporaryDirectory(prefix="kronig-precompile-") as scratch:
        binding.adapter.compile(spec, Path(scratch) / "compiled")


# A refined mesh costs more than the run it checks, so each level keeps a floor of its own
# instead of inheriting whatever is left of the original run's allowance.
_REFINEMENT_RUN_SECONDS = 2400
_MESH_VERIFICATION_SECONDS = 7200
_MAX_MESH_LEVELS = 6

class ExperimentEngine:
    """Prepare and execute typed experiments without interpreting prompts."""

    def __init__(
        self,
        *,
        backend_resolver: Callable[[str], BackendBinding] = get_backend,
        precompile: Callable[[ExperimentSpec, str], None] | None = None,
    ) -> None:
        self.backend_resolver = backend_resolver
        self.precompile = precompile or _precompile

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
        self._check_compiles(spec, backend)
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

    def _check_compiles(self, spec: ExperimentSpec, backend: str) -> None:
        """Generate the simulator input once, discarded, so a rejection happens before approval.

        A plan the researcher approves must be one the compiler accepts; finding out afterwards
        wastes their approval and the run.
        """
        try:
            self.precompile(spec, backend)
        except Exception as exc:
            raise ExperimentCompileError(
                f"The simulator input could not be generated for this experiment: {exc}"
            ) from exc

    def execute(
        self,
        prepared: PreparedExperiment,
        *,
        approved_plan_digest: str,
        output_root: Path,
        budget: RunBudget,
        run_id: str | None = None,
    ) -> ExperimentBundle:
        raise_if_cancelled()
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

        validation_engine = ValidationEngine.for_backend(prepared.backend)
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

        selected_run_id = require_run_id(
            run_id if run_id is not None else f"run-{uuid4().hex[:12]}"
        )
        root = output_root.resolve()
        work = root / ".work" / selected_run_id
        staging = root / f".{selected_run_id}.staging"
        if (root / selected_run_id).exists() or staging.exists():
            raise ExperimentExecutionError("run ID already has saved or staged results")
        try:
            work.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise ExperimentExecutionError("run ID is already in use") from exc
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
            raise_if_cancelled()
            ledger.append(RunEventKind.COMPILED, {"backend": prepared.backend})
            ledger.append(
                RunEventKind.STARTED,
                {"backend": prepared.backend, "timeout_seconds": budget.seconds},
            )
            native = binding.runner.run(job, budget)
            raise_if_cancelled()
            result = binding.adapter.normalize(native)
            mesh_root = None
            if result.status == "completed" and result.operating_points:
                mesh_root = work / "mesh-verification"
                mesh_root.mkdir()
                original = mesh_root / "level-00"
                original.mkdir()
                (original / "experiment.json").write_text(prepared.spec.model_dump_json(indent=2))
                (original / "canonical.json").write_text(result.model_dump_json(indent=2))
                shutil.copytree(job.entrypoint.parent, original / "compiled")
                (original / "provenance.json").write_text(
                    json.dumps(
                        {
                            "input_digest": job.input_digest,
                            "runtime_digest": job.runtime_digest,
                            "compiler_version": job.compiler_version,
                            "simulator_version": result.simulator_version,
                            "execution_state": native.status,
                            "elapsed_seconds": native.elapsed_seconds,
                        },
                        indent=2,
                    )
                )
                coarse_spec = prepared.spec
                record = {
                    "status": "failed",
                    "relative_tolerance": 0.03,
                    "reason": "Execution budget exhausted before mesh verification.",
                }
                # Verification has its own allowance: the run budget sizes one execution, and a
                # refined mesh is several more of them, each costlier than the last.
                elapsed = 0.0
                history = []
                level = 0
                limit = 4
                while level < limit:
                    level += 1
                    raise_if_cancelled()
                    remaining = _MESH_VERIFICATION_SECONDS - elapsed
                    if remaining <= 0:
                        record = {
                            **record,
                            "status": "failed",
                            "reason": "Mesh verification exhausted its total execution budget.",
                        }
                        break
                    fine_spec = refined_spec(coarse_spec)
                    level_root = mesh_root / f"level-{level:02d}"
                    level_root.mkdir()
                    (level_root / "experiment.json").write_text(fine_spec.model_dump_json(indent=2))
                    started = time.monotonic()
                    try:
                        fine_job = binding.adapter.compile(fine_spec, level_root / "compiled")
                        raise_if_cancelled()
                        fine_native = binding.runner.run(
                            fine_job,
                            RunBudget(seconds=min(max(budget.seconds, _REFINEMENT_RUN_SECONDS), 3600)),
                        )
                        raise_if_cancelled()
                        fine_result = binding.adapter.normalize(fine_native)
                        (level_root / "canonical.json").write_text(
                            fine_result.model_dump_json(indent=2)
                        )
                        record = mesh_comparison(
                            result,
                            fine_result,
                            equilibrium=prepared.spec.study.kind == "equilibrium",
                            # At equilibrium the true current is zero, so what the solver
                            # leaves is noise bounded by the equilibrium criterion itself.
                            current_absolute_tolerance=(
                                validation_engine._equilibrium_current_atol(prepared.spec)
                                if prepared.spec.study.kind == "equilibrium"
                                else validation_engine._current_atol(prepared.spec)
                            ),
                        )
                        record.update(
                            {
                                "input_digest": fine_job.input_digest,
                                "runtime_digest": fine_job.runtime_digest,
                                "compiler_version": fine_job.compiler_version,
                                "simulator_version": fine_result.simulator_version,
                                "execution_state": fine_native.status,
                                "elapsed_seconds": time.monotonic() - started,
                                "selected_input_digest": job.input_digest,
                                "selected_mesh_level": level - 1,
                            }
                        )
                    except ExecutionCancelled:
                        raise
                    except Exception as exc:
                        record = {
                            **record,
                            "status": "failed",
                            "reason": f"Mesh verification did not complete ({type(exc).__name__}).",
                        }
                        break
                    elapsed += time.monotonic() - started
                    history.append(record)
                    (level_root / "provenance.json").write_text(json.dumps(record, indent=2))
                    if record["status"] == "passed" or fine_result.status != "completed":
                        break
                    if level == limit < _MAX_MESH_LEVELS and _clearly_converging(history):
                        limit += 1
                    if level < limit and all(
                        p.state == "converged" for p in fine_result.operating_points
                    ):
                        coarse_spec, result, native, job = (
                            fine_spec,
                            fine_result,
                            fine_native,
                            fine_job,
                        )
                    else:
                        break
                record = {**record, "comparisons": history}
                (mesh_root / "experiment.json").write_text(coarse_spec.model_dump_json(indent=2))
                (mesh_root / "provenance.json").write_text(json.dumps(record, indent=2))
                result = result.model_copy(
                    update={
                        "metadata": {
                            **result.metadata,
                            "mesh_verification": record,
                            "resolved_mesh_spec": coarse_spec.model_dump(mode="json"),
                        }
                    }
                )
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
            raise_if_cancelled()
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
                    mesh_verification_root=mesh_root,
                    recovery_comparison=RecoveryProposalService().record_comparison(
                        prepared.recovery_proposal,
                        reviewed_spec=prepared.spec,
                        new_bundle_id=selected_run_id,
                    )
                    if prepared.recovery_proposal is not None
                    else None,
                )
            )
        except (PlanDigestMismatchError, ExecutionCancelled):
            raise
        except Exception as exc:
            raise ExperimentExecutionError(f"Simulator execution failed: {exc}") from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)
