import json
from pathlib import Path

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.projects import ExperimentProjector
from tcad_agent.experiments.service import ExperimentEngine


def test_projector_exposes_research_artifacts_without_runtime_internals(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
) -> None:
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    bundle = tmp_path / "app-data" / "bundles" / "run-1"
    (bundle / "results").mkdir(parents=True)
    (bundle / "validation").mkdir()
    (bundle / "results" / "canonical.json").write_text('{"status":"completed"}\n')
    (bundle / "validation" / "report.json").write_text('{"overall":"passed"}\n')
    (bundle / "report.md").write_text("# Scientific report\n")
    (bundle / "traceability.json").write_text('{"records":[]}\n')

    record = ExperimentProjector(tmp_path / "selected").project(
        prepared=prepared,
        run_id="run-1",
        bundle_root=bundle,
    )

    assert record.plan_path.name == "PLAN.md"
    assert record.report_path.name == "REPORT.md"
    assert record.result_path.name == "results.json"
    assert record.traceability_path.name == "traceability.json"
    assert json.loads(record.result_path.read_text())["status"] == "completed"
    assert not (tmp_path / "selected" / "runs").exists()
    assert not any(
        part in {"compiled", "native", "logs", ".work"}
        for path in record.project_root.rglob("*")
        for part in path.parts
    )
