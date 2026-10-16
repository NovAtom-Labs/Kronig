"""Execution and cleanup may only address a single safe run identifier."""

import pytest

from tcad_agent.experiments.errors import ExperimentExecutionError
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.runners.models import RunBudget


@pytest.mark.parametrize("run_id", ["../protected", "absolute_fixture_path", "..", r"..\protected"])
def test_invalid_run_id_is_rejected_before_backend_admission(tmp_path, valid_spec, run_id):
    if run_id == "absolute_fixture_path":
        run_id = str(tmp_path / "absolute-fixture")
    root = tmp_path / "runs"
    protected = root / "protected"
    protected.mkdir(parents=True)
    marker = protected / "keep.txt"
    marker.write_text("researcher-owned fixture")
    admitted = []

    def forbidden_backend(name):
        admitted.append(name)
        raise RuntimeError("backend must not be reached")

    engine = ExperimentEngine(backend_resolver=forbidden_backend)
    prepared = engine.prepare(valid_spec, "devsim")
    with pytest.raises(ValueError, match="run ID"):
        engine.execute(
            prepared,
            approved_plan_digest=prepared.plan_digest,
            output_root=root,
            budget=RunBudget(seconds=1),
            run_id=run_id,
        )
    assert not admitted
    assert marker.read_text() == "researcher-owned fixture"


@pytest.mark.parametrize(
    "occupied", [".work/run-occupied", ".run-occupied.staging", "run-occupied"]
)
def test_duplicate_run_never_cleans_an_existing_owners_files(tmp_path, valid_spec, occupied):
    root = tmp_path / "runs"
    owned = root / occupied
    owned.mkdir(parents=True)
    marker = owned / "keep.txt"
    marker.write_text("another execution owns this")
    admitted = []

    def forbidden_backend(name):
        admitted.append(name)
        raise RuntimeError("backend must not be reached")

    engine = ExperimentEngine(backend_resolver=forbidden_backend)
    prepared = engine.prepare(valid_spec, "devsim")
    with pytest.raises(ExperimentExecutionError, match="already"):
        engine.execute(
            prepared,
            approved_plan_digest=prepared.plan_digest,
            output_root=root,
            budget=RunBudget(seconds=1),
            run_id="run-occupied",
        )
    assert not admitted
    assert marker.read_text() == "another execution owns this"
