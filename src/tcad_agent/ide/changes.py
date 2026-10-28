"""Bounded, read-only workspace baselines and run change comparison."""

from __future__ import annotations

import difflib
import os
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import ClassVar

from tcad_agent.ide.models import (
    BaselineFile,
    IDEEvent,
    WorkspaceBaseline,
    WorkspaceChange,
    WorkspaceChangeSet,
)
from tcad_agent.security.paths import is_credential_path


class WorkspaceChangeTracker:
    """Capture a bounded workspace state and compare it without mutating Git."""

    _ignored_directories: ClassVar[set[str]] = {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".superpowers",
        ".tcad-agent",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
    def __init__(
        self,
        *,
        file_limit: int = 5_000,
        hash_limit: int = 1024 * 1024,
        content_budget: int = 20 * 1024 * 1024,
        diff_limit: int = 256 * 1024,
    ) -> None:
        self.file_limit = file_limit
        self.hash_limit = hash_limit
        self.content_budget = content_budget
        self.diff_limit = diff_limit

    def capture(self, root: Path) -> WorkspaceBaseline:
        canonical_root = root.resolve(strict=True)
        files: dict[str, BaselineFile] = {}
        content_bytes = 0
        truncated = False
        for target in self._files(canonical_root):
            if len(files) >= self.file_limit:
                truncated = True
                break
            try:
                stat = target.stat()
            except OSError:
                truncated = True
                continue
            relative = target.relative_to(canonical_root).as_posix()
            digest: str | None = None
            content: str | None = None
            if stat.st_size <= self.hash_limit:
                try:
                    raw = target.read_bytes()
                except OSError:
                    truncated = True
                    continue
                digest = sha256(raw).hexdigest()
                if content_bytes + len(raw) <= self.content_budget:
                    try:
                        content = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        content = None
                    else:
                        content_bytes += len(raw)
                else:
                    truncated = True
            files[relative] = BaselineFile(
                path=relative,
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256=digest,
                content=content,
            )
        git_head, git_branch = self._git_identity(canonical_root)
        return WorkspaceBaseline(
            root=canonical_root,
            captured_at=datetime.now(UTC),
            git_head=git_head,
            git_branch=git_branch,
            truncated=truncated,
            files=files,
        )

    def compare(self, root: Path, baseline: WorkspaceBaseline) -> WorkspaceChangeSet:
        canonical_root = root.resolve(strict=True)
        if canonical_root != baseline.root.resolve():
            raise ValueError("workspace baseline belongs to a different root")
        current = self.capture(canonical_root)
        before_paths = set(baseline.files)
        after_paths = set(current.files)
        deleted = before_paths - after_paths
        created = after_paths - before_paths
        changes: list[WorkspaceChange] = []

        comparison_incomplete = baseline.truncated or current.truncated
        if comparison_incomplete:
            # A bounded scan can shift its cutoff when a path is inserted or removed.
            # Common paths remain comparable, but one-sided paths cannot be claimed as
            # exact creates, deletes, or renames.
            created.clear()
            deleted.clear()

        renamed: list[tuple[str, str]] = []
        created_by_hash: dict[str, list[str]] = {}
        for path in sorted(created):
            digest = current.files[path].sha256
            if digest:
                created_by_hash.setdefault(digest, []).append(path)
        for old_path in sorted(deleted):
            digest = baseline.files[old_path].sha256
            candidates = created_by_hash.get(digest or "", [])
            if digest and candidates:
                new_path = candidates.pop(0)
                renamed.append((old_path, new_path))
                created.remove(new_path)
                deleted.remove(old_path)

        for old_path, new_path in renamed:
            before = baseline.files[old_path]
            after = current.files[new_path]
            changes.append(
                WorkspaceChange(
                    path=new_path,
                    previous_path=old_path,
                    operation="renamed",
                    before_sha256=before.sha256,
                    after_sha256=after.sha256,
                )
            )
        for path in sorted(created):
            changes.append(self._change(path, "created", None, current.files[path]))
        for path in sorted(deleted):
            changes.append(self._change(path, "deleted", baseline.files[path], None))
        for path in sorted(before_paths & after_paths):
            before = baseline.files[path]
            after = current.files[path]
            if self._same(before, after):
                continue
            changes.append(self._change(path, "modified", before, after))

        return WorkspaceChangeSet(
            baseline_captured_at=baseline.captured_at,
            generated_at=datetime.now(UTC),
            baseline_truncated=comparison_incomplete,
            files=tuple(sorted(changes, key=lambda row: row.path)),
        )

    def _change(
        self,
        path: str,
        operation: str,
        before: BaselineFile | None,
        after: BaselineFile | None,
    ) -> WorkspaceChange:
        before_content = before.content if before is not None else ""
        after_content = after.content if after is not None else ""
        uncertain = any(
            item is not None and item.sha256 is None for item in (before, after)
        )
        diff: str | None = None
        additions: int | None = None
        deletions: int | None = None
        diff_truncated = False
        if not uncertain and before_content is not None and after_content is not None:
            diff_lines = list(
                difflib.unified_diff(
                    before_content.splitlines(keepends=True),
                    after_content.splitlines(keepends=True),
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
            additions = sum(
                1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
            )
            deletions = sum(
                1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
            )
            rendered = "".join(diff_lines)
            encoded = rendered.encode("utf-8")
            if len(encoded) > self.diff_limit:
                rendered = encoded[: self.diff_limit].decode("utf-8", errors="ignore")
                diff_truncated = True
            diff = rendered or None
        return WorkspaceChange(
            path=path,
            operation=operation,  # type: ignore[arg-type]
            before_sha256=before.sha256 if before is not None else None,
            after_sha256=after.sha256 if after is not None else None,
            additions=additions,
            deletions=deletions,
            diff=diff,
            diff_truncated=diff_truncated,
            uncertain=uncertain,
        )

    @staticmethod
    def _same(before: BaselineFile, after: BaselineFile) -> bool:
        if before.sha256 is not None and after.sha256 is not None:
            return before.sha256 == after.sha256
        return before.size == after.size and before.mtime_ns == after.mtime_ns

    def _files(self, root: Path):  # type: ignore[no-untyped-def]
        for current_root, directory_names, file_names in os.walk(root):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in self._ignored_directories
                and not is_credential_path(Path(current_root).relative_to(root) / name)
                and not (Path(current_root) / name).is_symlink()
            )
            for name in sorted(file_names):
                lowered = name.casefold()
                target = Path(current_root) / name
                if (
                    is_credential_path(target.relative_to(root))
                    or lowered.endswith((".key", ".pem"))
                ):
                    continue
                if not target.is_symlink() and target.is_file():
                    yield target

    @staticmethod
    def _git_identity(root: Path) -> tuple[str | None, str | None]:
        def run(*arguments: str) -> str | None:
            try:
                completed = subprocess.run(
                    ["git", *arguments],
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            return completed.stdout.strip() if completed.returncode == 0 else None

        return run("rev-parse", "HEAD"), run("branch", "--show-current")


def attribute_changes(
    change_set: WorkspaceChangeSet,
    events: tuple[IDEEvent, ...],
    *,
    root: Path | None = None,
) -> WorkspaceChangeSet:
    """Attach only explicit, successful action identities to changed paths."""

    starts: dict[str, IDEEvent] = {}
    completions: dict[str, IDEEvent] = {}
    successful: set[str] = set()
    for event in events:
        action_id = event.payload.get("action_id")
        if not isinstance(action_id, str):
            continue
        if event.kind == "tool_call_started":
            starts[action_id] = event
        elif event.kind == "tool_call_completed" and not event.payload.get("is_error"):
            successful.add(action_id)
            completions[action_id] = event

    def relative_path(value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        candidate = Path(value)
        if candidate.is_absolute():
            if root is None:
                return None
            try:
                candidate = candidate.resolve(strict=False).relative_to(root.resolve())
            except ValueError:
                return None
        return candidate.as_posix().removeprefix("./")

    mutations: dict[str, list[tuple[str, str, str | None]]] = {}
    validations: dict[str, list[tuple[str, str]]] = {}
    artifact_paths: set[str] = set()
    for action_id, event in starts.items():
        if action_id not in successful:
            continue
        payload = event.payload
        completion_payload = completions.get(action_id)
        outcome = completion_payload.payload if completion_payload is not None else {}
        arguments = payload.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        tool_name = payload.get("tool_name")
        tool_name = tool_name if isinstance(tool_name, str) else "tool"
        subagent = outcome.get("subagent") or payload.get("subagent")
        subagent = subagent if isinstance(subagent, str) else None
        command = arguments.get("command")
        path = relative_path(arguments.get("path"))
        if tool_name == "file_editor" and command != "view" and path:
            mutations.setdefault(path, []).append((action_id, tool_name, subagent))
        affected_paths = outcome.get("affected_paths")
        if isinstance(affected_paths, list):
            for affected in affected_paths:
                if normalized := relative_path(affected):
                    mutations.setdefault(normalized, []).append(
                        (action_id, tool_name, subagent)
                    )
        validated_files = outcome.get("validated_files")
        if payload.get("evidence_kind") == "validation" and isinstance(
            validated_files, dict
        ):
            for target, digest in validated_files.items():
                if (normalized := relative_path(target)) and isinstance(digest, str):
                    validations.setdefault(normalized, []).append(
                        (action_id, digest)
                    )
        artifacts = outcome.get("artifact_paths") or payload.get("artifact_paths")
        if isinstance(artifacts, list):
            artifact_paths.update(
                normalized
                for item in artifacts
                if (normalized := relative_path(item)) is not None
            )

    attributed: list[WorkspaceChange] = []
    for change in change_set.files:
        actions = list(dict.fromkeys(mutations.get(change.path, [])))
        attributed.append(
            change.model_copy(
                update={
                    "attributed_action_ids": tuple(item[0] for item in actions),
                    "attributed_tools": tuple(dict.fromkeys(item[1] for item in actions)),
                    "attributed_subagents": tuple(
                        dict.fromkeys(item[2] for item in actions if item[2])
                    ),
                    "validation_action_ids": tuple(
                        dict.fromkeys(
                            action_id
                            for action_id, digest in validations.get(change.path, [])
                            if change.after_sha256 is not None
                            and digest == change.after_sha256
                        )
                    ),
                    "artifact": change.path in artifact_paths,
                }
            )
        )
    return change_set.model_copy(update={"files": tuple(attributed)})
