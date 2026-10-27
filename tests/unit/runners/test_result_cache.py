from pathlib import Path

from tcad_agent.runners.cache import CachingRunner
from tcad_agent.runners.models import CompiledJob, NativeRunResult, RunBudget


class _Counting:
    def __init__(self, status="completed"):
        self.calls = 0
        self.status = status

    def run(self, job, budget):
        self.calls += 1
        out = job.entrypoint.parent / "ssh-result" / f"run{id(self)}-{self.calls}"
        out.mkdir(parents=True)
        for name, text in (("stdout.log", "o"), ("stderr.log", ""), ("sentaurus-result.json", "{}")):
            (out / name).write_text(text)
        return NativeRunResult(
            backend="sentaurus", status=self.status, return_code=0,
            stdout_path=out / "stdout.log", stderr_path=out / "stderr.log",
            result_path=out / "sentaurus-result.json", elapsed_seconds=12.0,
        )


def _job(tmp_path: Path, digest="a" * 16) -> CompiledJob:
    entry = tmp_path / "job" / "sdevice.cmd"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("x")
    return CompiledJob(
        backend="sentaurus", entrypoint=entry, input_files=(entry,),
        input_digest=digest, runtime_digest="b" * 16, compiler_version="t",
    )


def test_an_identical_completed_job_is_replayed_without_running_again(tmp_path):
    inner = _Counting()
    runner = CachingRunner(inner, tmp_path / "cache")
    first = runner.run(_job(tmp_path), RunBudget(seconds=60))
    second = runner.run(_job(tmp_path), RunBudget(seconds=60))
    assert inner.calls == 1
    assert second.status == "completed" and second.elapsed_seconds == 0.0
    assert second.result_path.read_text() == first.result_path.read_text()
    assert second.result_path != first.result_path


def test_a_different_input_or_a_failed_run_is_never_replayed(tmp_path):
    inner = _Counting()
    runner = CachingRunner(inner, tmp_path / "cache")
    runner.run(_job(tmp_path, "a" * 16), RunBudget(seconds=60))
    runner.run(_job(tmp_path, "c" * 16), RunBudget(seconds=60))
    assert inner.calls == 2
    failing = _Counting(status="execution_failed")
    again = CachingRunner(failing, tmp_path / "cache2")
    again.run(_job(tmp_path, "d" * 16), RunBudget(seconds=60))
    again.run(_job(tmp_path, "d" * 16), RunBudget(seconds=60))
    assert failing.calls == 2
