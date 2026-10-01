import platform
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from openhands.sdk.conversation import ConversationExecutionStatus
from openhands.sdk.event import ActionEvent, MessageEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.llm.message import MessageToolCall
from openhands.sdk.security import SecurityRisk
from openhands.tools.terminal.definition import TerminalAction

from tcad_agent.agent.supervisor import AgentSupervisor
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import RunState
from tcad_agent.ide.store import ConversationNotFoundError, SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.runtime.paths import RuntimePaths
from tcad_agent.web import ide_routes
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import IDEServices


def ide_client(tmp_path: Path) -> TestClient:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    return TestClient(create_app(ide=services))


class ApprovalConversation:
    def __init__(self, conversation_id: UUID, callback) -> None:
        self.id = conversation_id
        self.callback = callback
        self.state = SimpleNamespace(
            execution_status=ConversationExecutionStatus.IDLE
        )
        self.run_count = 0

    def send_message(self, message: str, sender: str | None = None) -> None:
        del message, sender

    def run(self) -> None:
        self.run_count += 1
        if self.run_count == 1:
            self.callback(
                ActionEvent(
                    thought=[],
                    action=TerminalAction(command="git push"),
                    tool_name="terminal",
                    tool_call_id="push-1",
                    tool_call=MessageToolCall(
                        id="push-1",
                        name="terminal",
                        arguments='{"command":"git push"}',
                        origin="completion",
                    ),
                    llm_response_id="response-1",
                    security_risk=SecurityRisk.LOW,
                )
            )
            self.state.execution_status = (
                ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
            )
            return
        self.callback(
            MessageEvent(
                source="agent",
                llm_message=Message(
                    role="assistant",
                    content=[TextContent(text="Push approved and task completed")],
                ),
            )
        )
        self.state.execution_status = ConversationExecutionStatus.FINISHED

    def pause(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.PAUSED

    def interrupt(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.PAUSED

    def reject_pending_actions(self, reason: str = "User rejected") -> None:
        del reason


class ApprovalRuntimeFactory:
    def create(self, workspace: Path, conversation_id: UUID, callback):
        assert workspace.is_dir()
        return ApprovalConversation(conversation_id, callback)


def test_agent_run_and_approval_api_lifecycle(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    supervisor = AgentSupervisor(services, ApprovalRuntimeFactory())
    web = TestClient(create_app(ide=services, agent_supervisor=supervisor))
    root = tmp_path / "repo"
    root.mkdir()
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    conversation = web.post(session_url).json()
    message = web.post(
        f"{session_url}/messages",
        json={"content": "Inspect, edit, test, and push only if I approve"},
    ).json()

    started = web.post(
        f"{session_url}/runs",
        json={"message_id": message["id"]},
    )
    assert started.status_code == 202
    run = started.json()
    supervisor.join(UUID(run["id"]), timeout=2)

    active = web.get(f"{session_url}/runs/active")
    approvals = web.get(f"{session_url}/approvals")
    duplicate = web.post(
        f"{session_url}/runs",
        json={"message_id": message["id"]},
    )

    assert active.status_code == 200
    assert active.json()["state"] == "waiting_for_approval"
    assert active.json()["conversation_id"] == conversation["id"]
    assert approvals.status_code == 200
    approval = approvals.json()[0]
    assert approval["payload"] == {"command": "git push"}
    assert approval["permission_category"] == "git_mutation"
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "agent_run_conflict"

    approved = web.post(
        f"/api/approvals/{approval['id']}/approve-category",
        json={"expected_revision": approval["revision"]},
    )
    assert approved.status_code == 200
    assert services.store.list_run_permission_grants(UUID(run["id"])) == (
        "git_mutation",
    )
    supervisor.join(UUID(run["id"]), timeout=2)

    messages = web.get(f"{session_url}/messages").json()
    stale = web.post(
        f"/api/approvals/{approval['id']}/approve-category",
        json={"expected_revision": approval["revision"]},
    )
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "Push approved and task completed"
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_revision"


def test_run_changes_endpoint_compares_against_starting_workspace(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    supervisor = AgentSupervisor(services, ApprovalRuntimeFactory())
    web = TestClient(create_app(ide=services, agent_supervisor=supervisor))
    root = tmp_path / "repo"
    root.mkdir()
    existing = root / "existing.txt"
    untouched = root / "untouched-dirty.txt"
    existing.write_text("already dirty\n")
    untouched.write_text("pre-existing\n")
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    conversation = web.post(session_url).json()
    message = web.post(
        f"{session_url}/messages",
        json={"content": "Inspect the repository"},
    ).json()

    started = web.post(
        f"{session_url}/runs",
        json={"message_id": message["id"]},
    )
    assert started.status_code == 202
    run = started.json()
    supervisor.join(UUID(run["id"]), timeout=2)
    events.append(
        UUID(conversation["id"]),
        "tool_call_started",
        {
            "run_id": run["id"],
            "action_id": "edit-existing",
            "tool_name": "file_editor",
            "phase": "edit",
            "arguments": {"command": "str_replace", "path": "existing.txt"},
        },
    )
    events.append(
        UUID(conversation["id"]),
        "tool_call_completed",
        {
            "run_id": run["id"],
            "action_id": "edit-existing",
            "tool_name": "file_editor",
            "is_error": False,
            "output": "updated",
        },
    )
    existing.write_text("already dirty\nagent line\n")
    approval = services.store.list_pending_approvals(UUID(conversation["id"]))[0]
    approved = web.post(
        f"/api/approvals/{approval.id}/approve-category",
        json={"expected_revision": approval.revision},
    )
    assert approved.status_code == 200
    supervisor.join(UUID(run["id"]), timeout=2)

    response = web.get(f"/api/runs/{run['id']}/changes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run["id"]
    assert [(row["path"], row["operation"]) for row in payload["files"]] == [
        ("existing.txt", "modified")
    ]
    assert payload["files"][0]["additions"] == 1
    assert payload["files"][0]["attributed_action_ids"] == ["edit-existing"]
    assert payload["files"][0]["attributed_tools"] == ["file_editor"]

    existing.write_text("later run state\n")
    restored = web.get(f"/api/runs/{run['id']}/changes").json()
    assert restored == payload


def test_run_changes_endpoint_handles_legacy_run_without_baseline(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    web = TestClient(create_app(ide=services))
    root = tmp_path / "repo"
    root.mkdir()
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    conversation = web.post(
        f"/api/workspaces/{workspace['id']}/session"
    ).json()
    run = store.create_run(UUID(conversation["id"]), uuid4())

    response = web.get(f"/api/runs/{run.id}/changes")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == str(run.id)
    assert payload["files"] == []
    assert payload["baseline_truncated"] is True
    assert "before change tracking was available" in payload["manifest_warning"]


def test_workspace_session_and_tree_api(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("# Research\n", encoding="utf-8", newline="\n")
    web = ide_client(tmp_path)

    opened = web.post("/api/workspaces", json={"path": str(root)})
    assert opened.status_code == 201
    workspace = opened.json()
    assert workspace["root"] == str(root.resolve())
    assert workspace["git"]["available"] is False

    entries = web.get(f"/api/workspaces/{workspace['id']}/entries")
    assert entries.json() == [
        {"path": "README.md", "name": "README.md", "kind": "file", "size": 11}
    ]

    session_url = f"/api/workspaces/{workspace['id']}/session"
    created = web.post(session_url)
    assert created.status_code == 200
    sent = web.post(
        f"{session_url}/messages",
        json={"content": "Find the simulation entrypoint"},
    )
    assert sent.status_code == 201
    assert sent.json()["role"] == "user"


def test_workspace_session_api_is_idempotent_and_conversation_routes_are_removed(
    tmp_path: Path,
) -> None:
    web = ide_client(tmp_path)
    root = tmp_path / "session-repository"
    root.mkdir()
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"

    first = web.post(session_url)
    second = web.post(session_url)
    message = web.post(
        f"{session_url}/messages", json={"content": "Inspect the repository"}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert message.status_code == 201
    assert web.get(f"{session_url}/messages").json()[0]["content"] == (
        "Inspect the repository"
    )
    removed_routes = (
        ("post", f"/api/workspaces/{workspace['id']}/conversations"),
        ("get", f"/api/workspaces/{workspace['id']}/conversations"),
        ("get", f"/api/conversations/{first.json()['id']}"),
        ("get", f"/api/conversations/{first.json()['id']}/messages"),
        ("post", f"/api/conversations/{first.json()['id']}/runs"),
        ("get", f"/api/conversations/{first.json()['id']}/approvals"),
        ("get", f"/api/conversations/{first.json()['id']}/events"),
    )
    for method, url in removed_routes:
        assert getattr(web, method)(url).status_code == 404


def test_workspace_session_switch_refuses_live_run_then_releases_terminal_state(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    web = TestClient(create_app(ide=services))
    first_root = tmp_path / "first-repository"
    second_root = tmp_path / "second-repository"
    first_root.mkdir()
    second_root.mkdir()
    first_workspace = web.post(
        "/api/workspaces", json={"path": str(first_root)}
    ).json()
    second_workspace = web.post(
        "/api/workspaces", json={"path": str(second_root)}
    ).json()
    first_url = f"/api/workspaces/{first_workspace['id']}/session"
    first_session = web.post(first_url).json()
    run = store.create_run(UUID(first_session["id"]), UUID(first_session["id"]))

    busy = web.post(f"/api/workspaces/{second_workspace['id']}/session")

    assert busy.status_code == 409
    assert busy.json()["code"] == "workspace_session_busy"
    terminal = store.transition_run(run.id, run.revision, RunState.COMPLETED)
    assert terminal.state is RunState.COMPLETED

    second = web.post(f"/api/workspaces/{second_workspace['id']}/session")

    assert second.status_code == 200
    assert second.json()["workspace_id"] == second_workspace["id"]
    second_url = f"/api/workspaces/{second_workspace['id']}/session"
    assert web.get(f"{second_url}/messages").json() == []
    assert web.get(f"{second_url}/runs/active").json() is None
    with pytest.raises(ConversationNotFoundError):
        store.get_conversation(UUID(first_session["id"]))
    assert web.get(f"{first_url}/approvals").status_code == 404
    assert web.get(f"{first_url}/events?follow=false").status_code == 404


def test_workspace_file_preview_classifies_and_formats_supported_text(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "notes.md").write_text(
        "# Junction\n\nBuilt-in potential.\n", encoding="utf-8", newline="\n"
    )
    (root / "result.json").write_text('{"voltage":0.71,"converged":true}')
    (root / "sweep.csv").write_text(
        "bias,current\n0,0\n1,2e-6\n", encoding="utf-8", newline="\n"
    )
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    markdown = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "notes.md"},
    )
    structured = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "result.json"},
    )
    table = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "sweep.csv"},
    )

    assert markdown.status_code == 200
    assert markdown.json() == {
        "path": "notes.md",
        "name": "notes.md",
        "kind": "markdown",
        "mime_type": "text/markdown",
        "size": 32,
        "truncated": False,
        "content": "# Junction\n\nBuilt-in potential.\n",
    }
    assert structured.json()["kind"] == "json"
    assert structured.json()["content"] == (
        '{\n  "voltage": 0.71,\n  "converged": true\n}'
    )
    assert table.json()["kind"] == "csv"
    assert table.json()["content"] == "bias,current\n0,0\n1,2e-6\n"


def test_workspace_results_endpoint_returns_verified_canonical_bundle(
    tmp_path: Path, result_bundle_factory
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    result_bundle_factory(root)
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    response = web.get(
        f"/api/workspaces/{workspace['id']}/results",
        params={"path": "run-0001/results/canonical.json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["bundle_path"] == "run-0001"
    assert payload["manifest"]["run_id"] == "run-0001"
    assert payload["result"]["backend"] == "devsim"
    assert payload["result"]["fields"]["potential"]["unit"] == "V"
    assert payload["result"]["datasets"]["potential"]["unit"] == "V"
    assert payload["result"]["datasets"]["potential"]["axes"] == [
        "position__potential"
    ]
    assert payload["result"]["axes"]["position__potential"]["kind"] == "position"
    catalog = {entry["id"]: entry for entry in payload["catalog"]}
    assert catalog["potential"]["view"] == "curve"


def test_agent_run_result_endpoint_opens_application_managed_bundle(
    tmp_path: Path, result_bundle_factory, monkeypatch
) -> None:
    data_root = tmp_path / "app-data"
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(data_root))
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    conversation = services.conversations.create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)
    runtime = RuntimePaths.from_workspace(root)
    result_bundle_factory(runtime.bundle_root)
    store.save_experiment_result(
        run.id,
        bundle_run_id="run-0001",
        project_root=root / "experiments" / "bias-study",
        execution_state="completed",
        validation_state="passed",
    )
    web = TestClient(create_app(ide=services))

    response = web.get(f"/api/runs/{run.id}/result")

    assert response.status_code == 200
    assert response.json()["manifest"]["run_id"] == "run-0001"


def test_agent_run_bundle_export_writes_verified_reproducibility_archive(
    tmp_path: Path, result_bundle_factory, monkeypatch
) -> None:
    data_root = tmp_path / "app-data"
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(data_root))
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    conversation = services.conversations.create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)
    runtime = RuntimePaths.from_workspace(root)
    result_bundle_factory(runtime.bundle_root)
    store.save_experiment_result(
        run.id,
        bundle_run_id="run-0001",
        project_root=root / "experiments" / "bias-study",
        execution_state="completed",
        validation_state="passed",
    )
    web = TestClient(create_app(ide=services))
    destination = tmp_path / "exports" / "bias-study.akbundle"

    response = web.post(
        f"/api/runs/{run.id}/bundle/export",
        json={"destination": str(destination)},
    )

    assert response.status_code == 201
    assert destination.is_file()
    assert response.json()["destination"] == str(destination.resolve())
    assert response.json()["run_id"] == "run-0001"
    assert len(response.json()["sha256"]) == 64


def test_agent_run_dataset_endpoint_returns_bounded_viewer_data(
    tmp_path: Path, result_bundle_factory, monkeypatch
) -> None:
    data_root = tmp_path / "app-data"
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(data_root))
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    conversation = services.conversations.create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)
    runtime = RuntimePaths.from_workspace(root)
    result_bundle_factory(runtime.bundle_root)
    store.save_experiment_result(
        run.id,
        bundle_run_id="run-0001",
        project_root=root / "experiments" / "bias-study",
        execution_state="completed",
        validation_state="passed",
    )
    web = TestClient(create_app(ide=services))

    response = web.get(
        f"/api/runs/{run.id}/result/datasets/potential",
        params={"max_points": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "potential"
    assert payload["shape"] == [3]
    assert payload["axes"][0]["kind"] == "position"
    assert payload["values"] == [0.0, 0.41, 0.82]


def test_workspace_experiments_endpoint_lists_researcher_facing_projects(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    root = tmp_path / "repo"
    project = root / "experiments" / "gaussian-implant-sweep"
    project.mkdir(parents=True)
    for name in ("PLAN.md", "REPORT.md", "results.json", "validation.json"):
        (project / name).write_text("{}\n")
    workspace = services.workspaces.open(root)
    conversation = services.conversations.create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)
    store.save_experiment_result(
        run.id,
        bundle_run_id="run-0001",
        project_root=project,
        execution_state="completed",
        validation_state="needs_review",
    )
    web = TestClient(create_app(ide=services))

    response = web.get(f"/api/workspaces/{workspace.id}/experiments")

    assert response.status_code == 200
    assert response.json() == [
        {
            "run_id": str(run.id),
            "bundle_run_id": "run-0001",
            "name": "gaussian-implant-sweep",
            "project_path": "experiments/gaussian-implant-sweep",
            "execution_state": "completed",
            "validation_state": "needs_review",
            "artifacts": {
                "plan": "experiments/gaussian-implant-sweep/PLAN.md",
                "report": "experiments/gaussian-implant-sweep/REPORT.md",
                "results": "experiments/gaussian-implant-sweep/results.json",
                "validation": "experiments/gaussian-implant-sweep/validation.json",
            },
        }
    ]


def test_workspace_results_endpoint_sanitizes_invalid_bundle_error(
    tmp_path: Path, result_bundle_factory
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    bundle = result_bundle_factory(root)
    (bundle / "results" / "canonical.json").write_text("{}\n")
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    response = web.get(
        f"/api/workspaces/{workspace['id']}/results",
        params={"path": "run-0001/results/canonical.json"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "invalid_result_bundle",
        "message": "The result bundle is incomplete, malformed, or failed provenance checks.",
    }


def test_workspace_results_comparison_loads_only_bounded_verified_bundles(
    tmp_path: Path, result_bundle_factory
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    first = result_bundle_factory(root)
    second = root / "run-0002"
    shutil.copytree(first, second)
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    response = web.get(
        f"/api/workspaces/{workspace['id']}/results/compare",
        params=[
            ("paths", "run-0001/results/canonical.json"),
            ("paths", "run-0002/results/canonical.json"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert [run["bundle_path"] for run in payload["runs"]] == [
        "run-0001",
        "run-0002",
    ]

    too_many = web.get(
        f"/api/workspaces/{workspace['id']}/results/compare",
        params=[("paths", f"run-{index}/results/canonical.json") for index in range(9)],
    )
    assert too_many.status_code == 422


def test_workspace_file_preview_recognizes_extensionless_utf8_text(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "Makefile").write_text(
        "validate:\n\tpython scripts/check.py\n", encoding="utf-8", newline="\n"
    )
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    response = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "Makefile"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "text"
    assert response.json()["mime_type"] == "text/plain"
    assert response.json()["content"] == "validate:\n\tpython scripts/check.py\n"


def test_workspace_file_preview_truncates_large_text_without_loading_it_all(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "large.log").write_text("x" * (1024 * 1024 + 100))
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    response = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "large.log"},
    )

    assert response.status_code == 200
    assert response.json()["kind"] == "text"
    assert response.json()["truncated"] is True
    assert len(response.json()["content"].encode()) <= 1024 * 1024


def test_workspace_binary_preview_exposes_metadata_and_safe_raw_delivery(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    png = b"\x89PNG\r\n\x1a\n" + b"payload"
    (root / "field.png").write_bytes(png)
    (root / "report.pdf").write_bytes(b"%PDF-1.7\npreview")
    (root / "mesh.bin").write_bytes(b"\x00\x01\x02")
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    image = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "field.png"},
    )
    pdf = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "report.pdf"},
    )
    binary = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "mesh.bin"},
    )
    displayed = web.get(
        f"/api/workspaces/{workspace['id']}/files/raw",
        params={"path": "field.png"},
    )
    blocked_inline = web.get(
        f"/api/workspaces/{workspace['id']}/files/raw",
        params={"path": "mesh.bin"},
    )
    downloaded = web.get(
        f"/api/workspaces/{workspace['id']}/files/raw",
        params={"path": "mesh.bin", "download": "true"},
    )

    assert image.json()["kind"] == "image"
    assert image.json()["content"] is None
    assert pdf.json()["kind"] == "pdf"
    assert binary.json()["kind"] == "binary"
    assert displayed.status_code == 200
    assert displayed.content == png
    assert displayed.headers["content-type"] == "image/png"
    assert displayed.headers["content-disposition"].startswith("inline;")
    assert displayed.headers["x-content-type-options"] == "nosniff"
    assert displayed.headers["content-security-policy"] == "sandbox"
    assert blocked_inline.status_code == 415
    assert downloaded.status_code == 200
    assert downloaded.headers["content-disposition"].startswith("attachment;")


def test_workspace_file_preview_rejects_directories_and_workspace_escape(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "folder").mkdir()
    (tmp_path / "outside.txt").write_text("secret")
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    directory = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "folder"},
    )
    escaped = web.get(
        f"/api/workspaces/{workspace['id']}/files/preview",
        params={"path": "../outside.txt"},
    )

    assert directory.status_code == 400
    assert escaped.status_code == 400
    assert escaped.json() == {
        "code": "invalid_workspace_path",
        "message": "The workspace path is unavailable or invalid.",
    }
    assert "secret" not in escaped.text


