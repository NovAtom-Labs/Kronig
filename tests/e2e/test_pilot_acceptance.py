import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.sentaurus.compiler import SentaurusAdapter
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.events.ledger import EventLedger
from tcad_agent.experiments.errors import ExperimentExecutionError
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.runners.models import RunBudget


def test_same_simulator_neutral_contract_runs_devsim_and_compiles_sentaurus(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        yaml.safe_load(Path("examples/al-pn-al-equilibrium-devsim.yaml").read_text())
    )
    engine = ExperimentEngine()
    prepared = engine.prepare(spec, "devsim")
    completed = engine.execute(
        prepared,
        approved_plan_digest=prepared.plan_digest,
        output_root=tmp_path / "runs",
        budget=RunBudget(seconds=120),
    )

    manifest = json.loads((completed.root / "manifest.json").read_text())
    assert manifest["backend"] == "devsim"
    assert manifest["state"] == "completed"
    for name, record in manifest["artifacts"].items():
        assert hashlib.sha256((completed.root / name).read_bytes()).hexdigest() == record["sha256"]
    events = EventLedger(completed.root / "events.jsonl").verify()
    assert events[-1].kind == "completed"
    assert (completed.root / "results" / "canonical.json").is_file()
    assert (completed.root / "validation" / "report.json").is_file()

    sentaurus_job = SentaurusAdapter.from_defaults().compile(spec, tmp_path / "sentaurus-compile")
    assert sentaurus_job.backend == "sentaurus"
    assert (tmp_path / "sentaurus-compile" / "sdevice.cmd").is_file()


def test_full_sentaurus_example_compiles_without_a_licensed_machine(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        yaml.safe_load(Path("examples/al-pn-al-equilibrium.yaml").read_text())
    )
    job = SentaurusAdapter.from_defaults().compile(spec, tmp_path / "compiled")
    assert job.backend == "sentaurus"
    deck = job.entrypoint.read_text()
    assert "WorkFunction=4.1" in deck
    assert "Fermi" in deck
    assert "Recombination( SRH Auger )" in deck


def test_unconfigured_sentaurus_execution_is_a_bounded_engine_failure(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        yaml.safe_load(Path("examples/al-pn-al-equilibrium.yaml").read_text())
    )
    engine = ExperimentEngine()
    prepared = engine.prepare(spec, "sentaurus")

    with pytest.raises(ExperimentExecutionError, match="Sentaurus runner requires"):
        engine.execute(
            prepared,
            approved_plan_digest=prepared.plan_digest,
            output_root=tmp_path / "runs",
            budget=RunBudget(seconds=120),
        )
