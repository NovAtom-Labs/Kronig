"""Bounded workspace and local-knowledge context collection."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from tcad_agent.knowledge.models import SearchHit
from tcad_agent.prompting.models import (
    EvidenceExcerpt,
    WorkspaceContext,
    WorkspaceFileContext,
)
from tcad_agent.security.paths import is_credential_path


class SearchableKnowledgeIndex(Protocol):
    def search(
        self, query: str, filters: dict[str, str] | None = None, limit: int = 5
    ) -> tuple[SearchHit, ...]: ...


class WorkspaceContextCollector:
    """Collect identity-level repository context without reading file contents."""

    _excluded_directories = frozenset(
        {
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".tcad-agent",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "node_modules",
        }
    )

    def __init__(self, *, max_files: int = 500, hash_limit: int = 1_048_576) -> None:
        if max_files <= 0 or hash_limit <= 0:
            raise ValueError("workspace context limits must be positive")
        self.max_files = max_files
        self.hash_limit = hash_limit

    def collect(self, root: Path) -> WorkspaceContext:
        canonical = root.resolve(strict=True)
        candidates: list[Path] = []
        for directory, names, files in os.walk(canonical, followlinks=False):
            current = Path(directory)
            names[:] = sorted(
                name
                for name in names
                if name not in self._excluded_directories
                and not (current / name).is_symlink()
            )
            for name in sorted(files):
                path = current / name
                relative = path.relative_to(canonical)
                if (
                    path.is_symlink()
                    or is_credential_path(relative)
                    or any(part in self._excluded_directories for part in relative.parts)
                    or name.casefold().endswith((".key", ".pem", ".p12", ".pfx"))
                ):
                    continue
                candidates.append(path)

        ordered = sorted(candidates, key=lambda item: item.relative_to(canonical).as_posix())
        truncated = len(ordered) > self.max_files
        selected = ordered[: self.max_files]
        file_contexts = tuple(self._file_context(canonical, path) for path in selected)
        inventory_json = json.dumps(
            [item.model_dump(mode="json") for item in file_contexts],
            sort_keys=True,
            separators=(",", ":"),
        )
        available, branch, dirty = self._git_state(canonical)
        return WorkspaceContext(
            display_name=canonical.name,
            git_available=available,
            git_branch=branch,
            git_dirty=dirty,
            files=file_contexts,
            inventory_hash=hashlib.sha256(inventory_json.encode()).hexdigest(),
            inventory_truncated=truncated,
        )

    def _file_context(self, root: Path, path: Path) -> WorkspaceFileContext:
        size = path.stat().st_size
        digest: str | None = None
        if size <= self.hash_limit:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return WorkspaceFileContext(
            path=path.relative_to(root).as_posix(), size=size, sha256=digest
        )

    @staticmethod
    def _git_state(root: Path) -> tuple[bool, str | None, bool]:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain=v1", "--branch"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return False, None, False
        if result.returncode != 0:
            return False, None, False
        lines = result.stdout.splitlines()
        branch = None
        if lines and lines[0].startswith("## "):
            branch = lines[0][3:].split("...", 1)[0].strip()
        return True, branch or None, len(lines) > 1


class LocalEvidenceCollector:
    """Retrieve a small, deduplicated, local-first evidence packet."""

    def __init__(
        self,
        index: SearchableKnowledgeIndex,
        *,
        max_searches: int = 2,
        max_passages: int = 6,
        max_characters: int = 8_000,
    ) -> None:
        if min(max_searches, max_passages, max_characters) <= 0:
            raise ValueError("evidence budgets must be positive")
        self.index = index
        self.max_searches = max_searches
        self.max_passages = max_passages
        self.max_characters = max_characters

    def collect(
        self, original_prompt: str, answer_texts: Sequence[str]
    ) -> tuple[EvidenceExcerpt, ...]:
        queries = [original_prompt.strip()]
        if answer_texts:
            queries.append(" ".join(text.strip() for text in answer_texts if text.strip()))
        unique: dict[str, SearchHit] = {}
        for query in tuple(query for query in queries if query)[: self.max_searches]:
            for hit in self.index.search(query, limit=self.max_passages):
                unique.setdefault(hit.id, hit)

        remaining = self.max_characters
        excerpts: list[EvidenceExcerpt] = []
        for hit in unique.values():
            if len(excerpts) >= self.max_passages or remaining <= 0:
                break
            slots = self.max_passages - len(excerpts)
            fair_share = max(1, remaining // slots)
            content = hit.content[: min(2_000, fair_share, remaining)].strip()
            if not content:
                continue
            excerpts.append(
                EvidenceExcerpt(
                    id=hit.id,
                    title=hit.citation.title,
                    url=hit.citation.url,
                    version=hit.citation.version,
                    content_hash=hit.citation.content_hash,
                    reviewed=hit.reviewed,
                    content=content,
                )
            )
            remaining -= len(content)
        return tuple(excerpts)


def capability_hashes(package_root: Path) -> dict[str, str]:
    """Return stable identities for packaged backend capability manifests."""

    manifests = package_root / "adapters"
    hashes: dict[str, str] = {}
    for backend in ("devsim", "sentaurus"):
        path = manifests / backend / "manifest.yaml"
        if path.is_file():
            hashes[backend] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes
