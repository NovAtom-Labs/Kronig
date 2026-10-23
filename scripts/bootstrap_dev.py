#!/usr/bin/env python3
"""Prepare a fast, repeatable Agent Kronig source-development checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

BOOTSTRAP_SCHEMA = "2"


class BootstrapError(RuntimeError):
    """Raised when a development checkout cannot be prepared safely."""


@dataclass(frozen=True)
class DevelopmentPaths:
    repository: Path
    application_python: Path
    devsim_python: Path
    electron: Path
    cache: Path


def development_paths(repository: Path, system: str) -> DevelopmentPaths:
    """Return platform-native paths for isolated development runtimes."""

    repository = repository.resolve()
    electron_parts: tuple[str, ...]
    if system == "Windows":
        python_parts = ("Scripts", "python.exe")
        electron_parts = ("desktop", "node_modules", "electron", "dist", "electron.exe")
    elif system == "Linux":
        python_parts = ("bin", "python")
        electron_parts = ("desktop", "node_modules", "electron", "dist", "electron")
    elif system == "Darwin":
        python_parts = ("bin", "python")
        electron_parts = (
            "desktop",
            "node_modules",
            "electron",
            "dist",
            "Electron.app",
            "Contents",
            "MacOS",
            "Electron",
        )
    else:
        raise BootstrapError("Development setup supports Windows, macOS, and Linux.")
    return DevelopmentPaths(
        repository=repository,
        application_python=repository.joinpath(".venv", *python_parts),
        devsim_python=repository.parent.joinpath("devsim", ".venv", *python_parts),
        electron=repository.joinpath(*electron_parts),
        cache=repository / ".tcad-agent-dev" / "bootstrap.json",
    )


def _version(value: str | None) -> tuple[int, int, int] | None:
    if value is None:
        return None
    match = re.search(r"(?:^|\s|v)(\d+)\.(\d+)(?:\.(\d+))?", value)
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def validate_versions(
    *,
    python_version: tuple[int, int, int],
    git_output: str | None,
    node_output: str | None,
    pnpm_output: str | None,
) -> tuple[str, ...]:
    """Return every actionable prerequisite problem in one pass."""

    errors: list[str] = []
    if python_version[:2] != (3, 13):
        errors.append(
            "Python 3.13 is required; found "
            f"{python_version[0]}.{python_version[1]}.{python_version[2]}."
        )
    if git_output is None:
        errors.append("Git is required and was not found on PATH.")
    node_version = _version(node_output)
    if node_output is None:
        errors.append("Node.js 24 is required and was not found on PATH.")
    elif node_version is None:
        errors.append("Node.js 24 is required; the installed version could not be read.")
    elif node_version[0] != 24:
        found = ".".join(map(str, node_version))
        errors.append(f"Node.js 24 is required; found {found}.")
    pnpm_version = _version(pnpm_output)
    if pnpm_output is None:
        errors.append("pnpm 11.19 is required and was not found on PATH.")
    elif pnpm_version is None:
        errors.append("pnpm 11.19 is required; the installed version could not be read.")
    elif pnpm_version[:2] != (11, 19):
        found = ".".join(map(str, pnpm_version))
        errors.append(f"pnpm 11.19 is required; found {found}.")
    return tuple(errors)


def dependency_fingerprint(paths: Sequence[Path], metadata: Sequence[str]) -> str:
    """Hash dependency inputs and toolchain identity for safe setup reuse."""

    digest = hashlib.sha256()
    for item in metadata:
        digest.update(b"metadata\0")
        digest.update(item.encode("utf-8"))
        digest.update(b"\0")
    for path in paths:
        digest.update(b"file\0")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def application_fingerprint(paths: DevelopmentPaths, metadata: Sequence[str]) -> str:
    return dependency_fingerprint(
        tuple(
            paths.repository / name
            for name in ("requirements.txt", "requirements.lock", "pyproject.toml")
        ),
        (*metadata, "editable-install=true"),
    )


def _application_versions(paths: DevelopmentPaths) -> dict[str, str]:
    versions = dict(
        re.findall(
            r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([^ ;\n]+)$",
            (paths.repository / "requirements.txt").read_text(),
            re.MULTILINE,
        )
    )
    project = tomllib.loads((paths.repository / "pyproject.toml").read_text())["project"]
    versions[project["name"]] = project["version"]
    return versions


def simulator_versions(paths: DevelopmentPaths, system: str) -> dict[str, str]:
    from pip._vendor.packaging.requirements import Requirement

    environment = {
        "sys_platform": {"Windows": "win32", "Linux": "linux", "Darwin": "darwin"}[system]
    }
    versions = {"numpy": _application_versions(paths)["numpy"]}
    for line in (paths.repository / "requirements/devsim.txt").read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate(environment):
            continue
        for specifier in requirement.specifier:
            if specifier.operator == "==":
                versions[requirement.name] = specifier.version
    return versions


def python_ready(python: Path, versions: dict[str, str], *, lock: Path | None = None) -> bool:
    """Check cached interpreter and dependency identities without loading a model."""
    # pip is present in both isolated environments, including the minimal simulator
    # environment. Its vendored parser avoids adding an application dependency there.
    program = """
