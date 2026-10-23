from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load_launcher() -> ModuleType:
    path = ROOT / "scripts" / "run_desktop_dev.py"
    if not path.is_file():
        pytest.fail(f"missing shared desktop launcher: {path}")
    spec = importlib.util.spec_from_file_location("agent_kronig_dev_launcher", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_launcher_uses_windows_electron_and_isolates_development_data(
    tmp_path: Path,
) -> None:
    launcher = load_launcher()
    repository = tmp_path / "agent-kronig"
    repository.mkdir()
    (repository / ".env").write_text(
        "AWS_REGION_NAME=ap-south-1\nAWS_BEARER_TOKEN_BEDROCK=local-secret\n"
    )

    launch = launcher.resolve_launch(
        repository,
        "Windows",
        {"PATH": "base-path", "AWS_REGION_NAME": "old-region"},
    )

    assert launch.command == repository / "desktop/node_modules/electron/dist/electron.exe"
    assert launch.arguments == (".",)
    assert launch.cwd == repository / "desktop"
    assert launch.environment["AWS_REGION_NAME"] == "ap-south-1"
    assert launch.environment["AWS_BEARER_TOKEN_BEDROCK"] == "local-secret"
    assert launch.environment["TCAD_WORKSPACE"] == str(repository / ".tcad-agent-desktop")
    assert launch.environment["OPENHANDS_SUPPRESS_BANNER"] == "1"
    assert "local-secret" not in repr(launch)


def test_launcher_preserves_explicit_workspace_and_rejects_unsupported_system(
    tmp_path: Path,
) -> None:
    launcher = load_launcher()
    repository = tmp_path / "agent-kronig"
    repository.mkdir()

    launch = launcher.resolve_launch(
        repository,
        "Linux",
        {"TCAD_WORKSPACE": "/approved/workspace"},
    )

    assert launch.environment["TCAD_WORKSPACE"] == "/approved/workspace"
    with pytest.raises(launcher.DevelopmentLaunchError, match="Windows, macOS, and Linux"):
        launcher.resolve_launch(repository, "FreeBSD", {})


@pytest.mark.parametrize(
    "system,parts",
    [
        ("Linux", ("bin", "python")),
        ("Darwin", ("bin", "python")),
        ("Windows", ("Scripts", "python.exe")),
    ],
)
def test_clean_launcher_selects_the_isolated_simulator(tmp_path, system, parts):
    launcher = load_launcher()
    repository = tmp_path / "checkout with spaces"
    repository.mkdir()
    (repository / ".env").write_text("TCAD_DEVSIM_PYTHON=\n")
    launch = launcher.resolve_launch(repository, system, {"ELECTRON_RUN_AS_NODE": "1"})
    assert launch.environment["TCAD_DEVSIM_PYTHON"] == str(
        tmp_path.joinpath("devsim", ".venv", *parts)
    )
    assert "ELECTRON_RUN_AS_NODE" not in launch.environment


def test_launcher_retains_explicit_simulator_override(tmp_path):
    launcher = load_launcher()
    launch = launcher.resolve_launch(
        tmp_path, "Linux", {"TCAD_DEVSIM_PYTHON": "/approved/simulator/bin/python"}
    )
    assert launch.environment["TCAD_DEVSIM_PYTHON"] == "/approved/simulator/bin/python"


def test_windows_launcher_resolves_local_mkl_without_bundling_an_installer(tmp_path):
    launcher = load_launcher()
    repository = tmp_path / "checkout"
    runtime = tmp_path / "devsim/.venv/Library/bin/mkl_rt.2.dll"
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    launch = launcher.resolve_launch(repository, "Windows", {"PATH": "existing"})
    assert launch.environment["DEVSIM_MATH_LIBS"] == str(runtime)
    assert str(runtime.parent) in launch.environment["PATH"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shortcut; Windows uses PowerShell")
def test_tracked_shortcut_launches_from_another_directory_without_local_env(tmp_path):
    repository = tmp_path / "checkout with spaces"
    (repository / "scripts").mkdir(parents=True)
    (repository / ".venv/bin").mkdir(parents=True)
    shortcut = repository / "Launch Agent Kronig Dev.command"
    shutil.copy2(ROOT / shortcut.name, shortcut)
    for name in ("run_desktop_dev.sh", "run_desktop_dev.py"):
        shutil.copy2(ROOT / "scripts" / name, repository / "scripts" / name)
    python = repository / ".venv/bin/python"
    python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    python.chmod(0o755)
    relative = (
        "desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
        if sys.platform == "darwin"
        else "desktop/node_modules/electron/dist/electron"
    )
    electron = repository / relative
    electron.parent.mkdir(parents=True)
    electron.write_text(
        '#!/bin/sh\npwd > "$KRONIG_LAUNCH_MARKER"\n'
        'printf "%s\\n" "$TCAD_DEVSIM_PYTHON" >> "$KRONIG_LAUNCH_MARKER"\n'
    )
    electron.chmod(0o755)
    marker = tmp_path / "launched.txt"
    completed = subprocess.run(
        ["bash", str(shortcut)],
        cwd=tmp_path,
        env={"PATH": os.defpath, "KRONIG_LAUNCH_MARKER": str(marker)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert marker.read_text().splitlines() == [
        str(repository / "desktop"),
        str(tmp_path / "devsim/.venv/bin/python"),
    ]
