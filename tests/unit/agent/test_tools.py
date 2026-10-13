import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from tcad_agent.agent.tools import (
    DomainTools,
    TcadDomainAction,
    TcadDomainExecutor,
    TcadDomainTool,
    build_tools,
)
from tcad_agent.bundles.models import ExperimentBundle
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.knowledge.models import Passage, WebEvidenceRecord, WebSearchResult
from tcad_agent.knowledge.retrieve import KnowledgeIndex

ROOT = Path(__file__).parents[3]


def test_agent_can_discover_and_reopen_verified_saved_results_without_chat(
    tmp_path, monkeypatch, result_bundle_factory
):
    from tcad_agent.runtime.paths import RuntimePaths

    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    result_bundle_factory(RuntimePaths.from_workspace(workspace).bundle_root)
    executor = TcadDomainExecutor(workspace)
    listing = executor(TcadDomainAction(operation="list_saved_results"))
    opened = executor(
        TcadDomainAction(operation="open_saved_result", payload={"run_id": "run-0001"})
    )

    assert listing.status == "ok"
    assert listing.data["entries"][0]["bundle_run_id"] == "run-0001"
    assert opened.code == "saved_result_opened"
    assert opened.data["bundle_run_id"] == "run-0001"
    assert opened.data["dataset_count"] > 0


def test_preparation_retains_confirmed_automatic_sampling(tmp_path):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Extract three representative points",
            fields=tuple(
                IntentField(path="profile_sampling." + key, value=value, origin="researcher")
                for key, value in (
                    ("mode", "automatic"),
                    ("method", "schedule_quantiles"),
                    ("sample_count", 3),
                )
            ),
        ),
    )
    payload = valid_spec_payload()
    assert tools.prepare_experiment(payload, backend="devsim").code == "requested_scope_missing"
    payload["profile_sampling"] = {
        "mode": "automatic",
        "method": "schedule_quantiles",
        "sample_count": 2,
    }
    assert tools.prepare_experiment(payload, backend="devsim").code == "requested_scope_missing"
    payload["profile_sampling"]["sample_count"] = 3
    assert tools.prepare_experiment(payload, backend="devsim").status == "ok"


def test_preparation_refuses_unrequested_automatic_sampling(tmp_path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation", objective="Use requested points"
        ),
    )
    payload = valid_spec_payload()
    payload["profile_sampling"] = {
        "mode": "automatic",
        "method": "schedule_quantiles",
        "sample_count": 3,
    }
    assert tools.prepare_experiment(payload, backend="devsim").code == "requested_scope_missing"


def valid_spec_payload() -> dict:
    return yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())


def test_frequency_equilibrium_baseline_satisfies_confirmed_zero_bias_scope(tmp_path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Solve equilibrium and linear response around it",
            selected_capabilities=("study.equilibrium", "study.frequency"),
        ),
    )
    payload = valid_spec_payload()
    payload["study"] = {
        "kind": "frequency",
        "contact": payload["contacts"][0]["id"],
        "start": "1 kHz",
        "stop": "1 MHz",
        "points": 7,
        "amplitude": "10 mV",
        "spacing": "log",
    }
    response = tools.prepare_experiment(payload, backend="devsim")
    assert response.status == "ok"


def test_biased_small_signal_plan_cannot_claim_an_unrecorded_equilibrium_point(tmp_path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Separate equilibrium and biased response",
            selected_capabilities=("study.equilibrium", "study.ac"),
        ),
    )
    payload = valid_spec_payload()
    contact = payload["contacts"][0]["id"]
    payload["study"] = {
        "kind": "ac",
        "contact": contact,
        "frequency": "1 MHz",
        "amplitude": "10 mV",
        "bias_schedule": {"kind": "dc_points", "contact": contact, "values": ["0.2 V"]},
    }
    assert tools.prepare_experiment(payload, backend="devsim").code == "requested_scope_missing"


def test_requested_legacy_current_alias_matches_normalized_density(tmp_path: Path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Check zero terminal current density",
            selected_capabilities=("observable.terminal_current",),
        ),
    )
    response = tools.prepare_experiment(valid_spec_payload(), backend="devsim")
    assert response.code != "requested_scope_missing"
    assert response.status == "ok"


def test_preparation_cannot_drop_a_confirmed_study(tmp_path: Path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Measure small-signal response over bias",
            selected_capabilities=("study.ac", "study.dc"),
        ),
    )
    response = tools.prepare_experiment(valid_spec_payload(), backend="devsim")
    assert response.status == "refused"
    assert response.code == "requested_scope_missing"
    assert "study.ac" in response.data["missing_capabilities"]


def test_preparation_cannot_drop_explicit_profile_sampling(tmp_path: Path):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Extract profiles at zero bias",
            fields=(
                IntentField(
                    path="profile_sampling.bias_values", value=["0 V"], origin="researcher"
                ),
            ),
        ),
    )
    response = tools.prepare_experiment(valid_spec_payload(), backend="devsim")
    assert response.status == "refused"
    assert response.code == "requested_scope_missing"


