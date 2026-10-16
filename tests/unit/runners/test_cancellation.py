"""Cancellation must stop the real owned worker, not just the chat spinner."""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from openhands.sdk.conversation.cancellation import CancellationToken

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import BackendBinding
from tcad_agent.agent.tools import TcadDomainAction, TcadDomainExecutor
from tcad_agent.desktop.devsim_runner import DevsimSidecarRunner
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.results.models import CanonicalResult, OperatingPoint
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import CompiledJob, NativeRunResult
from tcad_agent.runners.process import ExecutionCancelled, cancellation_scope, raise_if_cancelled


def test_cancellation_context_does_not_leak_into_another_thread_or_next_run():
    token = CancellationToken()
    failures = []

    def independent_run():
        try:
            raise_if_cancelled()
        except ExecutionCancelled as error:
            failures.append(error)

    with cancellation_scope(lambda: token.is_cancelled):
        token.cancel()
        thread = threading.Thread(target=independent_run)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert not failures
        with pytest.raises(ExecutionCancelled):
            raise_if_cancelled()
    raise_if_cancelled()


@pytest.mark.parametrize("stop_at", ["normalized", "refined_compilation"])
def test_cancel_between_mesh_solves_never_launches_the_next_native_job(
    tmp_path, valid_spec, result_bundle_factory, monkeypatch, stop_at
):
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))
    source = result_bundle_factory(tmp_path / "source")
    canonical = CanonicalResult.model_validate_json((source / "results/canonical.json").read_text())
    canonical = canonical.model_copy(
        update={
            "operating_points": tuple(
                OperatingPoint(
                    index=i,
                    state="converged",
                    terminal_currents_a_per_m2=p.terminal_currents_a_per_m2,
                )
                for i, p in enumerate(canonical.bias_points)
            )
        }
    )
    token = CancellationToken()
    compiled, launched = [], []
    adapter = DevsimAdapter.from_defaults()

    class ControlledAdapter:
        def compile(self, spec, directory):
            job = adapter.compile(spec, directory)
            compiled.append(job)
            if len(compiled) == 2 and stop_at == "refined_compilation":
                token.cancel()
            return job

        def normalize(self, native):
            if stop_at == "normalized":
                token.cancel()
            return canonical

    class RecordingRunner:
        def run(self, job, budget):
            launched.append(job)
            stdout = job.entrypoint.parent / "stdout.log"
            stderr = job.entrypoint.parent / "stderr.log"
            stdout.touch()
            stderr.touch()
            return NativeRunResult(
                backend="devsim",
                status="completed",
                return_code=0,
                stdout_path=stdout,
                stderr_path=stderr,
                elapsed_seconds=0,
            )

    engine = ExperimentEngine(
        backend_resolver=lambda _: BackendBinding(
            adapter=ControlledAdapter(), runner=RecordingRunner()
        )
    )
    prepared = engine.prepare(valid_spec, "devsim")
    executor = TcadDomainExecutor(tmp_path / "repo")
    executor.tools.experiment_engine = engine
    response = executor(
        TcadDomainAction(
            operation="execute_experiment",
            payload={
                "prepared": prepared.model_dump(mode="json"),
                "approved_plan_digest": prepared.plan_digest,
            },
        ),
        conversation=SimpleNamespace(cancel_token=token),
    )
    assert response.code == "experiment_cancelled", response
    assert len(launched) == 1
    assert len(compiled) == (1 if stop_at == "normalized" else 2)
    assert not list((tmp_path / "data").rglob("manifest.json"))


