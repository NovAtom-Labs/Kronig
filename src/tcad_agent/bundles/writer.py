"""Atomic, hash-addressed experiment bundle writer."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Literal

from tcad_agent.bundles.models import (
    ArtifactRecord,
    BundleInputs,
    BundleManifest,
    ExperimentBundle,
    require_run_id,
)
from tcad_agent.reporting.artifacts import FieldArtifactWriter
from tcad_agent.reporting.markdown import MarkdownReport
from tcad_agent.reporting.traceability import build_traceability
from tcad_agent.runners.process import raise_if_cancelled


class BundleWriter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, inputs: BundleInputs) -> ExperimentBundle:
        require_run_id(inputs.run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        final = self.root / inputs.run_id
        staging = self.root / f".{inputs.run_id}.staging"
        if final.exists() or staging.exists():
            raise FileExistsError(f"bundle run ID already exists: {inputs.run_id}")
        try:
            for directory in ("compiled", "logs", "native", "results", "validation"):
                (staging / directory).mkdir(parents=True, exist_ok=False)
            self._write_json(staging / "experiment.json", inputs.spec.model_dump_json(indent=2))
            if inputs.completeness is not None:
                self._write_json(
                    staging / "scientific-inputs.json",
                    inputs.completeness.model_dump_json(indent=2),
                )
            if inputs.recovery_comparison is not None:
                self._write_json(
                    staging / "recovery-comparison.json",
                    inputs.recovery_comparison.model_dump_json(indent=2),
                )
            if inputs.mesh_verification_root is not None:
                shutil.copytree(inputs.mesh_verification_root, staging / "verification" / "mesh")
            for source in inputs.job.input_files:
                shutil.copy2(source, staging / "compiled" / source.name)
            shutil.copy2(inputs.native.stdout_path, staging / "logs" / "stdout.log")
            shutil.copy2(inputs.native.stderr_path, staging / "logs" / "stderr.log")
            if inputs.native.result_path is not None and inputs.native.result_path.exists():
                shutil.copy2(inputs.native.result_path, staging / "native" / "native_result.json")
            self._write_json(
                staging / "results" / "canonical.json",
                inputs.result.model_dump_json(indent=2),
            )
            FieldArtifactWriter().write(inputs.result, staging / "results")
            self._write_json(
                staging / "validation" / "report.json",
                inputs.validation.model_dump_json(indent=2),
            )
            if not inputs.events_path.is_file():
                raise FileNotFoundError(f"event ledger does not exist: {inputs.events_path}")
            shutil.copy2(inputs.events_path, staging / "events.jsonl")
            traceability = build_traceability(inputs.spec, inputs.result)
            self._write_json(staging / "traceability.json", traceability.model_dump_json(indent=2))
            report = MarkdownReport().render(
                inputs.spec,
                inputs.result,
                inputs.validation,
                traceability=traceability,
            )
            (staging / "report.md").write_text(report)
            state: Literal["failed", "completed"] = (
                "completed"
                if inputs.native.status == "completed"
                and inputs.result.status == "completed"
                and inputs.validation.overall == "passed"
                else "failed"
            )
            execution_state: Literal["failed", "completed"] = (
                "completed"
                if inputs.native.status == "completed" and inputs.result.status == "completed"
                else "failed"
            )
            validation_state: Literal["passed", "needs_review"] = (
                "passed" if inputs.validation.overall == "passed" else "needs_review"
            )
            artifacts = self._hash_artifacts(staging)
            manifest = BundleManifest(
                run_id=inputs.run_id,
                state=state,
                execution_state=execution_state,
                validation_state=validation_state,
                backend=inputs.result.backend,
                simulator_version=inputs.result.simulator_version,
                compiler_version=inputs.job.compiler_version,
                input_digest=inputs.job.input_digest,
                runtime_digest=inputs.job.runtime_digest,
                artifacts=artifacts,
            )
            self._write_json(staging / "manifest.json", manifest.model_dump_json(indent=2))
            raise_if_cancelled()
            staging.replace(final)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return ExperimentBundle(
            run_id=inputs.run_id,
            state=state,
            execution_state=execution_state,
            validation_state=validation_state,
            root=final,
        )

    @staticmethod
    def _write_json(path: Path, content: str) -> None:
        path.write_text(content.rstrip() + "\n")

    @staticmethod
    def _hash_artifacts(root: Path) -> dict[str, ArtifactRecord]:
        artifacts: dict[str, ArtifactRecord] = {}
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
            artifacts[relative] = ArtifactRecord(
                sha256=hashlib.sha256(data).hexdigest(),
                bytes=len(data),
            )
        return artifacts
