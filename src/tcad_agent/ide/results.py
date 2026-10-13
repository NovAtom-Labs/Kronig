"""Verified, simulator-neutral result bundles for the repository IDE."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tcad_agent.bundles.models import BundleManifest
from tcad_agent.domain.models import ExperimentSpec, StrictModel
from tcad_agent.ide.paths import canonical_directory, resolve_workspace_path
from tcad_agent.recovery.proposals import RecoveryComparison
from tcad_agent.results.catalog import DatasetCatalogEntry, build_dataset_catalog
from tcad_agent.results.models import CanonicalResult
from tcad_agent.science.models import ScientificCompletenessReport
from tcad_agent.validation.models import ValidationReport


class WorkspaceResultError(ValueError):
    """Raised when a repository result bundle cannot be trusted or rendered."""


class WorkspaceResultView(StrictModel):
    bundle_path: str
    canonical_path: str
    experiment: ExperimentSpec
    result: CanonicalResult
    validation: ValidationReport
    manifest: BundleManifest
    catalog: tuple[DatasetCatalogEntry, ...]
    completeness: ScientificCompletenessReport | None = None
    recovery_comparison: RecoveryComparison | None = None


class WorkspaceResultComparison(StrictModel):
    runs: tuple[WorkspaceResultView, ...]


class WorkspaceResultReader:
    """Read and verify the canonical artifacts behind a workbench view."""

    json_limit = 8 * 1024 * 1024
    required_artifacts = (
        "experiment.json",
        "results/canonical.json",
        "validation/report.json",
    )

    comparison_limit = 8

    def read_many(self, root: Path, canonical_paths: list[str]) -> WorkspaceResultComparison:
        if not 2 <= len(canonical_paths) <= self.comparison_limit:
            raise WorkspaceResultError(
                f"result comparison requires 2 to {self.comparison_limit} paths"
            )
        if len(set(canonical_paths)) != len(canonical_paths):
            raise WorkspaceResultError("result comparison paths must be distinct")
        return WorkspaceResultComparison(
            runs=tuple(self.read(root, path) for path in canonical_paths)
        )

    def read(self, root: Path, canonical_path: str) -> WorkspaceResultView:
        relative = Path(canonical_path)
        if relative.is_absolute() or relative.parts[-2:] != (
            "results",
            "canonical.json",
        ):
            raise WorkspaceResultError("result path must end with results/canonical.json")

        workspace_root = canonical_directory(root)
        canonical_target = resolve_workspace_path(workspace_root, canonical_path)
        bundle_root = canonical_target.parent.parent
        if not bundle_root.is_relative_to(workspace_root):
            raise WorkspaceResultError("result bundle resolves outside the workspace")

        return self._read_verified_bundle(
            bundle_root,
            bundle_path=bundle_root.relative_to(workspace_root).as_posix(),
            canonical_path=canonical_target.relative_to(workspace_root).as_posix(),
        )

    def read_bundle(self, bundle_root: Path) -> WorkspaceResultView:
        """Read an application-managed bundle without projecting internals into a repo."""

        try:
            resolved = bundle_root.expanduser().resolve(strict=True)
        except OSError as exc:
            raise WorkspaceResultError("result bundle is unavailable") from exc
        if bundle_root.is_symlink() or not resolved.is_dir():
            raise WorkspaceResultError("result bundle must be a real directory")
        return self._read_verified_bundle(
            resolved,
            bundle_path=resolved.name,
            canonical_path="results/canonical.json",
        )

    def _read_verified_bundle(
        self,
        bundle_root: Path,
        *,
        bundle_path: str,
        canonical_path: str,
    ) -> WorkspaceResultView:

        manifest_payload = self._read_object(bundle_root / "manifest.json")
        try:
            manifest = BundleManifest.model_validate(manifest_payload)
        except ValidationError as exc:
            raise WorkspaceResultError("result manifest is malformed") from exc
        execution_state = manifest.execution_state or manifest.state
        if execution_state != "completed":
            raise WorkspaceResultError("result execution is not completed")

        artifacts_to_verify = set(self.required_artifacts) | set(manifest.artifacts)
        for artifact in artifacts_to_verify:
            record = manifest.artifacts.get(artifact)
            if record is None:
                raise WorkspaceResultError(f"result manifest does not include {artifact}")
            try:
                target = (bundle_root / artifact).resolve(strict=True)
            except OSError as exc:
                raise WorkspaceResultError(f"result artifact is unavailable: {artifact}") from exc
            if not target.is_relative_to(bundle_root):
                raise WorkspaceResultError("result artifact resolves outside the bundle")
            if target.stat().st_size != record.bytes:
                raise WorkspaceResultError(f"result artifact size mismatch: {artifact}")
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != record.sha256:
                raise WorkspaceResultError(f"result artifact hash mismatch: {artifact}")

        try:
            experiment = ExperimentSpec.model_validate(
                self._read_object(bundle_root / "experiment.json")
            )
            result = CanonicalResult.model_validate(
                self._read_object(bundle_root / "results" / "canonical.json")
            )
            validation = ValidationReport.model_validate(
                self._read_object(bundle_root / "validation" / "report.json")
            )
            completeness = (
                ScientificCompletenessReport.model_validate(
                    self._read_object(bundle_root / "scientific-inputs.json")
                )
                if "scientific-inputs.json" in manifest.artifacts
                else None
            )
            recovery_comparison = (
                RecoveryComparison.model_validate(
                    self._read_object(bundle_root / "recovery-comparison.json")
                )
                if "recovery-comparison.json" in manifest.artifacts
                else None
            )
        except ValidationError as exc:
            raise WorkspaceResultError("result bundle schema is malformed") from exc

        if result.status != "completed":
            raise WorkspaceResultError("canonical result is not completed")
        if result.backend != manifest.backend:
            raise WorkspaceResultError(
                "canonical result backend does not match the manifest backend"
            )
        if result.simulator_version != manifest.simulator_version:
            raise WorkspaceResultError("canonical simulator version does not match the manifest")

        return WorkspaceResultView(
            bundle_path=bundle_path,
            canonical_path=canonical_path,
            experiment=experiment,
            result=result,
            validation=validation,
            manifest=manifest,
            catalog=build_dataset_catalog(result),
            completeness=completeness,
            recovery_comparison=recovery_comparison,
        )

    def _read_object(self, path: Path) -> dict[str, Any]:
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise WorkspaceResultError("required result artifact is unavailable") from exc
        if size > self.json_limit:
            raise WorkspaceResultError("result JSON exceeds the supported size")
        try:
            payload = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceResultError("result artifact is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise WorkspaceResultError("result artifact must contain a JSON object")
        return payload
