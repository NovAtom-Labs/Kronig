import json
from pathlib import Path
from types import SimpleNamespace

import pytest
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


def test_preparation_binds_requested_display_units_to_portable_plan(tmp_path, valid_spec):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Inspect potential in millivolts",
            fields=(
                IntentField(path="display_units", value={"potential": "mV"}, origin="researcher"),
            ),
        ),
    )
    response = tools.prepare_experiment(valid_spec.model_dump(mode="json"), backend="devsim")
    assert response.status == "ok", response
    assert response.data["prepared"]["spec"]["display_units"] == {"potential": "mV"}


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


def test_preparation_refuses_invented_contact_area_and_can_retry_density_only(tmp_path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute terminal current density",
            selected_capabilities=("observable.terminal_current_density",),
        ),
    )
    payload = valid_spec_payload()
    for contact in payload["contacts"]:
        contact["area"] = "1 cm^2"
    response = tools.prepare_experiment(payload, backend="devsim")
    assert response.status == "refused"
    assert response.code == "scientific_input_authority_violation"
    assert {issue["path"] for issue in response.data["issues"]} == {
        "contacts.anode.area",
        "contacts.cathode.area",
    }
    assert response.data["repair_action"] == "remove_unconfirmed_area_and_retry"
    assert not (tmp_path / "experiments").exists()

    for contact in payload["contacts"]:
        del contact["area"]
    response = tools.prepare_experiment(payload, backend="devsim")
    assert response.status == "ok"
    assert all(contact["area"] is None for contact in response.data["prepared"]["spec"]["contacts"])


@pytest.mark.parametrize("origin", ["evidence", "platform_default"])
def test_preparation_cannot_authorize_area_from_nonresearcher_sources(tmp_path, origin):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    evidence = {"rationale": "A published example uses this area", "evidence_refs": ("paper",)}
    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute current density",
            fields=(
                IntentField(
                    path="contacts.area",
                    value="1 cm^2",
                    origin=origin,
                    **(evidence if origin == "evidence" else {}),
                ),
            ),
        ),
    )
    payload = valid_spec_payload()
    payload["contacts"][0]["area"] = "1 cm^2"
    assert tools.prepare_experiment(payload, backend="devsim").code == (
        "scientific_input_authority_violation"
    )


@pytest.mark.parametrize("supplied", ["2 cm^2", "1 cm", 1, None])
def test_preparation_cannot_replace_confirmed_area_with_different_quantity(tmp_path, supplied):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute current density",
            fields=(IntentField(path="contacts.area", value=supplied, origin="researcher"),),
        ),
    )
    payload = valid_spec_payload()
    for contact in payload["contacts"]:
        contact["area"] = "1 cm^2"
    assert tools.prepare_experiment(payload, backend="devsim").code == (
        "scientific_input_authority_violation"
    )


def test_preparation_must_retain_confirmed_area_even_for_density_outputs(tmp_path):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute current density",
            fields=(IntentField(path="contacts.anode.area", value="1 cm^2", origin="researcher"),),
        ),
    )
    response = tools.prepare_experiment(valid_spec_payload(), backend="devsim")
    assert response.code == "scientific_input_authority_violation"


@pytest.mark.parametrize("origin", ["researcher", "repository"])
@pytest.mark.parametrize(
    "area_fields",
    [
        (("contacts.area", "1 cm^2"),),
        (("contacts.area", {"anode": "1 cm^2", "cathode": "1 cm^2"}),),
        (("contacts.anode.area", "1 cm^2"), ("contacts.cathode.area", "1 cm^2")),
        (
            (
                "contacts.area",
                {
                    "magnitude_si": 0.0001,
                    "si_unit": "meter ** 2",
                    "dimensionality": "[length] ** 2",
                },
            ),
        ),
    ],
)
def test_preparation_preserves_explicit_area_for_absolute_current(tmp_path, origin, area_fields):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    source = {"source_reference": "experiment.yaml"} if origin == "repository" else {}
    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute absolute terminal current",
            selected_capabilities=("observable.absolute_terminal_current",),
            fields=tuple(
                IntentField(path=path, value=value, origin=origin, **source)
                for path, value in area_fields
            ),
        ),
    )
    payload = valid_spec_payload()
    payload["observables"].append("absolute_terminal_current")
    for contact in payload["contacts"]:
        contact["area"] = "100 mm^2"
    response = tools.prepare_experiment(payload, backend="devsim")
    assert response.status == "ok"
    areas = [contact["area"] for contact in response.data["prepared"]["spec"]["contacts"]]
    assert (
        areas
        == [{"magnitude_si": 0.0001, "si_unit": "meter ** 2", "dimensionality": "[length] ** 2"}]
        * 2
    )


