"""Bounded shell-free execution for local simulator jobs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from tcad_agent.runners.models import CompiledJob, NativeRunResult, RunBudget


class LocalRunner:
    def __init__(self, devsim_python: Path) -> None:
        self.devsim_python = devsim_python.absolute()

    def run(self, job: CompiledJob, budget: RunBudget) -> NativeRunResult:
        if job.backend != "devsim":
            raise ValueError(f"local runner cannot execute backend {job.backend!r}")
        if not self.devsim_python.is_file():
            raise FileNotFoundError(self.devsim_python)
        workspace = job.entrypoint.parent.resolve()
        if not job.entrypoint.resolve().is_relative_to(workspace):
            raise ValueError("entrypoint must be inside its compiled workspace")
        stdout_path = workspace / "stdout.log"
        stderr_path = workspace / "stderr.log"
        result_path = workspace / "native_result.json"
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "TMPDIR", "LANG", "LC_ALL"}
        }
        environment.update(job.environment)
        environment["PYTHONUNBUFFERED"] = "1"
        command = [str(self.devsim_python), str(job.entrypoint), *job.arguments]
        owns_group = os.name != "nt" and os.environ.get("AGENT_KRONIG_DESKTOP_OWNER_PIPE") != "1"
        started = time.monotonic()
        with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                text=True,
                start_new_session=owns_group,
            )
            try:
                return_code = process.wait(timeout=budget.seconds)
            except subprocess.TimeoutExpired:
                if owns_group:
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if owns_group:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait(timeout=5)
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
        except (json.JSONDecodeError, OSError) as exc:
            return NativeRunResult(
                backend="devsim",
                status="malformed_result",
                return_code=return_code,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                result_path=result_path,
                elapsed_seconds=elapsed,
                error=f"invalid native result: {exc}",
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
