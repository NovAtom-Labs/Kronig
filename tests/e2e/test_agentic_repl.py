from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
import yaml
from fastapi.testclient import TestClient
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.testing import TestLLM

from scripts.create_repl_test_repo import create_repository
from tcad_agent.agent.runtime import OpenHandsRuntimeFactory
from tcad_agent.agent.supervisor import AgentSupervisor
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import PermissionCategory, RunState, is_run_grantable
from tcad_agent.ide.results import WorkspaceResultReader
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import IDEServices

PROJECT_ROOT = Path(__file__).parents[2]
GRADER = PROJECT_ROOT / "evaluations/repl/grade_workspace.py"
ACCEPTANCE_PROMPT = (
    "Inspect this repository and RESEARCH_TASK.md. Diagnose and fix the scientific "
    "validation failures without changing researcher-owned inputs, run the repository "
    "checks, delegate a read-only scientific review, and report exact evidence."
)


def _tool_call(identifier: str, name: str, arguments: dict[str, object]) -> Message:
    return Message(
        role="assistant",
        content=[TextContent(text="")],
        tool_calls=[
            MessageToolCall(
                id=identifier,
                name=name,
                arguments=json.dumps(
                    {
                        **arguments,
                        "security_risk": "LOW",
                        "summary": f"acceptance {name} operation",
                    }
                ),
                origin="completion",
            )
        ],
    )


def _scripted_responses(repository: Path) -> list[Message | Exception]:
    physics = repository / "src/junction_lab/physics.py"
    validation = repository / "src/junction_lab/validation.py"
    report = repository / "src/junction_lab/report.py"
    return [
        _tool_call(
            "view-task",
            "file_editor",
            {"command": "view", "path": str(repository / "RESEARCH_TASK.md")},
        ),
        _tool_call(
            "fix-field",
            "file_editor",
            {
                "command": "str_replace",
                "path": str(physics),
                "old_str": "return (2.0 * potential_v / width_m) / 100.0",
                "new_str": "return 2.0 * potential_v / width_m",
            },
        ),
        _tool_call(
            "fix-tolerance",
            "file_editor",
            {
                "command": "str_replace",
                "path": str(validation),
                "old_str": "<= tolerance_fraction * 0.01",
                "new_str": "<= tolerance_fraction",
            },
        ),
        _tool_call(
            "fix-provenance",
            "file_editor",
            {
                "command": "str_replace",
                "path": str(report),
                "old_str": ('    del input_sha256\n    return "\\n".join('),
                "new_str": '    return "\\n".join(',
            },
        ),
        _tool_call(
            "add-provenance",
            "file_editor",
            {
                "command": "str_replace",
                "path": str(report),
                "old_str": ('            f"Model: {summary[\'model_version\']}",\n            "",'),
                "new_str": (
                    "            f\"Model: {summary['model_version']}\",\n"
                    '            f"Input SHA-256: {input_sha256}",\n'
                    '            "",'
                ),
            },
        ),
        _tool_call(
            "run-checks",
            "terminal",
            {"command": "python scripts/check.py"},
        ),
        _tool_call(
            "delegate-review",
            "task",
            {
                "description": "Review the scientific repair",
                "prompt": (
                    "Read the repaired physics, validation, and report code. "
                    "Confirm units, tolerance semantics, provenance, and test evidence."
                ),
                "subagent_type": "tcad-reviewer",
            },
        ),
        _tool_call(
            "review-file",
            "file_editor",
            {"command": "view", "path": str(physics)},
        ),
        Message(
            role="assistant",
            content=[
                TextContent(
                    text=(
                        "Scientific review passed: electric field remains in V/m, "
                        "tolerance is fractional, and provenance is retained."
                    )
                )
            ],
        ),
        Message(
            role="assistant",
            content=[
                TextContent(
                    text=(
                        "Repaired three independent scientific defects. "
                        "Evidence: scripts/check.py passed 5 tests; the TCAD review "
                        "confirmed V/m units, fractional tolerance, and input SHA-256 "
                        "provenance. Researcher-owned experiment, data, and tests were "
                        "not changed."
                    )
                )
            ],
        ),
    ]


def _services(tmp_path: Path) -> IDEServices:
    store = SqliteIDEStore(tmp_path / "runtime/ide.sqlite3")
    events = EventFeed(store)
    return IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )


