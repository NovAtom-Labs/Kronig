"""Projection of immutable runtime evidence into researcher-facing projects."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from tcad_agent.domain.models import StrictModel
from tcad_agent.experiments.artifacts import ExperimentPlanArtifactWriter
from tcad_agent.experiments.models import PreparedExperiment


class ExperimentProjectRecord(StrictModel):
    schema_version: str = "1.0"
    run_id: str
    project_root: Path
    plan_path: Path
    spec_path: Path
    report_path: Path
    result_path: Path
    validation_path: Path
    traceability_path: Path


class ExperimentProjector:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def project(
        self,
        *,
        prepared: PreparedExperiment,
        run_id: str,
        bundle_root: Path,
    ) -> ExperimentProjectRecord:
        plan = ExperimentPlanArtifactWriter(self.workspace).write(prepared)
        bundle = bundle_root.resolve()
        if bundle_root.is_symlink() or not bundle.is_dir():
            raise ValueError("runtime bundle must be a real directory")
        required = {
            "report": bundle / "report.md",
            "result": bundle / "results" / "canonical.json",
            "validation": bundle / "validation" / "report.json",
            "traceability": bundle / "traceability.json",
        }
        missing = [name for name, path in required.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "runtime bundle is missing: " + ", ".join(sorted(missing))
            )
        spec_path = plan.project_root / "experiment.json"
        report_path = plan.project_root / "REPORT.md"
        result_path = plan.project_root / "results.json"
        validation_path = plan.project_root / "validation.json"
        traceability_path = plan.project_root / "traceability.json"
        self._atomic_text(
            spec_path,
            prepared.spec.model_dump_json(indent=2).rstrip() + "\n",
        )
        self._atomic_copy(required["report"], report_path)
        self._atomic_copy(required["result"], result_path)
        self._atomic_copy(required["validation"], validation_path)
        self._atomic_copy(required["traceability"], traceability_path)
        self._atomic_text(
            plan.project_root / "project.json",
            json.dumps(
                {
                    "schema_version": "1.0",
                    "run_id": run_id,
                    "plan_digest": prepared.plan_digest,
                    "runtime_bundle_managed_by_application": True,
                    "artifacts": {
                        "plan": "PLAN.md",
                        "spec": "experiment.json",
                        "report": "REPORT.md",
                        "results": "results.json",
                        "validation": "validation.json",
                        "traceability": "traceability.json",
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        return ExperimentProjectRecord(
            run_id=run_id,
            project_root=plan.project_root,
            plan_path=plan.markdown_path,
            spec_path=spec_path,
            report_path=report_path,
            result_path=result_path,
            validation_path=validation_path,
            traceability_path=traceability_path,
        )

    @staticmethod
    def _atomic_text(destination: Path, content: str) -> None:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            path = Path(temporary)
            if path.exists():
                path.unlink()

    @classmethod
    def _atomic_copy(cls, source: Path, destination: Path) -> None:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        os.close(descriptor)
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            path = Path(temporary)
            if path.exists():
                path.unlink()
