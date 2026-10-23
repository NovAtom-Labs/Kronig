"""Real subprocess ownership checks; every cleanup targets fixture process identities."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

import pytest


def _live(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return code.value == 259
    record = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(record) and not record.startswith("Z")


def _wait_until_stopped(pids: list[int], seconds: float = 8) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not any(_live(pid) for pid in pids):
            return
        time.sleep(0.05)
    assert not [pid for pid in pids if _live(pid)], "owned subprocesses survived owner death"


@pytest.mark.parametrize("lost_process", [
    "owner", "backend", pytest.param("unobserved_group_worker", marks=pytest.mark.skipif(
        os.name == "nt", reason="POSIX group observation race"
    )),
    pytest.param("unobserved_group_shutdown", marks=pytest.mark.skipif(
        os.name == "nt", reason="POSIX group shutdown race"
    )),
    pytest.param("unobserved_local_runner", marks=pytest.mark.skipif(
        os.name == "nt", reason="POSIX local-runner ownership race"
    )),
])
def test_independent_monitor_cleans_workers_after_abrupt_death(
    tmp_path: Path, lost_process: str
) -> None:
    """Deleting independent owner supervision leaves resistant detached workers running."""
    worker = (
        "import faulthandler; faulthandler.dump_traceback_later(5); "
        "import os,signal,sys,time; print('fixture worker: entered '+str(os.getpid()),"
        "file=sys.stderr,flush=True); signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "print('fixture worker: handler ready',file=sys.stderr,flush=True); "
        "print('worker-ready',flush=True); faulthandler.cancel_dump_traceback_later(); "
        "time.sleep(60)"
    )
    unobserved = lost_process.startswith("unobserved_")
    abrupt_exit = (
        "os.killpg(os.getpgrp(), signal.SIGTERM)"
        if lost_process == "unobserved_group_shutdown"
        else "os.kill(os.getpid(), signal.SIGKILL)"
    )
    worker_creation = f"""
worker = subprocess.Popen([sys.executable, '-c', {worker!r}], stdout=subprocess.PIPE,
                          start_new_session={not unobserved!r} and os.name != 'nt', text=True)
print(f'fixture backend: worker spawned {{worker.pid}}', file=sys.stderr, flush=True)
assert worker.stdout.readline().strip() == 'worker-ready'
"""
    if lost_process == "unobserved_local_runner":
        local_worker = (
            "import os,signal,time\nfrom pathlib import Path\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            "Path('local-worker.pid').write_text(str(os.getpid()))\ntime.sleep(60)\n"
        )
        worker_creation = f"""
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import CompiledJob, RunBudget
runtime = Path(__file__).with_name('local-job.py')
runtime.write_text({local_worker!r})
job = CompiledJob(backend='devsim', entrypoint=runtime, arguments=(), input_files=(runtime,),
                  input_digest='a'*64, runtime_digest='b'*64, compiler_version='fixture')
Thread(target=lambda: LocalRunner(Path(sys.executable)).run(job, RunBudget(seconds=30)),
       daemon=True).start()
pidfile = runtime.with_name('local-worker.pid')
deadline = time.monotonic() + 5
while not pidfile.exists() or not pidfile.read_text().strip().isdecimal():
    if time.monotonic() > deadline: raise RuntimeError('fixture local worker did not start')
    time.sleep(.001)
worker = SimpleNamespace(pid=int(pidfile.read_text()))
"""
    backend_source = f"""
import faulthandler, json, os, signal, subprocess, sys, time
from tcad_agent.desktop.owner_monitor import start_owner_monitor
faulthandler.dump_traceback_later(5)
print('fixture backend: starting monitor', file=sys.stderr, flush=True)
monitor = start_owner_monitor()
print('fixture backend: monitor ready', file=sys.stderr, flush=True)
{ "os.kill(monitor.pid, signal.SIGSTOP)" if unobserved else "" }
{ worker_creation }
print('fixture backend: worker ready', file=sys.stderr, flush=True)
faulthandler.cancel_dump_traceback_later()
{ "" if unobserved else "time.sleep(.3)" }
print(json.dumps({{'backend':os.getpid(),'worker':worker.pid,'monitor':monitor.pid}}),flush=True)
{ abrupt_exit if unobserved else "" }
time.sleep(60)
"""
    script = tmp_path / "backend.py"
    script.write_text(backend_source)
    owner_source = f"""
import os, subprocess, sys, time
backend = subprocess.Popen([sys.executable, {str(script)!r}], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, text=True, start_new_session=True)
print(f'fixture owner: pid={{os.getpid()}} backend={{backend.pid}}', file=sys.stderr, flush=True)
print(backend.stdout.readline().strip(),flush=True)
time.sleep(60)
"""
    environment = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[3] / "src"),
        "AGENT_KRONIG_DESKTOP_OWNER_PIPE": "1",
        **({"PYLAUNCHER_DEBUG": "1"} if os.name == "nt" else {}),
    }
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    diagnostics = tmp_path / "fixture-stderr.log"
    with diagnostics.open("w") as trace:
        owner = subprocess.Popen(
            [sys.executable, "-c", owner_source], stdout=subprocess.PIPE, stderr=trace,
            text=True, env=environment,
        )
    records: dict[str, int] = {}
    try:
        assert owner.stdout is not None
        ready: Queue[str] = Queue()
        Thread(target=lambda: ready.put(owner.stdout.readline()), daemon=True).start()
        try:
            line = ready.get(timeout=15)
        except Empty:
            pytest.fail(f"fixture startup timed out: {diagnostics.read_text()[-3000:]}")
        assert line.strip(), f"backend did not establish ownership: {diagnostics.read_text()}"
        records = json.loads(line)
        if unobserved:
            # Force the orphaned/stopped-group ordering, rather than racing a
            # resume against backend exit and accidentally hiding SIGHUP.
            _wait_until_stopped([records["backend"]])
            try:
                os.kill(records["monitor"], signal.SIGCONT)
            except ProcessLookupError:
                pass  # The strict owned-process assertion below still applies.
        elif lost_process == "owner":
            owner.kill()
            owner.wait(timeout=5)
        else:
            os.kill(records["backend"], getattr(signal, "SIGKILL", signal.SIGTERM))
        try:
            _wait_until_stopped(list(records.values()))
        except AssertionError as error:
            raise AssertionError(
                f"{error}; fixture process roles: {records}; {diagnostics.read_text()}"
            ) from error
        assert unrelated.poll() is None, "cleanup must not affect unrelated processes"
    finally:
        for pid in records.values():
            if _live(pid):
                try:
                    os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                except ProcessLookupError:
                    pass  # A monitor can finish between inspection and teardown.
        if owner.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(owner.pid), "/T", "/F"],
                    capture_output=True, check=False, timeout=5,
                )
            else:
                owner.kill()
        owner.wait(timeout=5)
        unrelated.kill()
        unrelated.wait(timeout=5)
