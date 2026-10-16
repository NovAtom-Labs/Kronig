"""Run-local cooperative cancellation and bounded owned-process cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar


class ExecutionCancelled(RuntimeError):
    """The caller stopped execution before result publication."""


_cancelled: ContextVar[Callable[[], bool]] = ContextVar(
    "simulation_cancelled", default=lambda: False
)


@contextmanager
def cancellation_scope(check: Callable[[], bool]) -> Iterator[None]:
    previous = _cancelled.get()
    token = _cancelled.set(lambda: previous() or check())
    try:
        raise_if_cancelled()
        yield
    finally:
        _cancelled.reset(token)


def raise_if_cancelled() -> None:
    if _cancelled.get()():
        raise ExecutionCancelled("Simulation cancelled before result publication.")


def _terminate(process: subprocess.Popen[str], *, owns_group: bool) -> None:
    def send(signum: int) -> None:
        try:
            if owns_group:
                os.killpg(process.pid, signum)
            elif process.poll() is None:
                if signum == signal.SIGTERM:
                    process.terminate()
                else:
                    process.kill()
        except ProcessLookupError:
            pass

    send(signal.SIGTERM)
    try:
        process.wait(timeout=0.75)
    except subprocess.TimeoutExpired:
        pass
    # Also reap group members that outlived a parent which handled SIGTERM.
    send(signal.SIGKILL if os.name != "nt" else signal.SIGTERM)
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def wait_for_process(process: subprocess.Popen[str], seconds: float, *, owns_group: bool) -> int:
    deadline = time.monotonic() + seconds
    try:
        while True:
            raise_if_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, seconds)
            try:
                code = process.wait(timeout=min(0.1, remaining))
                raise_if_cancelled()
                return code
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        _terminate(process, owns_group=owns_group)
        raise