def test_prepare_experiment_returns_typed_plan(tmp_path: Path) -> None:
    tools = build_tools(tmp_path)
    response = tools.prepare_experiment(valid_spec_payload(), backend="devsim")

    assert response.status == "ok"
    assert response.code == "experiment_prepared"
    prepared = response.data["prepared"]
    assert prepared["backend"] == "devsim"
    assert len(prepared["plan_digest"]) == 64
    assert prepared["spec"]["schema_version"] == "1.0"


def test_invalid_dimensional_input_returns_json_serializable_tool_error(
    tmp_path: Path,
) -> None:
    payload = valid_spec_payload()
    payload["regions"][0]["x0"] = 0.0

    response = build_tools(tmp_path).prepare_experiment(payload, backend="devsim")

    assert response.status == "refused"
    assert response.code == "invalid_spec"
    encoded = response.model_dump_json()
    assert json.loads(encoded)["data"]["errors"]
    assert response.data["schema_operation"] == "describe_spec"


def test_describe_spec_returns_the_authoritative_experiment_contract(
    tmp_path: Path,
) -> None:
    response = build_tools(tmp_path).describe_spec()

    assert response.status == "ok"
    assert response.code == "experiment_spec_schema"
    schema = response.data["schema"]
    assert schema["title"] == "ExperimentSpec"
    assert "regions" in schema["properties"]
    assert "study" in schema["properties"]
    assert response.data["usage"]["payload_shape"] == "direct ExperimentSpec object"


def test_typed_bundle_inspection_returns_bounded_canonical_summary(
    tmp_path: Path,
    monkeypatch,
    result_bundle_factory,
) -> None:
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "app-data"))
    workspace = tmp_path / "project"
    workspace.mkdir()
    tools = DomainTools(workspace)
    from tcad_agent.runtime.paths import RuntimePaths

    root = RuntimePaths.from_workspace(workspace).bundle_root
    result_bundle_factory(root)

    response = tools.inspect_bundle("run-0001")

    assert response.status == "ok"
    assert response.code == "bundle_inspected"
    assert response.data["run_id"] == "run-0001"
    assert response.data["dataset_count"] > 0
    assert "values" not in response.data["datasets"][0]
    assert response.data["validation"]["failed_count"] == 0


def test_sentaurus_prepares_without_configured_remote(tmp_path: Path) -> None:
    response = build_tools(tmp_path).prepare_experiment(valid_spec_payload(), backend="sentaurus")
    assert response.status == "ok"
    assert response.code == "experiment_prepared"
    assert response.data["prepared"]["backend"] == "sentaurus"


def test_execute_experiment_keeps_runtime_bundle_outside_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    class RecordingEngine:
        def __init__(self) -> None:
            self.delegate = ExperimentEngine()
            self.output_root: Path | None = None

        def prepare(self, spec, backend, *, warnings=()):
            return self.delegate.prepare(spec, backend, warnings=warnings)

        def execute(
            self,
            prepared,
            *,
            approved_plan_digest,
            output_root,
            budget,
            run_id=None,
        ):
            del approved_plan_digest, budget, run_id
            self.output_root = output_root
            root = output_root / "run-recorded"
            (root / "results").mkdir(parents=True)
            (root / "validation").mkdir()
            (root / "results" / "canonical.json").write_text('{"status":"completed"}\n')
            (root / "validation" / "report.json").write_text('{"overall":"passed"}\n')
            (root / "report.md").write_text("# Report\n")
            (root / "traceability.json").write_text('{"records":[]}\n')
            return ExperimentBundle(run_id="run-recorded", state="completed", root=root)

    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "app-data"))
    workspace = tmp_path / "selected-project"
    workspace.mkdir()
    engine = RecordingEngine()
    tools = DomainTools(workspace, experiment_engine=engine)
    prepared = tools.prepare_experiment(valid_spec_payload(), backend="devsim").data["prepared"]

    response = tools.execute_experiment(
        {
            "prepared": prepared,
            "plan_digest": prepared["plan_digest"],
            "timeout_seconds": 30,
            "output_root": "/tmp/model-controlled-output",
        }
    )

    assert response.status == "ok"
    assert response.code == "experiment_executed"
    assert engine.output_root is not None
    assert engine.output_root.is_relative_to((tmp_path / "app-data").resolve())
    assert not (workspace / "runs").exists()
    assert response.data["experiment"]["project_root"].startswith(
        str(workspace.resolve() / "experiments")
    )
    assert "root" not in response.data["bundle"]
    assert response.data["bundle"]["execution_state"] == "completed"
    assert response.data["bundle"]["validation_state"] == "passed"


