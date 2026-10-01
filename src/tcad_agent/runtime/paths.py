"""Cross-platform separation of selected projects from runtime internals."""

from __future__ import annotations

import hashlib
import os
import platform
from dataclasses import dataclass
from pathlib import Path


def default_application_data_root() -> Path:
    configured = os.getenv("AGENT_KRONIG_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return (home / "Library" / "Application Support" / "Agent Kronig").resolve()
    if system == "Windows":
        return Path(
            os.getenv("APPDATA", str(home / "AppData" / "Roaming"))
        ).resolve() / "Agent Kronig"
    linux_data = Path(
        os.getenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    ).resolve()
    return linux_data / "Agent Kronig"


@dataclass(frozen=True)
class RuntimePaths:
    data_root: Path
    workspace: Path
    workspace_key: str
    workspace_runtime_root: Path
    bundle_root: Path

    @classmethod
    def from_workspace(cls, workspace: Path) -> RuntimePaths:
        return cls.from_roots(
            data_root=default_application_data_root(),
            workspace=workspace,
        )

    @classmethod
    def from_roots(cls, *, data_root: Path, workspace: Path) -> RuntimePaths:
        resolved_data = data_root.expanduser().resolve()
        resolved_workspace = workspace.expanduser().resolve()
        key = hashlib.sha256(str(resolved_workspace).encode("utf-8")).hexdigest()[:24]
        runtime_root = resolved_data / "runtime" / "workspaces" / key
        return cls(
            data_root=resolved_data,
            workspace=resolved_workspace,
            workspace_key=key,
            workspace_runtime_root=runtime_root,
            bundle_root=runtime_root / "bundles",
        )
