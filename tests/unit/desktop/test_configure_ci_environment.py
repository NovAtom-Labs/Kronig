from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.configure_ci_environment import configure_environment


def test_configure_environment_exports_the_active_python(tmp_path: Path) -> None:
    github_environment = tmp_path / "github-env"

    configure_environment(
        github_environment,
        python_executable=Path("/opt/python/bin/python"),
        platform_name="linux",
    )

    assert github_environment.read_text(encoding="utf-8") == (
        f"TCAD_DEVSIM_PYTHON={Path('/opt/python/bin/python')}\n"
    )


def test_windows_environment_exports_the_installed_mkl_runtime_and_path(
    tmp_path: Path,
) -> None:
    github_environment = tmp_path / "github-env"
    github_path = tmp_path / "github-path"
    runtime_directory = tmp_path / "python" / "Library" / "bin"
    runtime_directory.mkdir(parents=True)
    runtime = runtime_directory / "mkl_rt.2.dll"
    runtime.write_bytes(b"fixture")

    configure_environment(
        github_environment,
        github_path=github_path,
        python_executable=tmp_path / "python" / "python.exe",
        platform_name="win32",
        python_prefix=tmp_path / "python",
    )

    assert github_environment.read_text(encoding="utf-8") == (
        f"TCAD_DEVSIM_PYTHON={tmp_path / 'python' / 'python.exe'}\nDEVSIM_MATH_LIBS={runtime}\n"
    )
    assert github_path.read_text(encoding="utf-8") == f"{runtime_directory}\n"


def test_ci_cli_selects_the_isolated_simulator_instead_of_application_python(tmp_path, monkeypatch):
    from scripts.configure_ci_environment import main

    target = tmp_path / "github-env"
    simulator = tmp_path / "devsim/bin/python"
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("GITHUB_ENV", str(target))
    assert main(["--python", str(simulator)]) == 0
    assert target.read_text() == f"TCAD_DEVSIM_PYTHON={simulator}\n"


@pytest.mark.skipif(os.name == "nt", reason="POSIX venv interpreter symlink regression")
def test_ci_export_preserves_virtual_environment_interpreter_identity(tmp_path, monkeypatch):
    from scripts.configure_ci_environment import main

    environment = tmp_path / "isolated simulator"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(environment)], check=True)
    target = tmp_path / "github-env"
    monkeypatch.setenv("GITHUB_ENV", str(target))
    assert main(["--python", str(environment / "bin/python")]) == 0
    executable = target.read_text().strip().split("=", 1)[1]
    prefix = subprocess.check_output([executable, "-c", "import sys; print(sys.prefix)"], text=True)
    assert Path(prefix.strip()) == environment