import json, subprocess, sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.version import Version
assert sys.version_info[:2] == (3, 13)
assert all(Version(version(name)) == Version(wanted)
           for name, wanted in json.loads(sys.argv[1]).items())
if sys.argv[2]:
    for line in Path(sys.argv[2]).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = version(requirement.name)
        except PackageNotFoundError:
            continue  # An OS-specific or unselected extra need not be installed.
        assert requirement.specifier.contains(installed, prereleases=True)
subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True, capture_output=True)
"""
    probe_environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME"):
        probe_environment.pop(name, None)
    try:
        return (
            subprocess.run(
                [str(python), "-c", program, json.dumps(versions), str(lock) if lock else ""],
                capture_output=True,
                check=False,
                timeout=30,
                env=probe_environment,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


class BootstrapCache:
    """Small credential-free record of completed dependency stages."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict[str, str]:
        try:
            payload = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        stages = payload.get("stages") if isinstance(payload, dict) else None
        if not isinstance(stages, dict):
            return {}
        return {
            str(name): str(fingerprint)
            for name, fingerprint in stages.items()
            if isinstance(name, str) and isinstance(fingerprint, str)
        }

    def is_current(
        self,
        stage: str,
        fingerprint: str,
        outputs: Sequence[Path],
    ) -> bool:
        return self._read().get(stage) == fingerprint and all(output.exists() for output in outputs)

    def record(self, stage: str, fingerprint: str) -> None:
        stages = self._read()
        stages[stage] = fingerprint
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {"schema": BOOTSTRAP_SCHEMA, "stages": stages},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary.replace(self.path)


def _capture(command: str, *arguments: str) -> str | None:
    executable = shutil.which(command)
    if executable is None:
        return None
    completed = subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode:
        return None
    return completed.stdout.strip() or completed.stderr.strip()


def _run(command: Sequence[str], repository: Path) -> None:
    subprocess.run(tuple(command), cwd=repository, check=True)


def _prepare_application(paths: DevelopmentPaths) -> None:
    if not paths.application_python.exists():
        _run((sys.executable, "-m", "venv", str(paths.repository / ".venv")), paths.repository)
    python = str(paths.application_python)
    _run((python, "-c", "import sys; assert sys.version_info[:2] == (3,13)"), paths.repository)
    _run((python, "-m", "pip", "install", "--upgrade", "pip"), paths.repository)
    # pip-compile retains dependency extras, but pip forbids them in constraints.
    # Keep the reviewed lock intact and project only the constraint package names.
    with tempfile.TemporaryDirectory(prefix="kronig-constraints-") as temporary:
        constraints = Path(temporary) / "constraints.txt"
        constraints.write_text(
            re.sub(
                r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\[[^\]\n]+\](?===)",
                r"\1",
                (paths.repository / "requirements.lock").read_text(),
                flags=re.MULTILINE,
            )
        )
        _run(
            (
                python,
                "-m",
                "pip",
                "install",
                "-r",
                str(paths.repository / "requirements.txt"),
                "-c",
                str(constraints),
            ),
            paths.repository,
        )
    _run(
        (python, "-m", "pip", "install", "--editable", str(paths.repository), "--no-deps"),
        paths.repository,
    )
    _run((python, "-m", "pip", "check"), paths.repository)


def _prepare_devsim(paths: DevelopmentPaths) -> None:
    environment = paths.devsim_python.parent.parent
    if not paths.devsim_python.exists():
        environment.parent.mkdir(parents=True, exist_ok=True)
        _run((sys.executable, "-m", "venv", str(environment)), paths.repository)
    python = str(paths.devsim_python)
    _run((python, "-m", "pip", "install", "--upgrade", "pip"), paths.repository)
    _run(
        (
            python,
            "-m",
            "pip",
            "install",
            "-r",
            str(paths.repository / "requirements/devsim.txt"),
            "-c",
            str(paths.repository / "requirements.txt"),
        ),
        paths.repository,
    )