def test_workspace_text_file_can_be_loaded_and_saved_with_conflict_protection(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "model.py"
    target.write_text("value = 1\n", encoding="utf-8", newline="\n")
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    endpoint = f"/api/workspaces/{workspace['id']}/files/content"

    loaded = web.get(endpoint, params={"path": "model.py"})

    assert loaded.status_code == 200
    original = loaded.json()
    assert original["content"] == "value = 1\n"
    assert len(original["sha256"]) == 64

    saved = web.put(
        endpoint,
        json={
            "path": "model.py",
            "content": "value = 2\n",
            "expected_sha256": original["sha256"],
        },
    )

    assert saved.status_code == 200
    assert saved.json()["content"] == "value = 2\n"
    assert target.read_text() == "value = 2\n"

    stale = web.put(
        endpoint,
        json={
            "path": "model.py",
            "content": "value = 3\n",
            "expected_sha256": original["sha256"],
        },
    )
    assert stale.status_code == 409
    assert stale.json() == {
        "code": "workspace_file_conflict",
        "message": "The file changed after it was opened. Refresh before saving.",
    }
    assert target.read_text() == "value = 2\n"


def test_workspace_editor_refuses_nul_content_on_save(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "model.py"
    target.write_text("value = 1\n")
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    endpoint = f"/api/workspaces/{workspace['id']}/files/content"
    original = web.get(endpoint, params={"path": "model.py"}).json()

    response = web.put(
        endpoint,
        json={
            "path": "model.py",
            "content": "value = 2\x00\n",
            "expected_sha256": original["sha256"],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_workspace_path"
    assert target.read_text() == "value = 1\n"


@pytest.mark.parametrize("relative", [".env", "large.log", "mesh.bin"])
def test_workspace_editor_refuses_sensitive_truncated_and_binary_files(
    tmp_path: Path, relative: str
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".env").write_text("SECRET=value\n")
    (root / "large.log").write_text("x" * (1024 * 1024 + 1))
    (root / "mesh.bin").write_bytes(b"\x00\x01")
    web = ide_client(tmp_path)
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    response = web.get(
        f"/api/workspaces/{workspace['id']}/files/content",
        params={"path": relative},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_workspace_path"


def test_local_directory_picker_returns_selected_directory(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "selected-repository"
    root.mkdir()
    monkeypatch.setattr(
        ide_routes,
        "select_directory",
        lambda: root,
        raising=False,
    )

    response = ide_client(tmp_path).post("/api/system/directories/select")

    assert response.status_code == 200
    assert response.json() == {"path": str(root)}


def test_local_directory_picker_reports_cancellation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        ide_routes,
        "select_directory",
        lambda: None,
        raising=False,
    )

    response = ide_client(tmp_path).post("/api/system/directories/select")

    assert response.status_code == 200
    assert response.json() == {"path": None}


def test_linux_directory_picker_uses_available_native_dialog(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "chosen"
    root.mkdir()
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda command: "/usr/bin/zenity" if command == "zenity" else None,
    )

    def run_dialog(
        command: list[str], **_options: object
    ) -> subprocess.CompletedProcess[str]:
        assert command == [
            "/usr/bin/zenity",
            "--file-selection",
            "--directory",
            "--title=Open repository folder",
        ]
        return subprocess.CompletedProcess(command, 0, f"{root}\n", "")

    monkeypatch.setattr(subprocess, "run", run_dialog)

    assert ide_routes.select_directory() == root.resolve()


def test_headless_linux_directory_picker_has_safe_error(monkeypatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    with pytest.raises(RuntimeError, match="graphical desktop"):
        ide_routes.select_directory()


def test_sse_reconnect_honors_last_event_id_without_duplicates(
    tmp_path: Path,
) -> None:
    web = ide_client(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    web.post(session_url)
    web.post(
        f"{session_url}/messages",
        json={"content": "Inspect files"},
    )
    all_events = web.get(f"{session_url}/events?follow=false")
    first_id = int(all_events.text.splitlines()[0].removeprefix("id: "))

    resumed = web.get(
        f"{session_url}/events?follow=false",
        headers={"Last-Event-ID": str(first_id)},
    )

    assert f"id: {first_id}\n" not in resumed.text
    assert "event: message_created" in resumed.text


def test_finite_sse_response_returns_complete_event_history(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    web = TestClient(create_app(ide=services))
    root = tmp_path / "repo"
    root.mkdir()
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    conversation = web.post(session_url).json()
    for sequence in range(205):
        events.append(
            conversation_id=conversation["id"],
            kind="status_changed",
            payload={"sequence": sequence},
        )

    response = web.get(
        f"{session_url}/events?follow=false"
    )

    assert response.status_code == 200
    assert response.text.count("event: status_changed") == 205


def test_invalid_workspace_paths_and_unknown_records_are_sanitized(
    tmp_path: Path,
) -> None:
    web = ide_client(tmp_path)
    missing = tmp_path / "company-secret-directory-name"

    invalid = web.post("/api/workspaces", json={"path": str(missing)})
    unknown = web.get(f"/api/workspaces/{uuid4()}")

    assert invalid.status_code == 400
    assert invalid.json() == {
        "code": "invalid_workspace_path",
        "message": "The workspace path is unavailable or invalid.",
    }
    assert str(missing) not in invalid.text
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "workspace_not_found"


def test_missing_child_workspace_path_is_a_sanitized_client_error(
    tmp_path: Path,
) -> None:
    web = ide_client(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()

    response = web.get(
        f"/api/workspaces/{workspace['id']}/entries?path=deleted-directory"
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid_workspace_path",
        "message": "The workspace path is unavailable or invalid.",
    }
    assert "deleted-directory" not in response.text
