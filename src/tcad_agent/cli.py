"""Researcher-facing command line workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from tcad_agent.adapters.registry import BackendAdapterUnavailable, get_backend
from tcad_agent.bundles.reader import BundleIntegrityError
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.conformance.bundles import compare_verified_bundles
from tcad_agent.conformance.models import ComparisonStatus
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.errors import (
    ExperimentCapabilityError,
    ExperimentExecutionError,
)
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.knowledge.ingest import KnowledgeIngestor
from tcad_agent.knowledge.models import SourceManifest
from tcad_agent.knowledge.retrieve import KnowledgeIndex
from tcad_agent.runners.models import RunBudget

app = typer.Typer(help="Validate, compile, run, and report simulator-neutral TCAD studies.")
knowledge_app = typer.Typer(help="Search the authorized versioned TCAD knowledge index.")
evaluation_app = typer.Typer(help="Inspect versioned TCAD agent evaluation prompts.")
conformance_app = typer.Typer(help="Compare verified canonical backend evidence bundles.")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(evaluation_app, name="evaluation")
app.add_typer(conformance_app, name="conformance")

DEFAULT_COMPILED_OUTPUT = Path("compiled")
DEFAULT_RUN_OUTPUT = Path("runs")
DEFAULT_KNOWLEDGE_INDEX = Path("knowledge-sources/index/knowledge.sqlite3")
DEFAULT_AGENT_EVALUATIONS = Path("evaluations/agent/cases.yaml")
DEFAULT_CONFORMANCE_RULES = Path("evaluations/conformance/cases.yaml")


def _load_spec(path: Path) -> ExperimentSpec:
    try:
        payload = yaml.safe_load(path.read_text())
        return ExperimentSpec.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(f"invalid specification: {exc}", err=True)
        raise typer.Exit(2) from exc


def _require_backend(spec: ExperimentSpec, backend: str) -> CapabilityManifest:
    try:
        manifest = CapabilityManifest.from_backend(backend)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    decision = CapabilityService().check(spec, manifest)
    if decision.status is not CapabilityStatus.SUPPORTED:
        for issue in decision.issues:
            typer.echo(f"{issue.path}: {issue.message}", err=True)
        raise typer.Exit(2)
    return manifest


@app.command("validate")
def validate_command(spec_path: Path) -> None:
    """Validate a specification and print its normalized representation."""
    spec = _load_spec(spec_path)
    typer.echo(json.dumps(spec.normalized(), sort_keys=True, indent=2))


@app.command("compile")
def compile_command(
    spec_path: Path,
    backend: Annotated[str, typer.Option("--backend")] = "devsim",
    output: Annotated[Path, typer.Option("--output")] = DEFAULT_COMPILED_OUTPUT,
) -> None:
    """Compile a supported specification without executing it."""
    spec = _load_spec(spec_path)
    _require_backend(spec, backend)
    try:
        job = get_backend(backend).adapter.compile(spec, output)
    except BackendAdapterUnavailable as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(job.model_dump(mode="json"), sort_keys=True, indent=2))


@app.command("run")
def run_command(
    spec_path: Path,
    backend: Annotated[str, typer.Option("--backend")] = "devsim",
    approve: Annotated[bool, typer.Option("--approve")] = False,
    output: Annotated[Path, typer.Option("--output")] = DEFAULT_RUN_OUTPUT,
    timeout_seconds: Annotated[float, typer.Option("--timeout-seconds")] = 120.0,
) -> None:
    """Run an explicitly approved experiment and create an evidence bundle."""
    if not approve:
        typer.echo("execution requires --approve", err=True)
        raise typer.Exit(2)
    spec = _load_spec(spec_path)
    engine = ExperimentEngine()
    try:
        prepared = engine.prepare(spec, backend)
        bundle = engine.execute(
            prepared,
            approved_plan_digest=prepared.plan_digest,
            output_root=output,
            budget=RunBudget(seconds=timeout_seconds),
        )
    except (ExperimentCapabilityError, ExperimentExecutionError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(str(bundle.root))
    if bundle.state != "completed":
        raise typer.Exit(1)


@app.command("report")
def report_command(bundle: Path) -> None:
    """Print the deterministic Markdown report from a completed bundle."""
    report = bundle / "report.md"
    if not report.is_file():
        typer.echo(f"report not found: {report}", err=True)
        raise typer.Exit(2)
    typer.echo(report.read_text())


@conformance_app.command("compare")
def compare_conformance_command(
    devsim_bundle: Path,
    sentaurus_bundle: Path,
    case_id: Annotated[str, typer.Option("--case")],
    rules_path: Annotated[
        Path, typer.Option("--rules")
    ] = DEFAULT_CONFORMANCE_RULES,
    output: Annotated[Path | None, typer.Option("--output")] = None,
) -> None:
    """Compare hash-verified DEVSIM and licensed Sentaurus evidence bundles."""
    try:
        payload, status = compare_verified_bundles(
            devsim_bundle,
            sentaurus_bundle,
            rules_path=rules_path,
            case_id=case_id,
        )
    except (BundleIntegrityError, OSError, ValueError, yaml.YAMLError) as exc:
        typer.echo(f"conformance comparison failed: {exc}", err=True)
        raise typer.Exit(2) from exc
    rendered = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if output is None:
        typer.echo(rendered, nl=False)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered)
        typer.echo(str(output))
    if status is not ComparisonStatus.PASSED:
        raise typer.Exit(1)


@evaluation_app.command("show")
def show_evaluation_command(
    case_id: str,
    suite_path: Annotated[
        Path, typer.Option("--suite")
    ] = DEFAULT_AGENT_EVALUATIONS,
) -> None:
    """Print a user-copyable natural-language evaluation prompt."""
    from tcad_agent.evaluations.agent_cases import AgentEvaluationSuite

    try:
        prompt = AgentEvaluationSuite.from_file(suite_path).read_prompt(case_id)
    except (OSError, KeyError, ValidationError, yaml.YAMLError) as exc:
        typer.echo(f"evaluation load failed: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(prompt)


@knowledge_app.command("search")
def search_knowledge_command(
    query: str,
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_KNOWLEDGE_INDEX,
    backend: Annotated[str | None, typer.Option("--backend")] = None,
    version: Annotated[str | None, typer.Option("--version")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 5,
) -> None:
    """Search a prebuilt authorized knowledge index."""
    if not index.is_file():
        typer.echo(f"knowledge index not found: {index}", err=True)
        raise typer.Exit(2)
    filters = {
        key: value
        for key, value in {"backend": backend, "version": version}.items()
        if value is not None
    }
    hits = KnowledgeIndex(index).search(query, filters, limit)
    typer.echo(json.dumps([hit.model_dump(mode="json") for hit in hits], indent=2))


@knowledge_app.command("build")
def build_knowledge_command(
    manifest: Annotated[Path, typer.Option("--manifest")],
    root: Annotated[Path, typer.Option("--root")],
    index: Annotated[Path, typer.Option("--index")] = DEFAULT_KNOWLEDGE_INDEX,
    source_id: Annotated[str | None, typer.Option("--source-id")] = None,
) -> None:
    """Build an immutable lexical index from authorized local source entries."""
    try:
        document = yaml.safe_load(manifest.read_text())
        if not isinstance(document, dict) or not isinstance(document.get("sources"), list):
            raise ValueError("knowledge manifest must contain a sources list")
        sources = tuple(
            SourceManifest.model_validate(item) for item in document.get("sources", ())
        )
        selected = tuple(
            source
            for source in sources
            if source.local_path is not None
            and (source_id is None or source.id == source_id)
        )
        if not selected:
            raise ValueError("manifest contains no matching local knowledge source")
        ingestor = KnowledgeIngestor()
        passages = tuple(
            passage
            for source in selected
            for passage in ingestor.ingest_local(source, root)
        )
        KnowledgeIndex.build(index, passages)
    except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
        typer.echo(f"knowledge build failed: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"indexed {len(passages)} passages at {index}")


def main() -> None:
    """Load local environment configuration and launch the CLI."""
    load_dotenv()
    app()


if __name__ == "__main__":
    main()
