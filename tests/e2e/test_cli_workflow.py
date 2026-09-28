import json
from types import SimpleNamespace

from typer.testing import CliRunner

import tcad_agent.cli as cli_module
from tcad_agent.bundles.models import ExperimentBundle
from tcad_agent.cli import app

runner = CliRunner()


def test_cli_run_delegates_to_shared_experiment_engine(tmp_path, monkeypatch) -> None:
    calls: dict[str, object] = {}

    class RecordingEngine:
        def prepare(self, spec, backend):
            calls["prepared"] = (spec, backend)
            return SimpleNamespace(plan_digest="a" * 64)

        def execute(
            self,
            prepared,
            *,
            approved_plan_digest,
            output_root,
            budget,
            run_id=None,
        ):
            calls["executed"] = {
                "prepared": prepared,
                "approved_plan_digest": approved_plan_digest,
                "output_root": output_root,
                "budget": budget,
                "run_id": run_id,
            }
            return ExperimentBundle(
                run_id="run-cli-test",
                state="completed",
                root=output_root / "run-cli-test",
            )

    monkeypatch.setattr(cli_module, "ExperimentEngine", RecordingEngine, raising=False)

    result = runner.invoke(
        app,
        [
            "run",
            "examples/pn-junction.yaml",
            "--backend",
            "devsim",
            "--approve",
            "--output",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["prepared"][1] == "devsim"
    assert calls["executed"]["approved_plan_digest"] == "a" * 64
    assert calls["executed"]["output_root"] == tmp_path
    assert str(tmp_path / "run-cli-test") in result.output


def test_cli_run_still_requires_explicit_approval() -> None:
    result = runner.invoke(app, ["run", "examples/pn-junction.yaml"])

    assert result.exit_code == 2
    assert "execution requires --approve" in result.output


def test_cli_does_not_expose_standalone_browser_mode() -> None:
    help_result = runner.invoke(app, ["--help"])
    serve_result = runner.invoke(app, ["serve"])

    assert help_result.exit_code == 0
    assert "serve" not in help_result.stdout
    assert serve_result.exit_code != 0


def test_cli_runs_example_to_completed_bundle(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "examples/pn-junction.yaml",
            "--backend",
            "devsim",
            "--approve",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    manifest_path = next(tmp_path.glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    assert manifest["state"] == "completed"
    assert (manifest_path.parent / "report.md").is_file()


def test_cli_builds_and_searches_authorized_knowledge_index(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manual.md").write_text("Ohmic contact boundary conditions for DEVSIM.")
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(
        """schema_version: \"1.0\"
sources:
  - id: local-devsim
    title: Local DEVSIM corpus
    url: https://example.invalid/devsim
    license: Apache-2.0
    access: public
    trust: primary
    backend: devsim
    version: \"2.9.1\"
    reviewed: true
    local_path: corpus
"""
    )
    index = tmp_path / "knowledge.sqlite3"

    built = runner.invoke(
        app,
        [
            "knowledge",
            "build",
            "--manifest",
            str(manifest),
            "--root",
            str(tmp_path),
            "--index",
            str(index),
        ],
    )
    assert built.exit_code == 0, built.output
    searched = runner.invoke(
        app,
        [
            "knowledge",
            "search",
            "ohmic contact",
            "--index",
            str(index),
            "--backend",
            "devsim",
        ],
    )
    assert searched.exit_code == 0, searched.output
    assert "local-devsim" in searched.output


def test_cli_refuses_malformed_knowledge_manifest(tmp_path) -> None:
    manifest = tmp_path / "sources.yaml"
    manifest.write_text("[]\n")

    result = runner.invoke(
        app,
        [
            "knowledge",
            "build",
            "--manifest",
            str(manifest),
            "--root",
            str(tmp_path),
            "--index",
            str(tmp_path / "knowledge.sqlite3"),
        ],
    )

    assert result.exit_code == 2
    assert "knowledge build failed" in result.output


def test_cli_shows_user_copyable_agent_evaluation_prompt() -> None:
    result = runner.invoke(
        app,
        ["evaluation", "show", "metal-silicon-junction-equilibrium"],
    )

    assert result.exit_code == 0, result.output
    assert "Equilibrium Al / p-Si / n-Si / Al" in result.output
    assert "both contacts maintained at 0 V" in result.output


def test_cli_compiles_sentaurus_deck_without_licensed_runner(tmp_path) -> None:
    output = tmp_path / "sentaurus"
    result = runner.invoke(
        app,
        [
            "compile",
            "examples/al-pn-al-equilibrium.yaml",
            "--backend",
            "sentaurus",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (output / "sdevice.cmd").is_file()


def test_cli_reports_unconfigured_sentaurus_runner_without_traceback(tmp_path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "examples/al-pn-al-equilibrium.yaml",
            "--backend",
            "sentaurus",
            "--approve",
            "--output",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "Sentaurus runner requires" in result.output
    assert "Traceback" not in result.output
