#!/usr/bin/env python3
"""Export portable native-build runtime paths for later GitHub Actions steps."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _windows_mkl_runtime(python_prefix: Path) -> Path:
    runtime_directory = python_prefix / "Library" / "bin"
    candidates = [
        runtime_directory / "mkl_rt.dll",
        *sorted(runtime_directory.glob("mkl_rt.*.dll")),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError(
        "Windows DEVSIM requires an MKL runtime under "
        f"{runtime_directory}; install the pinned mkl package first"
    )


def configure_environment(
    github_environment: Path,
    *,
    github_path: Path | None = None,
    python_executable: Path = Path(sys.executable),
    platform_name: str = sys.platform,
    python_prefix: Path = Path(sys.prefix),
) -> None:
    """Export the active interpreter and native math runtime for later CI steps."""

    with github_environment.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"TCAD_DEVSIM_PYTHON={python_executable}\n")
        if platform_name == "win32":
            runtime = _windows_mkl_runtime(python_prefix)
            handle.write(f"DEVSIM_MATH_LIBS={runtime}\n")
    if platform_name == "win32":
        if github_path is None:
            raise RuntimeError("GITHUB_PATH is required on Windows")
        runtime_directory = python_prefix / "Library" / "bin"
        with github_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{runtime_directory.resolve()}\n")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, help="isolated simulator Python executable")
    args = parser.parse_args(arguments)
    target = os.getenv("GITHUB_ENV")
    if not target:
        raise RuntimeError("GITHUB_ENV is required")
    path_target = os.getenv("GITHUB_PATH")
    # Resolving a venv's executable symlink selects the base interpreter and loses
    # its installed packages. Make the path absolute without dereferencing it.
    simulator = args.python.expanduser().absolute() if args.python else Path(sys.executable)
    configure_environment(
        Path(target),
        github_path=Path(path_target) if path_target else None,
        python_executable=simulator,
        python_prefix=simulator.parent.parent if args.python else Path(sys.prefix),
        platform_name=sys.platform,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
