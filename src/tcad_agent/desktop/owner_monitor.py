"""Independent, credential-free supervision of the desktop backend's owned workers.

Electron holds the sole write end of backend stdin. The monitor retains its read
end, so even SIGKILL of either Electron or the backend triggers tree cleanup.
POSIX workers use the backend process group; separately detached descendants are
tracked with their start identities. An anchor preserves group continuity between
snapshots even after backend death. Windows workers inherit a native Job Object.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    parent: int
    group: int
    started: str


def process_snapshot() -> dict[int, ProcessIdentity]:
    """Inspect public process metadata only, never arguments or environments."""
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,pgid=,stat=,lstart="],
        capture_output=True, text=True, check=True,
    )
    records = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=4)
        if len(fields) != 5 or fields[3].startswith("Z"):
            continue
        pid, parent, group = map(int, fields[:3])
        # Linux exposes a monotonic start tick, eliminating same-second PID reuse.
        started = fields[4]
        if sys.platform.startswith("linux"):
            try:
                with open(f"/proc/{pid}/stat") as source:
                    started = source.read().rsplit(")", 1)[1].split()[19]
            except (OSError, IndexError):
                continue
        records[pid] = ProcessIdentity(pid, parent, group, started)
    return records


def _same_process(record: ProcessIdentity | None, owned: ProcessIdentity) -> bool:
    return record is not None and record.started == owned.started


def _collect_owned(
    snapshot: dict[int, ProcessIdentity],
    owned: dict[int, ProcessIdentity],
    backend_pid: int,
) -> None:
    root = owned.get(backend_pid)
    group_continues = root is not None and any(
        record.group == root.group and _same_process(snapshot.get(pid), record)
        for pid, record in owned.items()
    )
    while True:
        added = False
        for pid, record in snapshot.items():
            if pid == os.getpid() or pid in owned:
                continue
            parent = owned.get(record.parent)
            if (parent and _same_process(snapshot.get(parent.pid), parent)) or (
                root and group_continues and record.group == root.group
            ):
                owned[pid] = record
                added = True
        if not added:
            return


def _signal_owned(owned: dict[int, ProcessIdentity], backend_pid: int, signum: int) -> None:
    snapshot = process_snapshot()
    _collect_owned(snapshot, owned, backend_pid)
    root = owned[backend_pid]
    active = [
        record for record in owned.values() if _same_process(snapshot.get(record.pid), record)
    ]
    # A process group is addressed only while a captured member's identity matches.
    # Its anchor keeps this group continuous even when a worker was not sampled.
    # The independent monitor belongs to a separate group and is never signalled.
    if root.group == backend_pid and any(record.group == root.group for record in active):
        try:
            os.killpg(root.group, signum)
        except ProcessLookupError:
            pass
    for record in active:
        if record.group == root.group:
            continue
        if _same_process(process_snapshot().get(record.pid), record):
            try:
                os.kill(record.pid, signum)
            except ProcessLookupError:
                pass


def _watch_eof(stream: BinaryIO, lost: threading.Event) -> None:
    try:
        while stream.read(1):
            pass
    finally:
        lost.set()


def _monitor_posix(backend_pid: int, lost: threading.Event) -> None:
    snapshot = process_snapshot()
    if backend_pid not in snapshot:
        return
    owned = {backend_pid: snapshot[backend_pid]}
    root = owned[backend_pid]
    if root.group != backend_pid:
        raise RuntimeError("Desktop backend must own a dedicated process group")
    # The monitor stays in the backend session but has its own process group.
    # This read-only child joins the original group before work is admitted.
    # It closes with its monitor, or is killed along with the owned workers.
    command = (
        [sys.executable, "--owner-anchor"]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-c",
              "from tcad_agent.desktop.owner_monitor import anchor_main; anchor_main()"]
    )
    anchor = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        process_group=root.group,
    )
    assert anchor.stdout is not None
    anchor_ready = anchor.stdout.readline()
    anchor.stdout.close()
    if anchor_ready.strip() != b"anchored":
        raise RuntimeError("Desktop process group anchor could not start")
    snapshot = process_snapshot()
    if anchor.pid not in snapshot:
        raise RuntimeError("Desktop process group anchor could not start")
    owned[anchor.pid] = snapshot[anchor.pid]
    _collect_owned(snapshot, owned, backend_pid)
    print("owned", flush=True)
    while not lost.wait(0.05):
        snapshot = process_snapshot()
        _collect_owned(snapshot, owned, backend_pid)
        if not _same_process(snapshot.get(backend_pid), owned[backend_pid]):
            break
    _signal_owned(owned, backend_pid, signal.SIGTERM)
    deadline = time.monotonic() + 0.75
    while time.monotonic() < deadline:
        snapshot = process_snapshot()
        _collect_owned(snapshot, owned, backend_pid)
        if not any(
            pid != anchor.pid and _same_process(snapshot.get(pid), record)
            for pid, record in owned.items()
        ):
            break
        time.sleep(0.05)
    _signal_owned(owned, backend_pid, signal.SIGKILL)
    while True:
        snapshot = process_snapshot()
        if not any(_same_process(snapshot.get(pid), record) for pid, record in owned.items()):
            anchor.wait(timeout=5)
            return
        time.sleep(0.05)


def _monitor_windows(backend_pid: int, lost: threading.Event) -> None:
    """Assign before readiness; closing the sole job handle kills all owned descendants."""
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t),
            ("maximum", ctypes.c_size_t), ("active", wintypes.DWORD),
            ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
            ("scheduling", wintypes.DWORD),
        ]

    class IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "reads", "writes", "other", "read_bytes", "write_bytes", "other_bytes"
        )]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimits), ("io", IOCounters),
            ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
            ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    process = kernel.OpenProcess(0x0100 | 0x0001 | 0x00100000, False, backend_pid)
    try:
        if not job or not process:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(job, process):
            raise ctypes.WinError(ctypes.get_last_error())
        print("owned", flush=True)
        while not lost.wait(0.05):
            if kernel.WaitForSingleObject(process, 0) == 0:
                break
    finally:
        if job:
            kernel.CloseHandle(job)
        if process:
            kernel.CloseHandle(process)


def monitor_main(backend_pid: int) -> None:
    lost = threading.Event()
    threading.Thread(target=_watch_eof, args=(sys.stdin.buffer, lost), daemon=True).start()
    if os.name == "nt":
        _monitor_windows(backend_pid, lost)
    else:
        _monitor_posix(backend_pid, lost)


def anchor_main() -> None:
    """Remain in the supervised group until killed or the independent monitor exits."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("anchored", flush=True)
    sys.stdin.buffer.read()


def start_owner_monitor() -> subprocess.Popen[str]:
    """Require an independent monitor handshake before admitting backend work."""
    command = (
        [sys.executable, "--owner-monitor", str(os.getpid())]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "tcad_agent.desktop.owner_monitor", str(os.getpid())]
    )
    environment = {
        key: value for key, value in os.environ.items()
        if key.upper() in {"PATH", "PYTHONPATH", "SYSTEMROOT", "WINDIR", "LANG", "LC_ALL"}
    }
    monitor = subprocess.Popen(
        command, stdin=sys.stdin.buffer, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, env=environment, process_group=0 if os.name != "nt" else None,
    )
    assert monitor.stdout is not None
    ready = monitor.stdout.readline()
    monitor.stdout.close()
    if ready.strip() != "owned":
        monitor.wait(timeout=5)
        raise RuntimeError("Desktop backend ownership supervision could not start")
    return monitor


if __name__ == "__main__":
    monitor_main(int(sys.argv[1]))
