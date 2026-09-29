from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tcad_agent.agent.runtime import OpenHandsRuntimeFactory, llm_from_environment
from tcad_agent.agent.supervisor import AgentSupervisor
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import PermissionCategory, RunState, is_run_grantable
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.knowledge.retrieve import KnowledgeIndex
from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.context import (
    LocalEvidenceCollector,
    WorkspaceContextCollector,
    capability_hashes,
)
from tcad_agent.prompting.gateway import OpenHandsPreparationModel
from tcad_agent.prompting.models import ClarificationAnswer
from tcad_agent.prompting.service import PromptPreparationService
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import IDEServices

PROJECT_ROOT = Path(__file__).parents[2]
TERMINAL_STATES = {
    RunState.COMPLETED,
    RunState.FAILED,
    RunState.BLOCKED,
    RunState.CANCELLED,
}


def require_live(pytestconfig: pytest.Config) -> None:
    if not pytestconfig.getoption("--run-live-bedrock"):
        pytest.skip("pass --run-live-bedrock to call the configured Bedrock model")
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        pytest.skip("AWS_BEARER_TOKEN_BEDROCK is not configured")


def preparation(llm) -> PromptPreparationService:
    return PromptPreparationService(
        model=OpenHandsPreparationModel(llm),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(
            KnowledgeIndex(PROJECT_ROOT / "knowledge-sources/index/knowledge.sqlite3")
        ),
        compiler=PromptCompiler(),
        capability_hashes=capability_hashes(PROJECT_ROOT / "src/tcad_agent"),
    )


@pytest.mark.live_bedrock
def test_live_preprocessor_asks_and_compiles_without_inventing_inputs(
    pytestconfig: pytest.Config, tmp_path: Path
) -> None:
    require_live(pytestconfig)
    service = preparation(llm_from_environment())
    prompt = (
        "Investigate how the electric field changes across a silicon structure "
        "and run an appropriate TCAD simulation."
    )

    first = service.prepare(root=tmp_path, original_prompt=prompt, answers=())

    assert first.decision.status == "clarification"
    assert 1 <= len(first.decision.questions) <= 7
    assert first.compiled_request is None
    answers: list[ClarificationAnswer] = []
    for question in first.decision.questions:
        key = f"{question.id} {question.field_path}".lower()
        if "dop" in key:
            value = (
                "Use uniform boron at 1e17 cm^-3 in the p region and uniform "
                "phosphorus at 1e17 cm^-3 in the n region."
            )
        elif any(word in key for word in ("geometr", "dimension", "structure", "topology")):
            value = (
                "Use a one-dimensional abrupt silicon p-n junction. The p region "
                "is x = 0 to 1 um and the n region is x = 1 to 2 um."
            )
        elif any(word in key for word in ("bias", "boundar", "contact")):
            value = (
                "Use ohmic contacts at both ends held at 0 V and solve equilibrium "
                "only at 300 K."
            )
        elif any(word in key for word in ("field", "observ", "output", "deliver")):
            value = (
                "Extract electrostatic potential and electric field versus position, "
                "plus the peak field and built-in potential."
            )
        elif "physics" in key:
            value = (
                "Use the backend-supported self-consistent equilibrium equations and "
                "classical carrier statistics needed for the requested fields."
            )
        else:
            value = (
                "Use a one-dimensional abrupt silicon p-n junction at 300 K. The p "
                "region is x = 0 to 1 um with uniform boron at 1e17 cm^-3, the n "
                "region is x = 1 to 2 um with uniform phosphorus at 1e17 cm^-3, and "
                "both end contacts are ohmic at 0 V. Extract potential and electric "
                "field versus position, peak field, and built-in potential."
            )
        answers.append(
            ClarificationAnswer(question_id=question.id, answer=value)
        )

    second = service.prepare(
        root=tmp_path, original_prompt=prompt, answers=tuple(answers)
    )

    assert second.decision.status == "ready"
    assert second.compiled_request is not None
    assert second.compiled_request.original_sha256
    assert second.compiled_request.compiled_sha256


