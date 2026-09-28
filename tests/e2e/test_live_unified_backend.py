from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tcad_agent.agent.runtime import OpenHandsRuntimeFactory
from tcad_agent.agent.supervisor import AgentSupervisor
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import PermissionCategory, RunState, is_run_grantable
from tcad_agent.ide.results import WorkspaceResultReader
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import IDEServices

TERMINAL_STATES = {
    RunState.COMPLETED,
    RunState.FAILED,
    RunState.BLOCKED,
    RunState.CANCELLED,
}


def _require_live_bedrock(pytestconfig: pytest.Config) -> None:
    if not pytestconfig.getoption("--run-live-bedrock"):
        pytest.skip("pass --run-live-bedrock to call the configured Bedrock model")
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        pytest.skip("AWS_BEARER_TOKEN_BEDROCK is not configured")


def _services(root: Path) -> IDEServices:
    store = SqliteIDEStore(root / "runtime/ide.sqlite3")
    events = EventFeed(store)
    return IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )


def _run_live_prompt(
    repository: Path,
    runtime_root: Path,
    prompt: str,
) -> tuple[IDEServices, TestClient, dict[str, object]]:
    services = _services(runtime_root)
    supervisor = AgentSupervisor(
        services,
        OpenHandsRuntimeFactory(services.runtime_root),
    )
    web = TestClient(create_app(ide=services, agent_supervisor=supervisor))
    workspace = web.post("/api/workspaces", json={"path": str(repository)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    web.post(session_url)
    message = web.post(f"{session_url}/messages", json={"content": prompt}).json()
    started = web.post(f"{session_url}/runs", json={"message_id": message["id"]}).json()
    run_id = UUID(str(started["id"]))

    for _ in range(20):
        supervisor.join(run_id, timeout=30)
        run = services.store.get_run(run_id)
        if run.state in TERMINAL_STATES:
            break
        if run.state is RunState.RUNNING:
            continue
        assert run.state is RunState.WAITING_FOR_APPROVAL
        approvals = web.get(f"{session_url}/approvals").json()
        assert approvals, "waiting run must expose a pending approval"
        for approval in approvals:
            category = PermissionCategory(approval["permission_category"])
            endpoint = "approve-category" if is_run_grantable(category) else "approve"
            response = web.post(
                f"/api/approvals/{approval['id']}/{endpoint}",
                json={"expected_revision": approval["revision"]},
            )
            assert response.status_code == 200, response.text
    else:
        pytest.fail("live agent exceeded the bounded approval loop")

    assert services.store.get_run(run_id).state is RunState.COMPLETED
    messages = web.get(f"{session_url}/messages").json()
    assert messages[-1]["role"] == "assistant"
    return services, web, {"workspace": workspace, "message": messages[-1]}


@pytest.mark.live_bedrock
def test_live_model_runs_devsim_and_produces_a_verified_result_workbench_bundle(
    pytestconfig: pytest.Config,
    tmp_path: Path,
) -> None:
    _require_live_bedrock(pytestconfig)
    repository = tmp_path / "equilibrium-study"
    repository.mkdir()
    prompt = (
        "Model a one-dimensional silicon structure at 300 K with a 1 µm "
        "acceptor-doped region followed by a 1 µm donor-doped region. Use uniform "
        "concentrations of 1e17 cm⁻³ on both sides and ohmic contacts held at "
        "zero volts. Run an equilibrium DEVSIM calculation and validate the "
        "electrostatic potential, electric field, electron concentration, hole "
        "concentration, and terminal current."
    )

    _run_live_prompt(repository, tmp_path / "live-simulation", prompt)

    results = tuple(repository.glob("runs/*/results/canonical.json"))
    assert len(results) == 1
    relative = results[0].relative_to(repository).as_posix()
    view = WorkspaceResultReader().read(repository, relative)
    assert view.result.backend == "devsim"
    assert view.validation.overall == "passed"
    assert {
        "potential",
        "electric_field",
        "electron_density",
        "hole_density",
    }.issubset(view.result.fields)


@pytest.mark.live_bedrock
def test_live_model_reports_unsupported_physics_without_approximating_it(
    pytestconfig: pytest.Config,
    tmp_path: Path,
) -> None:
    _require_live_bedrock(pytestconfig)
    repository = tmp_path / "unsupported-study"
    repository.mkdir()
    outcome = _run_live_prompt(
        repository,
        tmp_path / "live-unsupported",
        (
            "Run a one-dimensional DEVSIM silicon junction using a hydrodynamic "
            "transport model. Do not substitute drift diffusion or remove any requested "
            "physics. Tell me clearly if the backend cannot represent it."
        ),
    )

    final_text = str(outcome[2]["message"]["content"]).lower()
    assert "unsupported" in final_text or "cannot" in final_text
    assert not tuple(repository.glob("runs/*/results/canonical.json"))


@pytest.mark.live_bedrock
def test_live_model_keeps_ordinary_repository_work_on_the_same_runtime(
    pytestconfig: pytest.Config,
    tmp_path: Path,
) -> None:
    _require_live_bedrock(pytestconfig)
    repository = tmp_path / "ordinary-repository-task"
    repository.mkdir()
    (repository / "README.md").write_text("# Laboratory notes\n")

    _run_live_prompt(
        repository,
        tmp_path / "live-repository",
        (
            "Add a short section named Validation checklist to README.md with three "
            "checkboxes for units, provenance, and numerical convergence. Do not run a "
            "simulation because this is only a documentation edit."
        ),
    )

    text = (repository / "README.md").read_text()
    assert "Validation checklist" in text
    assert "units" in text.lower()
    assert "provenance" in text.lower()
    assert "convergence" in text.lower()
    assert not (repository / "runs").exists()
