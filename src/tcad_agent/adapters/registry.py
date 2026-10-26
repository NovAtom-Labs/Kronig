"""Single composition point for backend-specific adapters and runners."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tcad_agent.adapters.base import Adapter
from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.sentaurus.compiler import SentaurusAdapter
from tcad_agent.desktop.devsim_runner import DevsimSidecarRunner
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import CompiledJob, NativeRunResult, RunBudget
from tcad_agent.runners.remote import RemoteRunnerConfig, RemoteSentaurusRunner
from tcad_agent.runners.ssh import SSHSentaurusRunner


class BackendAdapterUnavailable(RuntimeError):
    """Raised when a declared backend has no installed execution binding."""


class Runner(Protocol):
    def run(self, job: CompiledJob, budget: RunBudget) -> NativeRunResult: ...


@dataclass(frozen=True)
class BackendBinding:
    adapter: Adapter
    runner: Runner


def resolve_devsim_python(project_root: Path | None = None) -> Path:
    """Resolve a development DEVSIM interpreter without machine-specific defaults."""

    configured = os.getenv("TCAD_DEVSIM_PYTHON")
    if configured:
        return Path(configured).expanduser().absolute()

    root = (project_root or Path.cwd()).resolve()
    sibling_environment = root.parent / "devsim" / ".venv"
    candidates = (
        sibling_environment / "Scripts" / "python.exe",
        sibling_environment / "bin" / "python",
    )

    return next(
        (candidate.absolute() for candidate in candidates if candidate.is_file()),
        Path(sys.executable).absolute(),
    )


def get_backend(backend: str) -> BackendBinding:
    """Return the installed backend binding or refuse at one explicit seam."""

    if backend == "devsim":
        packaged_runner = os.getenv("AGENT_KRONIG_DEVSIM_RUNNER")

        if packaged_runner:
            return BackendBinding(
                adapter=DevsimAdapter.from_defaults(),
                runner=DevsimSidecarRunner(Path(packaged_runner)),
            )

        return BackendBinding(
            adapter=DevsimAdapter.from_defaults(),
            runner=LocalRunner(resolve_devsim_python()),
        )

    if backend == "sentaurus":
        runner_type = os.getenv("TCAD_SENTAURUS_RUNNER", "remote").lower()

        if runner_type == "ssh":
            return BackendBinding(
                adapter=SentaurusAdapter.from_defaults(),
                runner=SSHSentaurusRunner(),
            )

        if runner_type == "remote":
            return BackendBinding(
                adapter=SentaurusAdapter.from_defaults(),
                runner=RemoteSentaurusRunner(
                    RemoteRunnerConfig.from_environment()
                ),
            )

        raise BackendAdapterUnavailable(
            f"unknown Sentaurus runner: {runner_type}"
        )

    raise BackendAdapterUnavailable(
        f"{backend} adapter and runner are not installed"
    )