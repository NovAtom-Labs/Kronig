"""The real compiler output must pass the packaged worker's integrity boundary."""

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.desktop.devsim_runner import execute_manifest, write_compiled_job_manifest
from tcad_agent.runners.models import RunBudget


def test_current_compiler_job_is_accepted_by_installed_sidecar(tmp_path, valid_spec):
    job = DevsimAdapter.from_defaults().compile(valid_spec, tmp_path / "compiled")
    manifest = write_compiled_job_manifest(job, RunBudget(seconds=5))
    invoked = []
    assert execute_manifest(manifest, runtime_main=lambda: invoked.append(True) or 0) == 0
    assert invoked == [True]


@pytest.mark.parametrize("helper", ["devsim_statistics.py", "devsim_density_solver.py"])
def test_sidecar_rejects_tampered_native_helper(tmp_path, valid_spec, helper):
    job = DevsimAdapter.from_defaults().compile(valid_spec, tmp_path / "compiled")
    manifest = write_compiled_job_manifest(job, RunBudget(seconds=5))
    candidate = job.entrypoint.parent / helper
    candidate.write_text(candidate.read_text() + "\n# changed after compilation\n")
    with pytest.raises(ValueError, match=r"reviewed runtime|runtime does not match"):
        execute_manifest(manifest, runtime_main=lambda: pytest.fail("executed tampered runtime"))
