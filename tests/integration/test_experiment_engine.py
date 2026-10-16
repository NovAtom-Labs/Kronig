from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.events.ledger import EventLedger
from tcad_agent.experiments.errors import ExperimentExecutionError
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.ide.results import WorkspaceResultReader
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_engine_executes_real_devsim_and_writes_verified_bundle(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        yaml.safe_load((ROOT / "examples/al-pn-al-equilibrium-devsim.yaml").read_text())
    )
    engine = ExperimentEngine()
    prepared = engine.prepare(spec, "devsim")

    bundle = engine.execute(
        prepared,
        approved_plan_digest=prepared.plan_digest,
        output_root=tmp_path / "runs",
        budget=RunBudget(seconds=120),
        run_id="run-engine-real-devsim",
    )

    assert bundle.state == "completed"
    assert bundle.root == tmp_path / "runs/run-engine-real-devsim"
    manifest = json.loads((bundle.root / "manifest.json").read_text())
    assert manifest["backend"] == "devsim"
    assert manifest["state"] == "completed"
    for relative, record in manifest["artifacts"].items():
        artifact = bundle.root / relative
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record["sha256"]
    events = EventLedger(bundle.root / "events.jsonl").verify()
    assert events[-1].kind == "completed"
    view = WorkspaceResultReader().read(
        bundle.root.parent,
        f"{bundle.root.name}/results/canonical.json",
    )
    assert view.manifest.run_id == bundle.run_id
    assert view.validation.overall == "passed"
    assert view.result.metadata["mesh_verification"]["status"] == "passed"
    assert "verification/mesh/experiment.json" in manifest["artifacts"]
    assert "verification/mesh/provenance.json" in manifest["artifacts"]
    assert "verification/mesh/level-00/canonical.json" in manifest["artifacts"]
    assert "verification/mesh/level-00/compiled/input.json" in manifest["artifacts"]
    assert view.validation.checks_by_id["mesh-refinement-stability"].status == "passed"
    assert not (tmp_path / "runs/.work/run-engine-real-devsim").exists()


@pytest.mark.integration
def test_engine_cleans_staging_work_after_runner_failure(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        yaml.safe_load((ROOT / "examples/al-pn-al-equilibrium-devsim.yaml").read_text())
    )

    class FailingRunner:
        def run(self, _job, _budget):
            raise OSError("simulator transport unavailable")

    from tcad_agent.adapters.devsim.compiler import DevsimAdapter
    from tcad_agent.adapters.registry import BackendBinding

    engine = ExperimentEngine(
        backend_resolver=lambda _backend: BackendBinding(
            adapter=DevsimAdapter.from_defaults(),
            runner=FailingRunner(),
        )
    )
    prepared = engine.prepare(spec, "devsim")

    with pytest.raises(ExperimentExecutionError, match="Simulator execution failed"):
        engine.execute(
            prepared,
            approved_plan_digest=prepared.plan_digest,
            output_root=tmp_path / "runs",
            budget=RunBudget(seconds=30),
            run_id="run-engine-failure",
        )

    assert not (tmp_path / "runs/run-engine-failure").exists()
    assert not (tmp_path / "runs/.work/run-engine-failure").exists()