@pytest.mark.live_bedrock
def test_live_compiled_request_runs_devsim_and_opens_graphable_results(
    pytestconfig: pytest.Config, tmp_path: Path
) -> None:
    require_live(pytestconfig)
    repository = tmp_path / "prepared-equilibrium-study"
    repository.mkdir()
    store = SqliteIDEStore(tmp_path / "runtime/ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    llm = llm_from_environment()
    supervisor = AgentSupervisor(
        services,
        OpenHandsRuntimeFactory(services.runtime_root, llm=llm),
        preparation=preparation(llm),
    )
    web = TestClient(create_app(ide=services, agent_supervisor=supervisor))
    workspace = web.post("/api/workspaces", json={"path": str(repository)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    web.post(session_url)
    prompt = (
        "Create and run a one-dimensional equilibrium DEVSIM study of an abrupt "
        "silicon p-n junction at 300 K. The p region is x = 0 to 1 um with uniform "
        "boron doping of 1e17 cm^-3. The n region is x = 1 to 2 um with uniform "
        "phosphorus doping of 1e17 cm^-3. Use ohmic contacts at both ends held at "
        "0 V. Extract potential, electric field, electron density, hole density, "
        "and terminal current. Validate current balance and field consistency. Keep "
        "the generated files reproducible in this repository and do not commit or push."
    )
    message = web.post(f"{session_url}/messages", json={"content": prompt}).json()
    started = web.post(
        f"{session_url}/runs", json={"message_id": message["id"]}
    ).json()
    run_id = UUID(started["id"])

    clarification_batches = 0
    for _ in range(24):
        supervisor.join(run_id, timeout=30)
        run = store.get_run(run_id)
        if run.state in TERMINAL_STATES:
            break
        if run.state is RunState.WAITING_FOR_USER:
            clarification_batches += 1
            assert clarification_batches <= 2
            pending = web.get(f"/api/runs/{run_id}/preparation").json()
            answers = [
                {
                    "question_id": question["id"],
                    "answer": (
                        "Use a backend-supported expert choice that preserves the stated "
                        "geometry, doping, equilibrium conditions, and requested outputs. "
                        "Prefer the smallest robust option and omit unsupported extras."
                    ),
                }
                for question in pending["decision"]["questions"]
            ]
            response = web.post(
                f"/api/runs/{run_id}/clarifications",
                json={"expected_revision": pending["revision"], "answers": answers},
            )
            assert response.status_code == 202, response.text
            continue
        if run.state in {RunState.RUNNING, RunState.QUEUED}:
            continue
        assert run.state is RunState.WAITING_FOR_APPROVAL
        for approval in web.get(f"{session_url}/approvals").json():
            category = PermissionCategory(approval["permission_category"])
            endpoint = "approve-category" if is_run_grantable(category) else "approve"
            response = web.post(
                f"/api/approvals/{approval['id']}/{endpoint}",
                json={"expected_revision": approval["revision"]},
            )
            assert response.status_code == 200, response.text
    else:
        pytest.fail("prepared live run exceeded its bounded execution loop")

    assert store.get_run(run_id).state is RunState.COMPLETED
    preparation_record = store.get_prompt_preparation(run_id)
    assert preparation_record.compiled_request is not None
    results = tuple(repository.glob("runs/*/results/canonical.json"))
    assert len(results) == 1
    relative = results[0].relative_to(repository).as_posix()
    response = web.get(
        f"/api/workspaces/{workspace['id']}/results", params={"path": relative}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    graphable = {
        name
        for name, field in payload["result"]["fields"].items()
        if len(field.get("positions_m", [])) == len(field.get("values", [])) >= 2
    }
    assert {"potential", "electric_field"}.issubset(graphable)
    assert payload["validation"]["overall"] == "passed"
    assert payload["manifest"]["backend"] == "devsim"
