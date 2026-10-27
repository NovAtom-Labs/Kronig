"""Replay of completed runs: an identical compiled input is never simulated twice.

A run is identified by the digest of its compiled inputs plus the runtime digest, so a hit is
exactly the job that produced the stored outputs. Only completed runs are stored; a failed or
timed-out run is always retried. Enabled by ``TCAD_RESULT_CACHE_DIR``; the directory is local
and holds the outputs the runner already keeps beside each job.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from tcad_agent.runners.models import CompiledJob, NativeRunResult, RunBudget

_DIGEST = re.compile(r"^[A-Za-z0-9._-]{8,200}$")
_PATHS = ("stdout_path", "stderr_path", "result_path", "audit_json_path", "audit_log_path")


class CachingRunner:
    def __init__(self, inner, root: Path) -> None:
        self._inner = inner
        self._root = Path(root)

    @classmethod
    def wrap(cls, inner):
        configured = os.getenv("TCAD_RESULT_CACHE_DIR")
        return cls(inner, Path(configured)) if configured else inner

    def _entry(self, job: CompiledJob) -> Path | None:
        key = f"{job.input_digest}-{job.runtime_digest}"
        return self._root / key if _DIGEST.match(key) else None

    def run(self, job: CompiledJob, budget: RunBudget) -> NativeRunResult:
        entry = self._entry(job)
        if entry is not None and (entry / "native.json").is_file():
            replayed = self._replay(entry, job)
            if replayed is not None:
                return replayed
        result = self._inner.run(job, budget)
        if entry is not None and result.status == "completed" and result.result_path is not None:
            self._store(entry, result)
        return result

    def _store(self, entry: Path, result: NativeRunResult) -> None:
        source = result.result_path.parent
        staging = entry.with_name(entry.name + f".{uuid4().hex}.tmp")
        try:
            payload = result.model_dump(mode="json")
            for name in _PATHS:
                path = getattr(result, name)
                payload[name] = path.relative_to(source).as_posix() if path is not None else None
            if not all(payload[name] for name in ("stdout_path", "stderr_path", "result_path")):
                return
            shutil.copytree(source, staging / "files")
            (staging / "native.json").write_text(json.dumps(payload), encoding="utf-8")
            if entry.exists():
                shutil.rmtree(entry)
            staging.rename(entry)
        except (OSError, ValueError):
            pass  # the cache is an optimisation; a failed store never fails the run
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def _replay(self, entry: Path, job: CompiledJob) -> NativeRunResult | None:
        try:
            payload = json.loads((entry / "native.json").read_text(encoding="utf-8"))
            destination = job.entrypoint.parent.resolve() / "ssh-result" / f"cached-{uuid4()}"
            shutil.copytree(entry / "files", destination)
            for name in _PATHS:
                value = payload.get(name)
                payload[name] = str(destination / value) if value else None
            payload["elapsed_seconds"] = 0.0
            return NativeRunResult.model_validate(payload)
        except (OSError, ValueError, KeyError):
            return None