def _prepare_desktop(paths: DevelopmentPaths, pnpm: str) -> None:
    _run(
        (pnpm, "--dir", str(paths.repository / "desktop"), "install", "--frozen-lockfile"),
        paths.repository,
    )
    if not paths.electron.is_file():
        _run(
            (
                shutil.which("node") or "node",
                str(paths.repository / "desktop/node_modules/electron/install.js"),
            ),
            paths.repository,
        )


def _stage(
    *,
    name: str,
    label: str,
    fingerprint: str,
    outputs: Sequence[Path],
    cache: BootstrapCache,
    force: bool,
    prepare: Callable[[], None],
    verify: Callable[[], bool] | None = None,
) -> None:
    if not force and cache.is_current(name, fingerprint, outputs) and (verify is None or verify()):
        print(f"[ready] {label}")
        return
    print(f"[setup] {label}")
    prepare()
    missing = [str(output) for output in outputs if not output.exists()]
    if missing:
        raise BootstrapError(f"{label} did not create: {', '.join(missing)}")
    if verify is not None and not verify():
        raise BootstrapError(f"{label} failed its runtime check; no ready state was recorded")
    cache.record(name, fingerprint)
    print(f"[ready] {label}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare an Agent Kronig source checkout for native development."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="reinstall every dependency stage even when its fingerprint is current",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    repository = Path(__file__).resolve().parents[1]
    system = platform.system()
    try:
        paths = development_paths(repository, system)
    except BootstrapError as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        return 2

    pnpm_command = "pnpm.cmd" if system == "Windows" else "pnpm"
    git_output = _capture("git", "--version")
    node_output = _capture("node", "--version")
    pnpm_output = _capture(pnpm_command, "--version")
    errors = validate_versions(
        python_version=(sys.version_info.major, sys.version_info.minor, sys.version_info.micro),
        git_output=git_output,
        node_output=node_output,
        pnpm_output=pnpm_output,
    )
    if errors:
        print("Development setup cannot continue:", file=sys.stderr)
        for issue in errors:
            print(f"  - {issue}", file=sys.stderr)
        return 2

    assert node_output is not None and pnpm_output is not None
    pnpm = shutil.which(pnpm_command)
    if pnpm is None:
        raise AssertionError("validated pnpm executable disappeared")
    common = (
        f"schema={BOOTSTRAP_SCHEMA}",
        f"python={platform.python_version()}",
        f"system={system}",
        f"architecture={platform.machine()}",
    )
    application_digest = application_fingerprint(paths, common)
    devsim_fingerprint = dependency_fingerprint(
        (repository / "requirements.txt", repository / "requirements/devsim.txt"),
        common,
    )
    desktop_fingerprint = dependency_fingerprint(
        (repository / "desktop/package.json", repository / "desktop/pnpm-lock.yaml"),
        (*common, f"node={node_output}", f"pnpm={pnpm_output}"),
    )
    cache = BootstrapCache(paths.cache)
    try:
        application_versions = _application_versions(paths)
        _stage(
            name="application",
            label="Python application environment",
            fingerprint=application_digest,
            outputs=(paths.application_python,),
            cache=cache,
            force=arguments.force,
            prepare=lambda: _prepare_application(paths),
            verify=lambda: python_ready(
                paths.application_python,
                application_versions,
                lock=repository / "requirements.lock",
            ),
        )
        _stage(
            name="devsim",
            label="isolated DEVSIM environment",
            fingerprint=devsim_fingerprint,
            outputs=(paths.devsim_python,),
            cache=cache,
            force=arguments.force,
            prepare=lambda: _prepare_devsim(paths),
            verify=lambda: python_ready(
                paths.devsim_python,
                simulator_versions(paths, system),
            ),
        )
        _stage(
            name="desktop",
            label="desktop dependencies",
            fingerprint=desktop_fingerprint,
            outputs=(paths.electron,),
            cache=cache,
            force=arguments.force,
            prepare=lambda: _prepare_desktop(paths, pnpm),
        )
        _run(
            (
                str(paths.application_python),
                str(repository / "scripts/rebuild_knowledge_index.py"),
                "--project-root",
                str(repository),
                "--fetch-sources",
                "--if-stale",
            ),
            repository,
        )
    except (BootstrapError, subprocess.CalledProcessError, OSError) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        return 1

    launch = {
        "Windows": ".\\scripts\\run_desktop_dev.ps1",
        "Darwin": './"Launch Agent Kronig Dev.command"',
        "Linux": "./scripts/run_desktop_dev.sh",
    }[system]
    print("\nAgent Kronig development setup is ready.")
    print(f"Launch with: {launch}")
    print("Configure Bedrock through Settings after the application opens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
