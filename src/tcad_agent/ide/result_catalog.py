"""Workspace-scoped scientific evidence, independent of conversation storage."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tcad_agent.domain.models import StrictModel
from tcad_agent.ide.results import WorkspaceResultError, WorkspaceResultReader, WorkspaceResultView
from tcad_agent.runtime.paths import RuntimePaths
from tcad_agent.validation.assessment import assess_result


class SavedResultEntry(StrictModel):
    bundle_run_id: str
    name: str
    project_path: str | None = None
    execution_state: str
    validation_state: str
    failed_check_count: int
    output_state: str
    reason: str
    modified_at: float


class SavedResultListing(StrictModel):
    entries: tuple[SavedResultEntry, ...]
    rejected_count: int = 0
    truncated: bool = False


class SavedResultCatalog:
    """Re-discover immutable managed bundles, never resurrect chat or agent runs."""

    limit = 500

    def __init__(self, reader: WorkspaceResultReader | None = None) -> None:
        self.reader = reader or WorkspaceResultReader()

    @staticmethod
    def _root(workspace: Path) -> Path:
        paths = RuntimePaths.from_workspace(workspace)
        root = paths.bundle_root
        # Every parent below the application data root is application owned.
        # Reject a substituted workspace/runtime directory as well as bundle links.
        current = root
        while current != paths.data_root:
            if current.is_symlink():
                raise WorkspaceResultError("managed result directory cannot be a symlink")
            current = current.parent
        if root.exists() and not root.is_dir():
            raise WorkspaceResultError("managed result directory is unavailable")
        return root

    def read(self, workspace: Path, bundle_run_id: str) -> WorkspaceResultView:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", bundle_run_id):
            raise WorkspaceResultError("invalid saved result identity")
        view = self.reader.read_bundle(self._root(workspace) / bundle_run_id)
        if view.manifest.run_id != bundle_run_id:
            raise WorkspaceResultError("saved result identity does not match the manifest")
        return view

    def list(self, workspace: Path) -> SavedResultListing:
        root = self._root(workspace)
        if not root.exists():
            return SavedResultListing(entries=())
        projects = self._projects(workspace)
        entries = []
        rejected = 0
        candidates = sorted(
            (path for path in root.iterdir() if path.name != ".work"),
            key=lambda path: path.name,
        )
        for candidate in candidates[: self.limit]:
            try:
                view = self.read(workspace, candidate.name)
                failed = sum(check.status == "failed" for check in view.validation.checks)
                assessment = assess_result(
                    view.result, spec=view.experiment, validation=view.validation
                )
                failures = [
                    check.message for check in view.validation.checks if check.status == "failed"
                ]
                reason = (
                    failures[0]
                    if failures
                    else assessment.output_coverage.message
                    if assessment.output_coverage.status != "passed"
                    else assessment.numerical.message
                )
                entries.append(
                    SavedResultEntry(
                        bundle_run_id=view.manifest.run_id,
                        name=view.experiment.name,
                        project_path=projects.get(view.manifest.run_id),
                        execution_state=view.manifest.execution_state or view.result.status,
                        validation_state=assessment.numerical.status,
                        failed_check_count=failed,
                        output_state=assessment.output_coverage.status,
                        reason=reason,
                        modified_at=(candidate / "manifest.json").stat().st_mtime,
                    )
                )
            except (WorkspaceResultError, OSError, ValueError):
                rejected += 1
        return SavedResultListing(
            entries=tuple(sorted(entries, key=lambda item: item.modified_at, reverse=True)),
            rejected_count=rejected,
            truncated=len(candidates) > self.limit,
        )

    @staticmethod
    def _projects(workspace: Path) -> dict[str, str]:
        root = workspace.resolve()
        projects = root / "experiments"
        if projects.is_symlink() or not projects.is_dir():
            return {}
        found = {}
        for project in sorted(projects.iterdir())[:500]:
            metadata = project / "project.json"
            if project.is_symlink() or metadata.is_symlink():
                continue
            try:
                if metadata.stat().st_size > 65536:
                    continue
                payload = json.loads(metadata.read_text())
                if isinstance(payload, dict) and isinstance(payload.get("run_id"), str):
                    found[payload["run_id"]] = project.relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
        return found