def test_execute_approved_plan_loads_exact_repository_artifact_by_digest(
    tmp_path: Path, monkeypatch
) -> None:
    class RecordingEngine:
        def __init__(self) -> None:
            self.delegate = ExperimentEngine()
            self.executed_digest: str | None = None

        def prepare(self, spec, backend, *, warnings=()):
            return self.delegate.prepare(spec, backend, warnings=warnings)

        def execute(
            self,
            prepared,
            *,
            approved_plan_digest,
            output_root,
            budget,
            run_id=None,
        ):
            del budget, run_id
            self.executed_digest = approved_plan_digest
            root = output_root / "run-approved"
            (root / "results").mkdir(parents=True)
            (root / "validation").mkdir()
            (root / "results" / "canonical.json").write_text('{"status":"completed"}\n')
            (root / "validation" / "report.json").write_text('{"overall":"passed"}\n')
            (root / "report.md").write_text("# Report\n")
            (root / "traceability.json").write_text('{"records":[]}\n')
            return ExperimentBundle(run_id="run-approved", state="completed", root=root)

    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "app-data"))
    workspace = tmp_path / "selected-project"
    workspace.mkdir()
    engine = RecordingEngine()
    tools = DomainTools(workspace, experiment_engine=engine)
    preparation = tools.prepare_experiment(valid_spec_payload(), backend="devsim")
    prepared = preparation.data["prepared"]

    response = tools.execute_approved_plan(
        {
            "approved_plan_digest": prepared["plan_digest"],
            "structured_plan_path": preparation.data["plan_artifacts"]["structured_plan"],
            "timeout_seconds": 30,
        }
    )

    assert response.status == "ok"
    assert response.code == "experiment_executed"
    assert engine.executed_digest == prepared["plan_digest"]


def test_execute_approved_plan_refuses_unknown_digest(tmp_path: Path) -> None:
    workspace = tmp_path / "selected-project"
    workspace.mkdir()

    response = DomainTools(workspace).execute_approved_plan(
        {
            "approved_plan_digest": "a" * 64,
            "structured_plan_path": "experiments/missing/plan.json",
        }
    )

    assert response.status == "refused"
    assert response.code == "approved_plan_not_found"


def test_tcad_executor_returns_llm_visible_refusal_for_missing_payload(
    tmp_path: Path,
) -> None:
    observation = TcadDomainExecutor(tmp_path)(TcadDomainAction(operation="validate_spec"))

    assert observation.status == "refused"
    assert observation.code == "invalid_spec"
    assert observation.content
    assert '"code": "invalid_spec"' in observation.text


def test_search_knowledge_uses_configured_product_index_not_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    index_path = tmp_path / "product" / "knowledge.sqlite3"
    KnowledgeIndex.build(
        index_path,
        [
            Passage.create(
                id="manual:contact",
                source_id="manual",
                title="DEVSIM manual",
                url="https://devsim.net/",
                license="CC-BY-ND-4.0",
                access="public",
                trust="primary",
                backend="devsim",
                version="2.9",
                reviewed=True,
                content="The contact_equation command assembles a boundary equation.",
            )
        ],
    )
    monkeypatch.setenv("TCAD_KNOWLEDGE_INDEX", str(index_path))

    response = build_tools(tmp_path / "empty-research-repository").search_knowledge(
        "contact equation", {"backend": "devsim"}
    )

    assert response.status == "ok"
    assert response.data["hits"]
    assert response.data["hits"][0]["citation"]["source_id"] == "manual"


class StubWebResearch:
    def search(
        self, query: str, preferred_domains: tuple[str, ...], limit: int
    ) -> tuple[WebSearchResult, ...]:
        assert query == "DEVSIM contact equation"
        assert preferred_domains == ("devsim.org",)
        assert limit == 3
        return (
            WebSearchResult(
                query=query,
                title="DEVSIM documentation",
                url="https://devsim.org/docs",
                snippet="Official command documentation",
                authority="primary",
            ),
        )

    def fetch_source(
        self,
        url: str,
        *,
        query: str = "",
        backend: str | None = None,
        version: str | None = None,
    ) -> WebEvidenceRecord:
        assert url == "https://devsim.org/docs"
        return WebEvidenceRecord.create(
            title="DEVSIM documentation",
            url=url,
            content_type="text/html",
            content="The solve command executes the configured equations.",
            query=query,
            authority="primary",
            backend=backend,
            version=version,
            from_cache=False,
        )


def test_tcad_tools_expose_structured_web_search_and_source_fetch(
    tmp_path: Path,
) -> None:
    tools = DomainTools(tmp_path, web_research=StubWebResearch())

    searched = tools.search_web("DEVSIM contact equation", ("devsim.org",), limit=3)
    fetched = tools.fetch_source(
        "https://devsim.org/docs",
        query="DEVSIM solve command",
        backend="devsim",
        version="2.9.1",
    )

    assert searched.status == "ok"
    assert searched.data["results"][0]["authority"] == "primary"
    assert fetched.status == "ok"
    assert fetched.data["evidence"]["backend"] == "devsim"
    assert fetched.data["evidence"]["content_hash"]
    assert fetched.data["evidence"]["untrusted_content"] is True


def test_tcad_domain_tool_declares_external_research_capability(
    tmp_path: Path,
) -> None:
    tool = TcadDomainTool.create(
        SimpleNamespace(workspace=SimpleNamespace(working_dir=str(tmp_path)))
    )[0]

    assert tool.annotations.openWorldHint is True
