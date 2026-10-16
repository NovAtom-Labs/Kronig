"""Fixed, manifest-driven DEVSIM sidecar boundary for desktop distributions."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, MutableMapping, Sequence
from pathlib import Path
from typing import Any

from tcad_agent.adapters.devsim import density_solver, runtime, statistics
from tcad_agent.runners.models import CompiledJob, NativeRunResult, RunBudget
from tcad_agent.runners.process import raise_if_cancelled, wait_for_process

_MANIFEST_NAME = "compiled-job.json"
_DLL_DIRECTORY_HANDLES: list[object] = []


def configure_bundled_math_runtime(
    bundle_root: Path | None,
    *,
    platform_name: str = sys.platform,
    environment: MutableMapping[str, str] = os.environ,
    add_dll_directory: Callable[[str], object] | None = None,
) -> None:
    """Configure dynamically loaded math libraries in a frozen sidecar."""

    if platform_name != "win32" or bundle_root is None:
        return
    runtime_directory = bundle_root / "math-runtime"
    candidates = [
        runtime_directory / "mkl_rt.dll",
        *sorted(runtime_directory.glob("mkl_rt.*.dll")),
    ]
    runtime = next((path for path in candidates if path.is_file()), None)
    if runtime is None:
        raise RuntimeError("the frozen DEVSIM sidecar is missing its MKL runtime")
    register = add_dll_directory or getattr(os, "add_dll_directory", None)
    if register is None:
        raise RuntimeError("Windows DLL directory registration is unavailable")
    handle = register(str(runtime_directory))
    if handle is not None:
        _DLL_DIRECTORY_HANDLES.append(handle)
    environment["DEVSIM_MATH_LIBS"] = str(runtime)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_bytes(module: Any) -> bytes:
    module_path = Path(module.__file__)
    source_path = module_path if module_path.suffix == ".py" else module_path.with_suffix(".py")
    if source_path.is_file():
        return source_path.read_bytes()
    return inspect.getsource(module).encode("utf-8")


def _runtime_digest(main: bytes, stats: bytes, density: bytes) -> str:
    # Same filename-delimited compiler contract, verified with real compiled jobs.
    return hashlib.sha256(
        b"run_devsim.py\0" + main + b"\0devsim_statistics.py\0" + stats
        + b"\0devsim_density_solver.py\0" + density
    ).hexdigest()


def _trusted_runtime_digest() -> str:
    return _runtime_digest(
        _source_bytes(runtime), _source_bytes(statistics), _source_bytes(density_solver)
    )


def _inside(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("compiled job path is malformed")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError("compiled job paths must be relative")
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("compiled job paths must remain inside the compiled job root")
    return resolved


def _validated_manifest(
    manifest_path: Path,
    *,
    trusted_runtime_digest: str,
) -> tuple[Path, Path, Path]:
    manifest_path = manifest_path.resolve()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("compiled job manifest must be an object")
    if data.get("schema_version") != 1 or data.get("backend") != "devsim":
        raise ValueError("compiled job manifest has an unsupported contract")
    root_value = data.get("job_root")
    if not isinstance(root_value, str):
        raise ValueError("compiled job root is missing")
    root = Path(root_value).resolve()
    if not root.is_dir() or not manifest_path.is_relative_to(root):
        raise ValueError("manifest must be inside the compiled job root")

    entrypoint = _inside(root, data.get("entrypoint"))
    inputs_value = data.get("input_files")
    if not isinstance(inputs_value, list) or len(inputs_value) not in {2, 4}:
        raise ValueError("compiled job must contain only the reviewed runtime inputs")
    input_paths = tuple(_inside(root, value) for value in inputs_value)
    if entrypoint not in input_paths or not all(path.is_file() for path in input_paths):
        raise ValueError("compiled job inputs are missing")

    arguments = data.get("arguments")
    if not isinstance(arguments, list) or len(arguments) != 1:
        raise ValueError("compiled job must provide one input argument")
    payload_path = _inside(root, arguments[0])
    if payload_path not in input_paths or payload_path == entrypoint:
        raise ValueError("compiled job input argument is not allowlisted")

    runtime_digest = data.get("runtime_digest")
    input_digest = data.get("input_digest")
    actual_runtime_digest = _sha256(entrypoint)
    if len(input_paths) == 4:
        named = {path.name: path for path in input_paths}
        expected = {
            entrypoint.name, payload_path.name, "devsim_statistics.py", "devsim_density_solver.py"
        }
        if len(expected) != 4 or set(named) != expected:
            raise ValueError("compiled runtime does not match the reviewed runtime file set")
        actual_runtime_digest = _runtime_digest(
            entrypoint.read_bytes(), named["devsim_statistics.py"].read_bytes(),
            named["devsim_density_solver.py"].read_bytes(),
        )
    if (
        not isinstance(runtime_digest, str)
        or actual_runtime_digest != runtime_digest
        or runtime_digest != trusted_runtime_digest
    ):
        raise ValueError("compiled runtime does not match the installed reviewed runtime")
    if not isinstance(input_digest, str) or _sha256(payload_path) != input_digest:
        raise ValueError("compiled input digest does not match")

    budget = data.get("budget_seconds")
    if not isinstance(budget, int | float) or not 0 < float(budget) <= 3600:
        raise ValueError("compiled run budget is invalid")
    return root, entrypoint, payload_path


def execute_manifest(
    manifest_path: Path,
    *,
    runtime_main: Callable[[], int] = runtime.main,
    trusted_runtime_digest: str | None = None,
) -> int:
    """Validate one compiler-produced job and invoke only the reviewed runtime."""

    root, entrypoint, payload_path = _validated_manifest(
        manifest_path,
        trusted_runtime_digest=trusted_runtime_digest or _trusted_runtime_digest(),
    )
    previous_cwd = Path.cwd()
    previous_argv = sys.argv[:]
    try:
        os.chdir(root)
        sys.argv = [str(entrypoint), str(payload_path)]
        return int(runtime_main())
    finally:
        sys.argv = previous_argv
        os.chdir(previous_cwd)


def write_compiled_job_manifest(job: CompiledJob, budget: RunBudget) -> Path:
    """Serialize the typed compiler contract without adding executable input."""

    if job.backend != "devsim":
        raise ValueError("desktop DEVSIM runner accepts only devsim jobs")
    root = job.entrypoint.parent.resolve()
    entrypoint = job.entrypoint.resolve()
    inputs = tuple(path.resolve() for path in job.input_files)
    if (
        not entrypoint.is_relative_to(root)
        or any(not path.is_relative_to(root) for path in inputs)
    ):
        raise ValueError("compiled inputs must remain inside its compiled workspace")
    manifest_path = root / _MANIFEST_NAME
    payload: dict[str, Any] = {
        "schema_version": 1,
        "backend": "devsim",
        "job_root": str(root),
        "entrypoint": entrypoint.relative_to(root).as_posix(),
        "arguments": list(job.arguments),
        "input_files": [path.relative_to(root).as_posix() for path in inputs],
        "input_digest": job.input_digest,
        "runtime_digest": job.runtime_digest,
        "compiler_version": job.compiler_version,
        "budget_seconds": budget.seconds,
    }
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    temporary.replace(manifest_path)
    return manifest_path


class DevsimSidecarRunner:
    """Execute compiler-produced DEVSIM jobs through the packaged fixed sidecar."""

    def __init__(self, executable: Path) -> None:
        self.executable = executable.resolve()

    def run(self, job: CompiledJob, budget: RunBudget) -> NativeRunResult:
        raise_if_cancelled()
        if not self.executable.is_file():
            raise FileNotFoundError(self.executable)
        workspace = job.entrypoint.parent.resolve()
        manifest_path = write_compiled_job_manifest(job, budget)
        stdout_path = workspace / "stdout.log"
        stderr_path = workspace / "stderr.log"
        result_path = workspace / "native_result.json"
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "TMPDIR", "TEMP", "LANG", "LC_ALL"}
        }
        started = time.monotonic()
        owns_group = os.name != "nt" and os.environ.get("AGENT_KRONIG_DESKTOP_OWNER_PIPE") != "1"
        with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
            process = subprocess.Popen(
                [str(self.executable), str(manifest_path)],
                cwd=workspace,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                text=True,
                start_new_session=owns_group,
            )
            try:
                return_code = wait_for_process(process, budget.seconds, owns_group=owns_group)
            except subprocess.TimeoutExpired:
                return NativeRunResult(
                    backend="devsim",
                    status="timed_out",
                    return_code=process.returncode,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    elapsed_seconds=time.monotonic() - started,
                    error=f"simulation exceeded {budget.seconds} seconds",
                )
        elapsed = time.monotonic() - started
        return self._result(
            return_code,
            result_path,
            stdout_path,
            stderr_path,
            elapsed,
        )

    @staticmethod
    def _result(
        return_code: int,
        result_path: Path,
        stdout_path: Path,
        stderr_path: Path,
        elapsed: float,
    ) -> NativeRunResult:
        if return_code != 0:
            return NativeRunResult(
                backend="devsim",
                status="execution_failed",
                return_code=return_code,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                elapsed_seconds=elapsed,
                error="simulator process returned a nonzero exit status",
            )
        if not result_path.is_file():
            return NativeRunResult(
                backend="devsim",
                status="malformed_result",
                return_code=return_code,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                elapsed_seconds=elapsed,
                error="simulator did not create native_result.json",
            )
        try:
            json.loads(result_path.read_text())
        except (json.JSONDecodeError, OSError):
            return NativeRunResult(
                backend="devsim",
                status="malformed_result",
                return_code=return_code,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                result_path=result_path,
                elapsed_seconds=elapsed,
                error="simulator produced an invalid native result",
            )
        return NativeRunResult(
            backend="devsim",
            status="completed",
            return_code=return_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            result_path=result_path,
            elapsed_seconds=elapsed,
        )


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    try:
        bundle_root_value = getattr(sys, "_MEIPASS", None)
        configure_bundled_math_runtime(
            Path(bundle_root_value) if bundle_root_value else None
        )
        if len(values) != 1:
            raise ValueError("one compiled job manifest is required")
        return execute_manifest(Path(values[0]))
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, TypeError, KeyError):
        print(
            "Agent Kronig rejected an invalid compiled DEVSIM job.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