def test_already_cancelled_tool_never_admits_a_native_job(tmp_path, valid_spec, monkeypatch):
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))

    class ForbiddenRunner:
        def run(self, job, budget):
            raise AssertionError("a cancelled tool launched a native job")

    engine = ExperimentEngine(
        backend_resolver=lambda _: BackendBinding(
            adapter=DevsimAdapter.from_defaults(), runner=ForbiddenRunner()
        )
    )
    prepared = engine.prepare(valid_spec, "devsim")
    executor = TcadDomainExecutor(tmp_path / "repo")
    executor.tools.experiment_engine = engine
    token = CancellationToken()
    token.cancel()
    response = executor(
        TcadDomainAction(
            operation="execute_experiment",
            payload={
                "prepared": prepared.model_dump(mode="json"),
                "approved_plan_digest": prepared.plan_digest,
            },
        ),
        conversation=SimpleNamespace(cancel_token=token),
    )

    assert response.code == "experiment_cancelled", response
    assert not list((tmp_path / "data").rglob("manifest.json"))


@pytest.mark.parametrize("desktop_owned,ignore_term", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize(
    "runner_kind",
    [
        "local",
        pytest.param("sidecar", marks=pytest.mark.skipif(os.name == "nt", reason="POSIX fixture")),
    ],
)
def test_stop_token_terminates_native_process_without_harming_other_run(
    tmp_path, valid_spec, monkeypatch, desktop_owned, ignore_term, runner_kind
):
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AGENT_KRONIG_DESKTOP_OWNER_PIPE", "1" if desktop_owned else "0")
    token = CancellationToken()
    pid_path = tmp_path / "worker.pid"
    program = (
        "import os,time,signal\nfrom pathlib import Path\n"
        + ("signal.signal(signal.SIGTERM,signal.SIG_IGN)\n" if ignore_term else "")
        + f"Path({str(pid_path)!r}).write_text(str(os.getpid()))\n"
        + "time.sleep(60)\n"
    )
    runner = LocalRunner(Path(sys.executable))
    if runner_kind == "sidecar":
        executable = tmp_path / "sidecar"
        executable.write_text(f"#!{Path(sys.executable).resolve()}\n" + program)
        executable.chmod(0o700)
        runner = DevsimSidecarRunner(executable)

    class WaitingAdapter:
        def compile(self, spec, directory):
            directory.mkdir(parents=True)
            entrypoint = directory / "worker.py"
            entrypoint.write_text(program)
            return CompiledJob(
                backend="devsim",
                entrypoint=entrypoint,
                input_files=(entrypoint,),
                input_digest="a" * 64,
                runtime_digest="b" * 64,
                compiler_version="fixture",
            )

        def normalize(self, native):
            raise AssertionError("a cancelled solve must not be normalized or published")

    engine = ExperimentEngine(
        backend_resolver=lambda _: BackendBinding(adapter=WaitingAdapter(), runner=runner)
    )
    prepared = engine.prepare(valid_spec, "devsim")
    executor = TcadDomainExecutor(tmp_path / "repo")
    executor.tools.experiment_engine = engine
    responses = []
    errors = []

    def execute():
        try:
            responses.append(
                executor(
                    TcadDomainAction(
                        operation="execute_experiment",
                        payload={
                            "prepared": prepared.model_dump(mode="json"),
                            "approved_plan_digest": prepared.plan_digest,
                        },
                    ),
                    conversation=SimpleNamespace(cancel_token=token),
                )
            )
        except BaseException as error:
            errors.append(error)

    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    thread = threading.Thread(target=execute, daemon=True)
    worker_pid = None
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not pid_path.exists() and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_path.exists(), errors or responses
        worker_pid = int(pid_path.read_text())
        token.cancel()
        thread.join(timeout=2)
        assert not thread.is_alive(), "Stop left the native solve running"
        assert not errors, errors
        assert responses[0].code == "experiment_cancelled", responses[0]
        with pytest.raises(ProcessLookupError):
            os.kill(worker_pid, 0)
        assert unrelated.poll() is None
        assert not list((tmp_path / "data").rglob("manifest.json"))
        assert not list((tmp_path / "data").rglob("worker.py"))
    finally:
        if thread.is_alive() and worker_pid:
            try:
                os.kill(worker_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        thread.join(timeout=3)
        unrelated.terminate()
        unrelated.wait(timeout=3)