def test_preparation_keeps_role_mapped_areas_when_contact_labels_change(tmp_path):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute current density",
            fields=(
                IntentField(
                    path="contacts.area",
                    value={"left": "1 cm^2", "right": "2 cm^2"},
                    origin="researcher",
                ),
            ),
        ),
    )
    payload = valid_spec_payload()
    payload["contacts"][0].update(id="input_terminal", area="1 cm^2")
    payload["contacts"][1].update(id="return_terminal", area="2 cm^2")
    payload["study"]["contact"] = "input_terminal"
    assert tools.prepare_experiment(payload, backend="devsim").status == "ok"
    payload["contacts"][0]["area"] = "2 cm^2"
    payload["contacts"][1]["area"] = "1 cm^2"
    assert tools.prepare_experiment(payload, backend="devsim").code == (
        "scientific_input_authority_violation"
    )


def test_preparation_binds_area_to_explicit_boundary_location(tmp_path):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute current density",
            fields=(
                IntentField(path="contacts.injecting.location", value="x_min", origin="researcher"),
                IntentField(path="contacts.injecting.area", value="1 cm^2", origin="researcher"),
                IntentField(path="contacts.x_max.area", value="2 cm^2", origin="researcher"),
            ),
        ),
    )
    payload = valid_spec_payload()
    payload["contacts"][0]["area"] = "1 cm^2"
    payload["contacts"][1]["area"] = "2 cm^2"
    assert tools.prepare_experiment(payload, backend="devsim").status == "ok"


def test_preparation_cannot_copy_one_confirmed_terminal_area_to_another(tmp_path):
    from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute current density",
            fields=(IntentField(path="contacts.anode.area", value="1 cm^2", origin="researcher"),),
        ),
    )
    payload = valid_spec_payload()
    payload["contacts"][0]["area"] = "1 cm^2"
    assert tools.prepare_experiment(payload, backend="devsim").status == "ok"
    payload["contacts"][1]["area"] = "1 cm^2"
    response = tools.prepare_experiment(payload, backend="devsim")
    assert response.code == "scientific_input_authority_violation"
    assert response.data["issues"] == [
        {"path": "contacts.cathode.area", "reason": "unconfirmed_area"}
    ]


def test_direct_preparation_without_research_intent_accepts_typed_area(tmp_path):
    payload = valid_spec_payload()
    payload["observables"].append("absolute_terminal_current")
    for contact in payload["contacts"]:
        contact["area"] = "1 cm^2"
    assert DomainTools(tmp_path).prepare_experiment(payload, backend="devsim").status == "ok"


def test_prepared_tool_text_is_bounded_while_typed_evidence_is_complete(tmp_path, monkeypatch):
    from tcad_agent.agent.tools import ToolResponse

    executor = TcadDomainExecutor(tmp_path)
    prepared = {
        "plan_digest": "a" * 64,
        "backend": "devsim",
        "spec": {"name": "study"},
        "plan": {"native_mesh": "x" * 100000},
    }
    response = ToolResponse(
        status="ok",
        code="experiment_prepared",
        message="Ready",
        data={
            "prepared": prepared,
            "plan_artifacts": {"plan": "plan.md", "structured_plan": "plan.json"},
        },
    )
    monkeypatch.setattr(executor.tools, "prepare_experiment", lambda *a, **k: response)
    observation = executor(TcadDomainAction(operation="prepare_experiment", payload={}))
    text = observation.content[0].text
    assert len(text) < 50000
    assert "plan.json" in text and "a" * 64 in text
    assert observation.data["prepared"] == prepared


def test_requested_physics_model_cannot_be_silently_replaced(tmp_path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Fermi transport",
            selected_capabilities=("model.fermi",),
        ),
    )
    payload = valid_spec_payload()
    response = tools.prepare_experiment(payload, backend="devsim")
    assert response.code == "requested_scope_missing"
    assert "model.fermi" in response.data["missing_capabilities"]


def test_recorded_zero_bias_dc_point_satisfies_equilibrium_baseline(tmp_path):
    from tcad_agent.prompting.models import ResolvedResearchIntent

    tools = DomainTools(
        tmp_path,
        research_intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Baseline and biased profiles",
            selected_capabilities=("study.equilibrium", "study.dc_points"),
        ),
    )
    payload = valid_spec_payload()
    payload["study"] = {"kind": "dc_points", "contact": "anode", "values": ["0 V", "2 V", "-2 V"]}
    assert tools.prepare_experiment(payload, backend="devsim").status == "ok"
    payload["study"]["values"] = ["2 V", "-2 V"]
    assert tools.prepare_experiment(payload, backend="devsim").code == "requested_scope_missing"
    payload["study"]["values"] = ["0 V", "2 V", "-2 V"]
    payload["contacts"][1]["voltage_offset"] = "0.1 V"
    assert tools.prepare_experiment(payload, backend="devsim").code == "requested_scope_missing"


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


def test_prepare_experiment_preserves_original_request_in_artifacts(
    tmp_path: Path,
) -> None:
    original_request = (
        "Simulate a silicon diode at 300 K and sweep voltage from 0 V to 1 V."
    )
    tools = DomainTools(tmp_path, original_request=original_request)

    response = tools.prepare_experiment(valid_spec_payload(), backend="devsim")

    assert response.status == "ok"
    artifact_paths = response.data["plan_artifacts"]
    plan_json = Path(artifact_paths["structured_plan"])
    payload = json.loads(plan_json.read_text(encoding="utf-8"))

    import hashlib

    expected_hash = hashlib.sha256(original_request.encode("utf-8")).hexdigest()
    assert payload["original_request"]["text"] == original_request
    assert payload["original_request"]["sha256"] == expected_hash


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


