#!/usr/bin/env python3
"""Launch the source desktop application consistently on every supported OS."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values


class DevelopmentLaunchError(RuntimeError):
    """Raised when the native development application cannot start."""


@dataclass(frozen=True, repr=False)
class DesktopLaunch:
    command: Path
    arguments: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]


def _electron_path(repository: Path, system: str) -> Path:
    distribution = repository / "desktop" / "node_modules" / "electron" / "dist"
    if system == "Windows":
        return distribution / "electron.exe"
    if system == "Linux":
        return distribution / "electron"
    if system == "Darwin":
        return distribution / "Electron.app" / "Contents" / "MacOS" / "Electron"
    raise DevelopmentLaunchError("Development launch supports Windows, macOS, and Linux.")


def resolve_launch(
    repository: Path,
    system: str,
    base_environment: Mapping[str, str],
) -> DesktopLaunch:
    """Resolve one secret-safe native launch without starting a process."""

    repository = repository.resolve()
    environment = dict(base_environment)
    dotenv_path = repository / ".env"
    if dotenv_path.is_file():
        for name, value in dotenv_values(dotenv_path).items():
            if value is not None:
                environment[name] = value
    # The backend's working directory is not necessarily the source root.
    # Do not depend on a machine-specific .env to find the isolated simulator.
    if not environment.get("TCAD_DEVSIM_PYTHON"):
        parts = ("Scripts", "python.exe") if system == "Windows" else ("bin", "python")
        environment["TCAD_DEVSIM_PYTHON"] = str(
            repository.parent.joinpath("devsim", ".venv", *parts)
        )
    if system == "Windows" and not environment.get("DEVSIM_MATH_LIBS"):
        prefix = Path(environment["TCAD_DEVSIM_PYTHON"]).parent.parent
        runtime_directory = prefix / "Library" / "bin"
        candidates = [
            runtime_directory / "mkl_rt.dll",
            *sorted(runtime_directory.glob("mkl_rt.*.dll")),
        ]
        runtime = next((item for item in candidates if item.is_file()), None)
        if runtime is not None:
            environment["DEVSIM_MATH_LIBS"] = str(runtime)
            environment["PATH"] = str(runtime_directory) + ";" + environment.get("PATH", "")
    environment.pop("ELECTRON_RUN_AS_NODE", None)
    environment.setdefault("TCAD_WORKSPACE", str(repository / ".tcad-agent-desktop"))
    environment["OPENHANDS_SUPPRESS_BANNER"] = "1"
    return DesktopLaunch(
        command=_electron_path(repository, system),
        arguments=(".",),
        cwd=repository / "desktop",
        environment=environment,
    )


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        raise DevelopmentLaunchError("The development launcher does not accept arguments.")
    repository = Path(__file__).resolve().parents[1]
    try:
        launch = resolve_launch(repository, platform.system(), os.environ)
        if not launch.command.is_file():
            raise DevelopmentLaunchError(
                "Desktop dependencies are missing. Run: "
                f"{sys.executable} {repository / 'scripts/bootstrap_dev.py'}"
            )
        completed = subprocess.run(
            (str(launch.command), *launch.arguments),
            cwd=launch.cwd,
            env=launch.environment,
            check=False,
        )
        return completed.returncode
    except (DevelopmentLaunchError, OSError) as error:
        print(f"Agent Kronig could not start: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
