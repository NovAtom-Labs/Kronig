"""Real local-runner ownership and timeout boundaries inside a fixture backend."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("runner_kind", [
    "local",
    pytest.param("sidecar", marks=pytest.mark.skipif(
        os.name == "nt", reason="POSIX fixture executable"
    )),
])
def test_noninteractive_jobs_cannot_inherit_the_desktop_control_input(tmp_path, runner_kind):
    worker = tmp_path / "worker.py"
    worker.write_text(
        f"#!{Path(sys.executable).resolve()}\nimport pathlib,sys\n"
        "pathlib.Path('observed-input').write_text(sys.stdin.read())\n"
        "pathlib.Path('native_result.json').write_text('{}')\n"
    )
    worker.chmod(0o700)
    source = f"""
import sys
from pathlib import Path
from tcad_agent.runners.local import LocalRunner
from tcad_agent.desktop.devsim_runner import DevsimSidecarRunner
from tcad_agent.runners.models import CompiledJob, RunBudget
worker = Path({str(worker)!r})
job = CompiledJob(backend='devsim', entrypoint=worker, arguments=(), input_files=(worker,),
                  input_digest='a'*64, runtime_digest='b'*64, compiler_version='fixture')
runner = (LocalRunner(Path(sys.executable)) if {runner_kind!r} == 'local'
          else DevsimSidecarRunner(worker))
print(runner.run(job, RunBudget(seconds=1)).status, flush=True)
"""
    backend = subprocess.Popen(
        [sys.executable, "-c", source], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
        env={**os.environ, "AGENT_KRONIG_DESKTOP_OWNER_PIPE": "1",
             "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src")},
    )
    try:
        backend.wait(timeout=5)  # Keep the parent's write end open during execution.
        assert backend.stdout.read().strip() == "completed", backend.stderr.read()
        assert (tmp_path / "observed-input").read_text() == ""
    finally:
        if backend.poll() is None:
            backend.kill()
        backend.wait(timeout=5)
        backend.stdin.close()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group ownership")
@pytest.mark.parametrize("timeout", [False, True])
@pytest.mark.parametrize("desktop_owned", [False, True])
def test_local_job_respects_ownership_and_timeout_preserves_backend(
    tmp_path: Path, timeout: bool, desktop_owned: bool
) -> None:
    runtime = tmp_path / "runtime.py"
    runtime.write_text(
        "import json,os,pathlib,time\n"
        "pathlib.Path('worker-group').write_text(str(os.getpgrp()))\n"
        + (
            "time.sleep(60)\n" if timeout
            else "pathlib.Path('native_result.json').write_text('{}')\n"
        )
    )
    backend_source = f"""
import json, os, sys, time
from pathlib import Path
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import CompiledJob, RunBudget
runtime = Path({str(runtime)!r})
job = CompiledJob(backend='devsim', entrypoint=runtime, arguments=(), input_files=(runtime,),
                  input_digest='a'*64, runtime_digest='b'*64, compiler_version='fixture')
result = LocalRunner(Path(sys.executable)).run(job, RunBudget(seconds={0.3 if timeout else 5}))
print(json.dumps({{'status':result.status,'backend_group':os.getpgrp(),
                  'worker_group':int((runtime.parent/'worker-group').read_text())}}),flush=True)
time.sleep(60)
"""
    backend = subprocess.Popen(
        [sys.executable, "-c", backend_source], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True, text=True,
        env={**os.environ, "AGENT_KRONIG_DESKTOP_OWNER_PIPE": "1" if desktop_owned else "0",
             "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src")},
    )
    try:
        assert backend.stdout is not None
        line = backend.stdout.readline()
        assert line.strip(), "timeout incorrectly signalled or interrupted the backend"
        record = json.loads(line)
        assert record["status"] == ("timed_out" if timeout else "completed")
        assert (record["worker_group"] == record["backend_group"]) is desktop_owned
        assert backend.poll() is None, "per-job timeout must preserve the backend"
    finally:
        try:
            os.killpg(backend.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        backend.wait(timeout=5)
