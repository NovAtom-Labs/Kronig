"""Validated configuration for the private desktop backend."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


def default_data_dir(
    system: str,
    home: Path,
    environment: Mapping[str, str],
) -> Path:
    """Return the platform-standard mutable application data directory."""

    if system == "Linux":
        root = Path(environment.get("XDG_DATA_HOME", home / ".local" / "share"))
        return root / "Agent Kronig"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "Agent Kronig"
    if system == "Windows":
        root = Path(environment.get("APPDATA", home / "AppData" / "Roaming"))
        return root / "Agent Kronig"
    raise ValueError(f"unsupported desktop operating system: {system}")


@dataclass(frozen=True)
class DesktopLaunchConfig:
    """Complete immutable contract passed from Electron to the backend."""

    host: str
    port: int
    launch_token: str
    data_dir: Path
    protocol_version: int = 1
    devsim_runner: Path | None = None
    owner_pipe: bool = False

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> DesktopLaunchConfig:
        values = os.environ if environment is None else environment
        token = values.get("AGENT_KRONIG_DESKTOP_TOKEN", "")
        if not token:
            raise ValueError("desktop launch token is required")
        if len(token.encode("utf-8")) < 32:
            raise ValueError("desktop launch token must contain at least 32 bytes")

        host = values.get("AGENT_KRONIG_DESKTOP_HOST", "127.0.0.1")
        if host != "127.0.0.1":
            raise ValueError("desktop backend host must be 127.0.0.1")

        try:
            port = int(values.get("AGENT_KRONIG_DESKTOP_PORT", "0"))
        except ValueError as exc:
            raise ValueError("desktop backend port must be an integer") from exc
        if not 0 <= port <= 65535:
            raise ValueError("desktop backend port must be between 0 and 65535")

        configured_data = values.get("AGENT_KRONIG_DATA_DIR")
        data_dir = (
            Path(configured_data).expanduser()
            if configured_data
            else default_data_dir(platform.system(), Path.home(), values)
        )
        configured_runner = values.get("AGENT_KRONIG_DEVSIM_RUNNER")
        owner_pipe = values.get("AGENT_KRONIG_DESKTOP_OWNER_PIPE", "0")
        if owner_pipe not in {"0", "1"}:
            raise ValueError("desktop owner pipe must be 0 or 1")
        return cls(
            host=host,
            port=port,
            launch_token=token,
            data_dir=data_dir.resolve(),
            owner_pipe=owner_pipe == "1",
            devsim_runner=(
                Path(configured_runner).expanduser().resolve()
                if configured_runner
                else None
            ),
        )