def test_native_agent_execution_has_bounded_default_budget_and_honors_explicit_budget(
    tmp_path, monkeypatch
):
    from tcad_agent.experiments.errors import ExperimentExecutionError

    class RecordingEngine:
        def prepare(self, spec, backend, *, warnings=()):
            return ExperimentEngine().prepare(spec, backend, warnings=warnings)

        def execute(self, prepared, *, approved_plan_digest, output_root, budget, run_id=None):
            self.seconds = budget.seconds
            raise ExperimentExecutionError("recorded execution budget")

    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "app-data"))
    engine = RecordingEngine()
    tools = DomainTools(tmp_path, experiment_engine=engine)
    prepared = tools.prepare_experiment(valid_spec_payload(), backend="devsim").data["prepared"]
    request = {"prepared": prepared, "plan_digest": prepared["plan_digest"]}
    assert tools.execute_experiment(request).code == "experiment_execution_failed"
    # Refined nonlinear meshes must have a finite runtime allowance without
    # changing the requested equations or the scientific acceptance policy.
    assert engine.seconds == 1200
    assert (
        tools.execute_experiment({**request, "timeout_seconds": 30}).code
        == "experiment_execution_failed"
    )
    assert engine.seconds == 30


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


def test_ssh_audit_discovery_uses_the_opened_workspace_runtime(tmp_path, monkeypatch):
    from tcad_agent.runtime.paths import RuntimePaths

    monkeypatch.delenv("TCAD_WORKSPACE", raising=False)
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "managed"))
    workspace = tmp_path / "selected-repo"
    workspace.mkdir()
    audit_dir = RuntimePaths.from_workspace(workspace).bundle_root / "run-current" / "logs"
    audit_dir.mkdir(parents=True)
    (audit_dir / "ssh-audit.json").write_text(
        '{"schema_version": 1, "run_id": "remote-run", "events": []}', encoding="utf-8"
    )

    tools = build_tools(workspace)
    assert tools.read_ssh_audit().data["runs"][0]["bundle_run_id"] == "run-current"
    assert tools.read_ssh_audit("run-current").data["audit"]["run_id"] == "remote-run"


def test_llm_can_read_ssh_audit_from_experiment_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))
    bundle = tmp_path / "bundles" / "run-123" / "logs"
    bundle.mkdir(parents=True)
    (bundle / "ssh-audit.json").write_text(
        '{"schema_version": 1, "run_id": "ssh-run", "events": '
        '[{"action": "ssh.connect", "status": "succeeded"}]}',
        encoding="utf-8",
    )
    (bundle / "ssh-audit.log").write_text(
        "[SUCCEEDED] ssh.connect\n", encoding="utf-8"
    )

    response = build_tools(tmp_path).read_ssh_audit("run-123")

    assert response.status == "ok"
    assert response.code == "ssh_audit_read"
    audit = response.data["audit"]
    assert isinstance(audit, dict)
    assert audit["events"][0]["action"] == "ssh.connect"
    assert "ssh.connect" in response.data["text_log"]


def test_read_ssh_audit_rejects_path_traversal(tmp_path: Path) -> None:
    response = build_tools(tmp_path).read_ssh_audit("../outside")

    assert response.status == "refused"
    assert response.code == "invalid_run_id"


def test_read_ssh_audit_reports_missing_bundle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))

    response = build_tools(tmp_path).read_ssh_audit("missing-run")

    assert response.status == "refused"
    assert response.code == "ssh_audit_not_found"


def test_llm_domain_tool_dispatches_ssh_audit_read(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))
    audit_dir = tmp_path / "bundles" / "run-456" / "logs"
    audit_dir.mkdir(parents=True)
    (audit_dir / "ssh-audit.json").write_text(
        '{"schema_version": 1, "run_id": "ssh-run", "events": []}',
        encoding="utf-8",
    )
    (audit_dir / "ssh-audit.log").write_text("audit available\n", encoding="utf-8")

    observation = TcadDomainExecutor(tmp_path)(
        TcadDomainAction(
            operation="read_ssh_audit",
            payload={"run_id": "run-456"},
        )
    )

    assert observation.status == "ok"
    assert observation.code == "ssh_audit_read"
    assert '"events": []' in observation.text


def test_llm_can_discover_recent_ssh_audit_bundles(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))
    audit_dir = tmp_path / "bundles" / "run-discover" / "logs"
    audit_dir.mkdir(parents=True)
    (audit_dir / "ssh-audit.json").write_text(
        '{"schema_version": 1, "run_id": "ssh-run", "updated_at": '
        '"2026-10-13T00:00:00+00:00", "events": [{"action": "ssh.connect"}]}',
        encoding="utf-8",
    )

    response = build_tools(tmp_path).read_ssh_audit()

    assert response.status == "ok"
    assert response.code == "ssh_audit_index"
    assert response.data["runs"][0]["bundle_run_id"] == "run-discover"
