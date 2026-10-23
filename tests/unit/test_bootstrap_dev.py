from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str) -> ModuleType:
    path = ROOT / "scripts" / f"{name}.py"
    if not path.is_file():
        pytest.fail(f"missing developer command: {path}")
    spec = importlib.util.spec_from_file_location(f"agent_kronig_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bootstrap_reports_every_missing_or_incompatible_prerequisite() -> None:
    bootstrap = load_script("bootstrap_dev")

    errors = bootstrap.validate_versions(
        python_version=(3, 12, 9),
        git_output=None,
        node_output="v22.18.0",
        pnpm_output="10.15.1",
    )

    assert errors == (
        "Python 3.13 is required; found 3.12.9.",
        "Git is required and was not found on PATH.",
        "Node.js 24 is required; found 22.18.0.",
        "pnpm 11.19 is required; found 10.15.1.",
    )


def test_bootstrap_distinguishes_missing_tools_from_unreadable_versions() -> None:
    bootstrap = load_script("bootstrap_dev")

    missing = bootstrap.validate_versions(
        python_version=(3, 13, 9),
        git_output="git version 2.50.1",
        node_output=None,
        pnpm_output=None,
    )
    unreadable = bootstrap.validate_versions(
        python_version=(3, 13, 9),
        git_output="git version 2.50.1",
        node_output="unexpected",
        pnpm_output="unexpected",
    )

    assert missing == (
        "Node.js 24 is required and was not found on PATH.",
        "pnpm 11.19 is required and was not found on PATH.",
    )
    assert unreadable == (
        "Node.js 24 is required; the installed version could not be read.",
        "pnpm 11.19 is required; the installed version could not be read.",
    )


def test_dependency_fingerprint_changes_for_inputs_or_toolchain(tmp_path: Path) -> None:
    bootstrap = load_script("bootstrap_dev")
    requirements = tmp_path / "requirements.txt"
    project = tmp_path / "pyproject.toml"
    requirements.write_text("fastapi==1\n")
    project.write_text("[project]\nname='example'\n")

    original = bootstrap.dependency_fingerprint(
        (requirements, project), ("python=3.13.9", "platform=Linux")
    )
    repeated = bootstrap.dependency_fingerprint(
        (requirements, project), ("python=3.13.9", "platform=Linux")
    )
    requirements.write_text("fastapi==2\n")
    changed_input = bootstrap.dependency_fingerprint(
        (requirements, project), ("python=3.13.9", "platform=Linux")
    )
    changed_toolchain = bootstrap.dependency_fingerprint(
        (requirements, project), ("python=3.13.9", "platform=Windows")
    )

    assert original == repeated
    assert original != changed_input
    assert changed_input != changed_toolchain


def test_bootstrap_cache_requires_matching_fingerprint_and_existing_outputs(
    tmp_path: Path,
) -> None:
    bootstrap = load_script("bootstrap_dev")
    output = tmp_path / ".venv" / "bin" / "python"
    output.parent.mkdir(parents=True)
    output.write_text("python")
    cache = bootstrap.BootstrapCache(tmp_path / ".tcad-agent-dev" / "bootstrap.json")

    assert cache.is_current("application", "first", (output,)) is False

    cache.record("application", "first")

    assert cache.is_current("application", "first", (output,)) is True
    assert cache.is_current("application", "second", (output,)) is False
    output.unlink()
    assert cache.is_current("application", "first", (output,)) is False
    assert "secret" not in cache.path.read_text().lower()


@pytest.mark.parametrize(
    ("system", "application_parts", "devsim_parts", "electron_parts"),
    [
        (
            "Windows",
            (".venv", "Scripts", "python.exe"),
            ("devsim", ".venv", "Scripts", "python.exe"),
            ("desktop", "node_modules", "electron", "dist", "electron.exe"),
        ),
        (
            "Linux",
            (".venv", "bin", "python"),
            ("devsim", ".venv", "bin", "python"),
            ("desktop", "node_modules", "electron", "dist", "electron"),
        ),
        (
            "Darwin",
            (".venv", "bin", "python"),
            ("devsim", ".venv", "bin", "python"),
            (
                "desktop",
                "node_modules",
                "electron",
                "dist",
                "Electron.app",
                "Contents",
                "MacOS",
                "Electron",
            ),
        ),
    ],
)
def test_development_paths_are_native_and_keep_devsim_separate(
    tmp_path: Path,
    system: str,
    application_parts: tuple[str, ...],
    devsim_parts: tuple[str, ...],
    electron_parts: tuple[str, ...],
) -> None:
    bootstrap = load_script("bootstrap_dev")
    repository = tmp_path / "agent-kronig"

    paths = bootstrap.development_paths(repository, system)

    assert paths.application_python == repository.joinpath(*application_parts)
    assert paths.devsim_python == tmp_path.joinpath(*devsim_parts)
    assert paths.electron == repository.joinpath(*electron_parts)


def test_bootstrap_help_is_available_without_modifying_the_checkout() -> None:
    bootstrap = load_script("bootstrap_dev")

    parser = bootstrap.build_parser()

    assert "Prepare an Agent Kronig source checkout" in parser.description


def test_application_install_constrains_transitive_versions(tmp_path, monkeypatch):
    bootstrap = load_script("bootstrap_dev")
    paths = bootstrap.development_paths(tmp_path / "checkout", "Linux")
    paths.application_python.parent.mkdir(parents=True)
    paths.application_python.touch()
    (paths.repository / "requirements.lock").write_text(
        "# generated lock\nhttpx[socks]==0.28.1\nnumpy==2.5.3\n"
    )
    commands = []

    def run(command, root):
        commands.append(tuple(command))
        if "-c" in command and "-r" in command:
            constraint = Path(command[command.index("-c") + 1])
            assert constraint.read_text() == ("# generated lock\nhttpx==0.28.1\nnumpy==2.5.3\n"), (
                "pip constraints must retain versions without requesting extras"
            )

    monkeypatch.setattr(bootstrap, "_run", run)

    bootstrap._prepare_application(paths)

    install = next(command for command in commands if "-r" in command)
    assert "-c" in install
    constraint = Path(install[install.index("-c") + 1])
    assert not constraint.exists(), "temporary projection must not bloat the checkout"
    assert "httpx[socks]" in (paths.repository / "requirements.lock").read_text()


def test_desktop_setup_installs_missing_trusted_electron_binary(tmp_path, monkeypatch):
    bootstrap = load_script("bootstrap_dev")
    paths = bootstrap.development_paths(tmp_path / "checkout", "Linux")
    installer = paths.repository / "desktop/node_modules/electron/install.js"

    def run(command, root):
        if "install" in command:
            installer.parent.mkdir(parents=True, exist_ok=True)
            installer.touch()
        if str(installer) in command:
            paths.electron.parent.mkdir(parents=True, exist_ok=True)
            paths.electron.touch()

    monkeypatch.setattr(bootstrap, "_run", run)
    bootstrap._prepare_desktop(paths, "pnpm")
    assert paths.electron.is_file(), "pnpm may skip dependency lifecycle scripts"


def test_application_fingerprint_includes_the_complete_lock(tmp_path):
    bootstrap = load_script("bootstrap_dev")
    root = tmp_path / "checkout"
    root.mkdir()
    for name in ("requirements.txt", "requirements.lock", "pyproject.toml"):
        (root / name).write_text("first\n")
    paths = bootstrap.development_paths(root, "Linux")
    first = bootstrap.application_fingerprint(paths, ("python=3.13",))
    (root / "requirements.lock").write_text("changed transitive dependency\n")
    assert first != bootstrap.application_fingerprint(paths, ("python=3.13",))


def test_windows_simulator_setup_installs_its_math_runtime(tmp_path, monkeypatch):
    bootstrap = load_script("bootstrap_dev")
    paths = bootstrap.development_paths(tmp_path / "checkout", "Windows")
    paths.devsim_python.parent.mkdir(parents=True)
    paths.devsim_python.touch()
    commands = []
    monkeypatch.setattr(bootstrap, "_run", lambda command, root: commands.append(tuple(command)))
    bootstrap._prepare_devsim(paths)
    assert any("mkl==2025.2.0" in command for command in commands)


def test_cached_setup_repairs_an_unhealthy_environment(tmp_path):
    bootstrap = load_script("bootstrap_dev")
    output = tmp_path / "python"
    output.touch()
    cache = bootstrap.BootstrapCache(tmp_path / "bootstrap.json")
    cache.record("application", "same")
    state = {"healthy": False}
    bootstrap._stage(
        name="application",
        label="application",
        fingerprint="same",
        outputs=(output,),
        cache=cache,
        force=False,
        prepare=lambda: state.update(healthy=True),
        verify=lambda: state["healthy"],
    )
    assert state["healthy"]


def test_python_health_probe_rejects_missing_or_wrong_dependencies():
    bootstrap = load_script("bootstrap_dev")
    assert bootstrap.python_ready(Path(sys.executable), {"pytest": "0.0.0"}) is False
    assert bootstrap.python_ready(Path(sys.executable), {"not-a-kronig-dependency": "1"}) is False


def test_python_health_probe_accepts_normalized_project_release_version():
    bootstrap = load_script("bootstrap_dev")
    assert bootstrap.python_ready(Path(sys.executable), {"novatom-tcad-agent": "0.1.0-alpha.12"})


def test_python_health_probe_rejects_missing_transitive_dependency(tmp_path):
    bootstrap = load_script("bootstrap_dev")
    environment = tmp_path / "environment"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    site_packages = Path(
        subprocess.check_output(
            [str(python), "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True
        ).strip()
    )
    metadata = site_packages / "setup_probe-1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: setup-probe\nVersion: 1.0\n"
        "Requires-Dist: missing-kronig-test-dependency>=1\n"
    )
    assert bootstrap.python_ready(python, {"setup-probe": "1.0"}) is False


def test_python_health_probe_rejects_installed_transitive_lock_drift(tmp_path):
    bootstrap = load_script("bootstrap_dev")
    lock = tmp_path / "requirements.lock"
    lock.write_text("# reviewed lock\nnumpy==0.0.0\n")
    assert bootstrap.python_ready(Path(sys.executable), {}, lock=lock) is False
