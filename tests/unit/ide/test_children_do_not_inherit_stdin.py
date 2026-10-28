"""The desktop backend holds a blocking read on its stdin pipe; children must not inherit it.

A child that touches the inherited pipe handle can block on it for good. This froze the folder
picker in the desktop app: opening a folder ran ``git rev-parse`` and it never returned.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tcad_agent.ide import changes, repository
from tcad_agent.prompting import context


def _spy(monkeypatch, module):
    seen: list[dict] = []

    def fake_run(command, **kwargs):
        seen.append(kwargs)
        return subprocess.CompletedProcess(command, 128, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    return seen


def test_repository_git_snapshot_gives_git_no_stdin(monkeypatch, tmp_path: Path) -> None:
    seen = _spy(monkeypatch, repository)
    repository.RepositoryInspector._git_snapshot(tmp_path)
    assert seen and all(call.get("stdin") is subprocess.DEVNULL for call in seen)


def test_change_tracker_git_identity_gives_git_no_stdin(monkeypatch, tmp_path: Path) -> None:
    seen = _spy(monkeypatch, changes)
    changes.WorkspaceChangeTracker._git_identity(tmp_path)
    assert seen and all(call.get("stdin") is subprocess.DEVNULL for call in seen)


def test_prompt_context_git_state_gives_git_no_stdin(monkeypatch, tmp_path: Path) -> None:
    seen = _spy(monkeypatch, context)
    context.WorkspaceContextCollector._git_state(tmp_path)
    assert seen and all(call.get("stdin") is subprocess.DEVNULL for call in seen)