def _start_through_http(
    web: TestClient, repository: Path
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    workspace = web.post("/api/workspaces", json={"path": str(repository)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    conversation = web.post(session_url).json()
    message = web.post(
        f"{session_url}/messages",
        json={"content": ACCEPTANCE_PROMPT},
    ).json()
    response = web.post(
        f"{session_url}/runs",
        json={"message_id": message["id"]},
    )
    assert response.status_code == 202, response.text
    return workspace, conversation, response.json()


def test_repository_agent_repairs_validates_and_delegates_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PATH",
        str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
    )
    repository = create_repository(tmp_path / "pn-junction-research")
    llm = TestLLM.from_messages(_scripted_responses(repository))
    services = _services(tmp_path)
    supervisor = AgentSupervisor(
        services,
        OpenHandsRuntimeFactory(services.runtime_root, llm=llm),
    )
    web = TestClient(
        create_app(ide=services, agent_supervisor=supervisor),
        raise_server_exceptions=True,
    )

    _workspace, conversation, started = _start_through_http(web, repository)
    run_id = UUID(str(started["id"]))
    conversation_id = UUID(str(conversation["id"]))
    supervisor.join(run_id, timeout=30)

    completed = services.store.get_run(run_id)
    baseline = services.store.get_run_baseline(run_id)
    messages = web.get(f"/api/workspaces/{_workspace['id']}/session/messages").json()
    changes_response = web.get(f"/api/runs/{run_id}/changes")
    assert changes_response.status_code == 200
    changes = changes_response.json()
    activity = services.events.list_after(conversation_id, 0)
    grade = subprocess.run(
        [sys.executable, str(GRADER), "--workspace", str(repository)],
        check=False,
        capture_output=True,
        text=True,
    )
    changed = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert completed.state is RunState.COMPLETED
    assert messages[-1]["role"] == "assistant"
    assert "passed 5 tests" in messages[-1]["content"]
    assert json.loads(grade.stdout) == {
        "checks": {
            "generalizes_beyond_reference": True,
            "protected_inputs": True,
            "scientific_artifacts": True,
            "visible_tests": True,
        },
        "passed": True,
        "score": 100,
    }
    assert changed == [
        "src/junction_lab/physics.py",
        "src/junction_lab/report.py",
        "src/junction_lab/validation.py",
    ]
    assert baseline.root == repository.resolve()
    assert completed.created_at <= baseline.captured_at <= completed.updated_at
    assert not baseline.truncated
    assert [row["path"] for row in changes["files"]] == changed
    assert {row["operation"] for row in changes["files"]} == {"modified"}
    assert all(row["diff"] and not row["uncertain"] for row in changes["files"])
    assert changes["run_id"] == str(run_id)
    started_actions = {
        str(event.payload["action_id"]) for event in activity if event.kind == "tool_call_started"
    }
    completed_tools = [event for event in activity if event.kind == "tool_call_completed"]
    assert started_actions == {str(event.payload["action_id"]) for event in completed_tools}
    assert len(started_actions) == len(completed_tools)
    assert any("Ran 5 tests" in str(event.payload) for event in completed_tools), [
        event.payload for event in completed_tools
    ]
    assert any(event.payload.get("task_id") for event in completed_tools)
    assert llm.remaining_responses == 0


def test_repository_agent_prepares_executes_and_opens_canonical_tcad_result(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "empty-tcad-research"
    repository.mkdir()
    spec_payload = yaml.safe_load((PROJECT_ROOT / "examples/pn-junction.yaml").read_text())
    spec = ExperimentSpec.model_validate(spec_payload)
    prepared = ExperimentEngine().prepare(spec, "devsim")
    result_path = repository / "runs/run-agent-acceptance/results/canonical.json"
    llm = TestLLM.from_messages(
        [
            _tool_call(
                "prepare-experiment",
                "tcad_domain",
                {
                    "operation": "prepare_experiment",
                    "payload": spec_payload,
                    "backend": "devsim",
                },
            ),
            _tool_call(
                "execute-experiment",
                "tcad_domain",
                {
                    "operation": "execute_experiment",
                    "payload": {
                        "prepared": prepared.model_dump(mode="json"),
                        "approved_plan_digest": prepared.plan_digest,
                        "timeout_seconds": 120,
                        "run_id": "run-agent-acceptance",
                    },
                },
            ),
            _tool_call(
                "inspect-canonical-result",
                "file_editor",
                {"command": "view", "path": str(result_path)},
            ),
            Message(
                role="assistant",
                content=[
                    TextContent(
                        text=(
                            "The approved DEVSIM experiment completed and its canonical "
                            "result passed deterministic validation."
                        )
                    )
                ],
            ),
        ]
    )
    services = _services(tmp_path)
    supervisor = AgentSupervisor(
        services,
        OpenHandsRuntimeFactory(services.runtime_root, llm=llm),
    )
    web = TestClient(create_app(ide=services, agent_supervisor=supervisor))
    workspace = web.post("/api/workspaces", json={"path": str(repository)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    conversation = web.post(session_url).json()
    message = web.post(
        f"{session_url}/messages",
        json={
            "content": (
                "Run a small equilibrium silicon junction study with DEVSIM, validate "
                "the result, and inspect the canonical scientific evidence."
            )
        },
    ).json()
    started = web.post(f"{session_url}/runs", json={"message_id": message["id"]}).json()
    run_id = UUID(str(started["id"]))

    supervisor.join(run_id, timeout=30)
    waiting = services.store.get_run(run_id)
    assert waiting.state is RunState.WAITING_FOR_APPROVAL
    approvals = web.get(f"{session_url}/approvals").json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["permission_category"] == "simulation_execution"
    resolved = web.post(
        f"/api/approvals/{approval['id']}/approve-category",
        json={"expected_revision": approval["revision"]},
    )
    assert resolved.status_code == 200, resolved.text
    supervisor.join(run_id, timeout=60)

    assert services.store.get_run(run_id).state is RunState.COMPLETED
    view = WorkspaceResultReader().read(
        repository, "runs/run-agent-acceptance/results/canonical.json"
    )
    assert view.result.backend == "devsim"
    assert view.validation.overall == "passed"
    messages = web.get(f"{session_url}/messages").json()
    assert messages[-1]["role"] == "assistant"
    assert "passed deterministic validation" in messages[-1]["content"]
    assert UUID(str(conversation["id"])) == services.sessions.current().id
    assert llm.remaining_responses == 0


@pytest.mark.live_bedrock
def test_live_bedrock_repository_agent_is_opt_in(
    pytestconfig: pytest.Config,
    tmp_path: Path,
) -> None:
    if not pytestconfig.getoption("--run-live-bedrock"):
        pytest.skip("pass --run-live-bedrock to call the configured Bedrock model")
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        pytest.skip("AWS_BEARER_TOKEN_BEDROCK is not configured")
    repository = create_repository(tmp_path / "pn-junction-research")
    services = _services(tmp_path)
    supervisor = AgentSupervisor(
        services,
        OpenHandsRuntimeFactory(services.runtime_root),
    )
    web = TestClient(create_app(ide=services, agent_supervisor=supervisor))

    workspace, _conversation, started = _start_through_http(web, repository)
    run_id = UUID(str(started["id"]))

    terminal_states = {
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.BLOCKED,
        RunState.CANCELLED,
    }
    for _ in range(20):
        supervisor.join(run_id, timeout=300)
        state = services.store.get_run(run_id).state
        if state in terminal_states:
            break
        assert state is RunState.WAITING_FOR_APPROVAL
        approvals = web.get(f"/api/workspaces/{workspace['id']}/session/approvals").json()
        assert approvals, "waiting run must expose its pending approval"
        approval = approvals[0]
        category = PermissionCategory(approval["permission_category"])
        endpoint = "approve-category" if is_run_grantable(category) else "approve"
        resolved = web.post(
            f"/api/approvals/{approval['id']}/{endpoint}",
            json={"expected_revision": approval["revision"]},
        )
        assert resolved.status_code == 200, resolved.text
    else:
        pytest.fail("live repository agent exceeded the approval/run bound")

    assert services.store.get_run(run_id).state is RunState.COMPLETED
    grade = subprocess.run(
        [sys.executable, str(GRADER), "--workspace", str(repository)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert grade.returncode == 0, grade.stdout
