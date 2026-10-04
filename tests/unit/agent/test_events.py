import shlex
import sys
from pathlib import Path
from uuid import UUID

from openhands.sdk.agent.stream_context import StreamAborted, StreamDelta, StreamStarted
from openhands.sdk.event import ActionEvent, MessageEvent, ObservationEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.llm.message import MessageToolCall
from openhands.sdk.security import SecurityRisk
from openhands.sdk.tool import Observation
from openhands.tools.task_tracker.definition import TaskItem, TaskTrackerAction
from openhands.tools.terminal.definition import TerminalAction

from tcad_agent.agent.events import AgentEventBridge, structured_action_metadata
from tcad_agent.agent.tools import TcadDomainAction, TcadDomainObservation
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.artifacts import ExperimentPlanArtifactWriter
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.ide.changes import WorkspaceChangeTracker
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager


class _TestObservation(Observation):
    pass


def _services(tmp_path: Path):
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    workspace = WorkspaceManager(store).open(tmp_path)
    conversations = ConversationService(store, events)
    conversation = conversations.create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    return store, events, conversations, conversation, run


def _terminal_action(command: str, *, risk: SecurityRisk) -> ActionEvent:
    return ActionEvent(
        thought=[TextContent(text="private chain of thought")],
        reasoning_content="private reasoning",
        action=TerminalAction(command=command),
        tool_name="terminal",
        tool_call_id="call-1",
        tool_call=MessageToolCall(
            id="call-1",
            name="terminal",
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="response-1",
        security_risk=risk,
    )


def _task_plan_action() -> ActionEvent:
    return ActionEvent(
        thought=[TextContent(text="private chain of thought")],
        reasoning_content="private reasoning",
        action=TaskTrackerAction(
            command="plan",
            task_list=[
                TaskItem(
                    title="Inspect the simulator adapter",
                    notes="credential secret-value must never cross the boundary",
                    status="in_progress",
                ),
                TaskItem(title="Run validation", status="todo"),
            ],
        ),
        tool_name="task_tracker",
        tool_call_id="call-plan",
        tool_call=MessageToolCall(
            id="call-plan",
            name="task_tracker",
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="response-plan",
        security_risk=SecurityRisk.LOW,
    )


def _domain_action(operation: str, *, risk: SecurityRisk) -> ActionEvent:
    return ActionEvent(
        thought=[],
        action=TcadDomainAction(
            operation=operation,
            payload={"query": "DEVSIM contact equation"},
        ),
        tool_name="tcad_domain",
        tool_call_id=f"call-{operation}",
        tool_call=MessageToolCall(
            id=f"call-{operation}",
            name="tcad_domain",
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="response-domain",
        security_risk=risk,
    )


def test_event_bridge_persists_normalized_tool_and_assistant_events(
    tmp_path: Path, monkeypatch
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-value")
    bridge = AgentEventBridge(conversation.id, run.id, store, events, conversations)
    action = _terminal_action("pytest -q --token secret-value", risk=SecurityRisk.LOW)
    observation = ObservationEvent(
        tool_name="terminal",
        tool_call_id="call-1",
        action_id=action.id,
        observation=_TestObservation.from_text("x" * 20_000 + " secret-value"),
    )
    answer = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text="Completed safely")]
        ),
    )

    bridge(action)
    bridge(observation)
    bridge(answer)

    activity = events.list_after(conversation.id, 0)
    serialized = " ".join(str(event.payload) for event in activity)
    assert "secret-value" not in serialized
    assert "private chain of thought" not in serialized
    assert "private reasoning" not in serialized
    assert max(len(str(event.payload)) for event in activity) < 17_000
    assert [event.kind for event in activity][-3:] == [
        "tool_call_started",
        "tool_call_completed",
        "message_created",
    ]
    started = activity[-3].payload
    assert started["phase"] == "validate"
    assert started["evidence_kind"] == "validation"
    assert conversations.messages(conversation.id)[-1].content == "Completed safely"


def test_high_risk_action_creates_one_pending_approval(tmp_path: Path) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    bridge = AgentEventBridge(conversation.id, run.id, store, events, conversations)
    action = _terminal_action("git push", risk=SecurityRisk.HIGH)

    bridge(action)

    approvals = store.list_pending_approvals(conversation.id)
    assert len(approvals) == 1
    assert approvals[0].action_id == action.id
    assert approvals[0].payload == {"command": "git push"}
    assert approvals[0].permission_category.value == "git_mutation"
    assert approvals[0].summary.startswith("Agent Kronig wants to change Git history")
    assert store.get_run(run.id).state.value == "waiting_for_approval"


def test_event_bridge_skips_approval_for_a_granted_run_category(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=tmp_path,
        permission_grants={"git_mutation"},
    )

    bridge(_terminal_action("git push", risk=SecurityRisk.HIGH))

    assert store.list_pending_approvals(conversation.id) == ()
    grant_events = [
        event
        for event in events.list_after(conversation.id, 0)
        if event.kind == "permission_grant_used"
    ]
    assert len(grant_events) == 1
    assert grant_events[0].payload["permission_category"] == "git_mutation"


def test_scientific_web_research_is_visible_and_reuses_run_network_grant(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    first_bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=tmp_path,
    )

    first_bridge(_domain_action("search_web", risk=SecurityRisk.HIGH))

    (approval,) = store.list_pending_approvals(conversation.id)
    assert approval.permission_category.value == "network_access"
    started = next(
        event
        for event in events.list_after(conversation.id, 0)
        if event.kind == "tool_call_started"
    )
    assert started.payload["phase"] == "inspect"
    assert started.payload["evidence_kind"] == "research"
    assert started.payload["research_scope"] == "web"

    store.resolve_approval_with_grant(approval.id, approval.revision)
    granted_bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=tmp_path,
        permission_grants={"network_access"},
    )
    granted_bridge(_domain_action("fetch_source", risk=SecurityRisk.HIGH))

    assert store.list_pending_approvals(conversation.id) == ()
    grant_events = [
        event
        for event in events.list_after(conversation.id, 0)
        if event.kind == "permission_grant_used"
    ]
    assert grant_events[-1].payload["permission_category"] == "network_access"


def test_on_stream_never_persists_private_model_reasoning(
    tmp_path: Path, monkeypatch
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-value")
    bridge = AgentEventBridge(conversation.id, run.id, store, events, conversations)

    bridge.on_stream(StreamStarted(item_id="item-1", attempt=1, anchor_seq=None))
    bridge.on_stream(
        StreamDelta(
            item_id="item-1",
            attempt=1,
            order=0,
            kind="reasoning",
            content="thinking about it, token secret-value",
        )
    )
    bridge.on_stream(
        StreamAborted(item_id="item-1", attempt=1, reason="cancelled")
    )

    activity = events.list_after(conversation.id, 0)
    serialized = " ".join(str(event.payload) for event in activity)
    assert "thinking about it" not in serialized
    assert "secret-value" not in serialized
    assert not {
        "thinking_started",
        "thinking_delta",
        "thinking_aborted",
    } & {event.kind for event in activity}
    assert [event.kind for event in activity][-2:] == [
        "agent_progress_started",
        "agent_progress_interrupted",
    ]
    assert all("content" not in event.payload for event in activity[-2:])


def test_task_plan_exposes_only_safe_operational_items(
    tmp_path: Path, monkeypatch
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "secret-value")
    bridge = AgentEventBridge(conversation.id, run.id, store, events, conversations)

    bridge(_task_plan_action())

    started = events.list_after(conversation.id, 0)[-1]
    assert started.kind == "tool_call_started"
    assert started.payload["arguments"] == {
        "tasks": [
            {"title": "Inspect the simulator adapter", "status": "in_progress"},
            {"title": "Run validation", "status": "todo"},
        ]
    }
    serialized = str(started.payload)
    assert "private chain of thought" not in serialized
    assert "private reasoning" not in serialized
    assert "secret-value" not in serialized


def test_bridge_accepts_uuid_identifiers(tmp_path: Path) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)

    bridge = AgentEventBridge(
        UUID(str(conversation.id)), UUID(str(run.id)), store, events, conversations
    )

    assert bridge.conversation_id == conversation.id


def test_structured_phase_metadata_uses_typed_command_semantics() -> None:
    validation = structured_action_metadata(
        _terminal_action(
            'cd "/workspace" && python scripts/check.py 2>&1',
            risk=SecurityRisk.LOW,
        )
    )
    inspection = structured_action_metadata(
        _terminal_action("cat checks/input.txt", risk=SecurityRisk.LOW)
    )
    module_validation = structured_action_metadata(
        _terminal_action(
            f"{shlex.quote(sys.executable)} -m pytest -q", risk=SecurityRisk.LOW
        )
    )
    formatting = structured_action_metadata(
        _terminal_action("ruff format src", risk=SecurityRisk.LOW)
    )
    fixing = structured_action_metadata(
        _terminal_action("ruff check --fix src", risk=SecurityRisk.LOW)
    )

    assert validation == {
        "phase": "validate",
        "evidence_kind": "validation",
        "validation_scope": "workspace",
    }
    assert inspection == {"phase": "inspect"}
    assert module_validation == validation
    assert formatting == {"phase": "execute"}
    assert fixing == {"phase": "execute"}


def test_experiment_tool_metadata_distinguishes_preparation_and_execution() -> None:
    prepared = structured_action_metadata(
        _domain_action("prepare_experiment", risk=SecurityRisk.LOW)
    )
    executed = structured_action_metadata(
        _domain_action("execute_experiment", risk=SecurityRisk.HIGH)
    )

    assert prepared == {"phase": "validate", "evidence_kind": "validation"}
    assert executed == {"phase": "execute", "evidence_kind": "simulation"}


def test_windows_python_validation_is_structured_as_validation() -> None:
    metadata = structured_action_metadata(
        _terminal_action(
            r'"C:\Program Files\Python\python.exe" -m pytest -q',
            risk=SecurityRisk.LOW,
        )
    )

    assert metadata == {
        "phase": "validate",
        "evidence_kind": "validation",
        "validation_scope": "workspace",
    }


def test_domain_refusal_is_failed_activity_without_workspace_validation_claims(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    workspace = tmp_path / "repository"
    workspace.mkdir()
    baseline = WorkspaceChangeTracker().capture(workspace)
    store.save_run_baseline(run.id, baseline)
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=workspace,
    )
    action = ActionEvent(
        thought=[],
        action=TcadDomainAction(operation="validate_spec", payload={}),
        tool_name="tcad_domain",
        tool_call_id="domain-1",
        tool_call=MessageToolCall(
            id="domain-1",
            name="tcad_domain",
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="domain-response-1",
        security_risk=SecurityRisk.LOW,
    )

    bridge(action)
    (workspace / "unrelated.txt").write_text("not validated\n")
    bridge(
        ObservationEvent(
            tool_name="tcad_domain",
            tool_call_id=action.tool_call_id,
            action_id=action.id,
            observation=TcadDomainObservation.from_text(
                text='{"status":"refused"}',
                status="refused",
                code="invalid_spec",
                message="invalid",
                data={},
                is_error=False,
            ),
        )
    )

    completed = events.list_after(conversation.id, 0)[-1]
    assert completed.payload["is_error"] is True
    assert "validated_files" not in completed.payload


def test_prepared_experiment_observation_creates_typed_plan_gate(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    artifacts = ExperimentPlanArtifactWriter(tmp_path).write(prepared)
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=tmp_path,
    )
    action = _domain_action("prepare_experiment", risk=SecurityRisk.LOW)
    bridge(action)
    bridge(
        ObservationEvent(
            tool_name="tcad_domain",
            tool_call_id=action.tool_call_id,
            action_id=action.id,
            observation=TcadDomainObservation.from_text(
                text="prepared payload deliberately omitted from transcript",
                status="ok",
                code="experiment_prepared",
                message="Experiment plan is ready.",
                data={
                    "prepared": prepared.model_dump(mode="json"),
                    "plan_artifacts": {
                        "plan": str(artifacts.markdown_path),
                        "structured_plan": str(artifacts.json_path),
                    },
                },
            ),
        )
    )
    bridge(
        MessageEvent(
            source="agent",
            llm_message=Message(
                role="assistant",
                content=[TextContent(text="# Giant duplicate plan")],
            ),
        )
    )

    pending = store.get_prepared_plan(run.id)
    assert pending.plan_digest == prepared.plan_digest
    assert store.get_run(run.id).state.value == "waiting_for_plan_approval"
    assert conversations.messages(conversation.id) == ()
    completed = [
        event
        for event in events.list_after(conversation.id, 0)
        if event.kind == "tool_call_completed"
    ][-1]
    assert completed.payload["output"] == "Experiment plan prepared for review."


def test_executed_experiment_observation_registers_managed_result(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    project_root = tmp_path / "experiments" / "bias-study"
    project_root.mkdir(parents=True)
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=tmp_path,
    )
    action = _domain_action("execute_experiment", risk=SecurityRisk.LOW)
    bridge(action)
    bridge(
        ObservationEvent(
            tool_name="tcad_domain",
            tool_call_id=action.tool_call_id,
            action_id=action.id,
            observation=TcadDomainObservation.from_text(
                text="managed bundle omitted",
                status="ok",
                code="experiment_executed",
                message="Experiment completed.",
                data={
                    "bundle": {
                        "run_id": "experiment-0001",
                        "state": "failed",
                        "execution_state": "completed",
                        "validation_state": "needs_review",
                    },
                    "experiment": {"project_root": str(project_root)},
                },
            ),
        )
    )

    record = store.get_experiment_result(run.id)
    assert record.bundle_run_id == "experiment-0001"
    assert record.execution_state == "completed"
    assert record.validation_state == "needs_review"
    result_event = [
        event for event in events.list_after(conversation.id, 0)
        if event.kind == "result_ready"
    ][-1]
    assert result_event.payload["run_id"] == str(run.id)
    assert result_event.payload["validation_state"] == "needs_review"


def test_executed_experiment_observation_pauses_agent_after_result_handoff(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    project_root = tmp_path / "experiments" / "failed-study"
    project_root.mkdir(parents=True)
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=tmp_path,
    )
    pauses: list[str] = []
    bridge.bind_result_pause(lambda: pauses.append("paused"))
    action = _domain_action("execute_experiment", risk=SecurityRisk.LOW)

    bridge(action)
    bridge(
        ObservationEvent(
            tool_name="tcad_domain",
            tool_call_id=action.tool_call_id,
            action_id=action.id,
            observation=TcadDomainObservation.from_text(
                text="execution failed",
                status="ok",
                code="experiment_executed",
                message="Experiment finished with a failed execution state.",
                data={
                    "bundle": {
                        "run_id": "experiment-failed",
                        "execution_state": "failed",
                        "validation_state": "failed",
                    },
                    "experiment": {"project_root": str(project_root)},
                },
            ),
        )
    )

    assert pauses == ["paused"]
    kinds = [event.kind for event in events.list_after(conversation.id, 0)]
    assert kinds.index("result_ready") < len(kinds)


def test_executed_experiment_observation_records_structured_outcome(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    project_root = tmp_path / "experiments" / "bias-study"
    project_root.mkdir(parents=True)
    (project_root / "REPORT.md").write_text("# Evidence summary\n")
    (project_root / "results.json").write_text('{"status":"completed"}\n')
    (project_root / "validation.json").write_text(
        '{"overall":"warning","checks":['
        '{"id":"charge","level":"physical","status":"failed",'
        '"message":"charge mismatch","evidence_origin":"derived",'
        '"evidence_paths":[]}]}\n'
    )
    (project_root / "traceability.json").write_text(
        '{"schema_version":"1.0","records":['
        '{"deliverable":"potential","status":"satisfied",'
        '"evidence_datasets":["potential"],"rationale":"present"},'
        '{"deliverable":"current","status":"unmet",'
        '"evidence_datasets":[],"rationale":"absent"}]}\n'
    )
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=tmp_path,
    )
    action = _domain_action("execute_experiment", risk=SecurityRisk.LOW)
    bridge(action)
    bridge(
        ObservationEvent(
            tool_name="tcad_domain",
            tool_call_id=action.tool_call_id,
            action_id=action.id,
            observation=TcadDomainObservation.from_text(
                text="managed bundle omitted",
                status="ok",
                code="experiment_executed",
                message="Experiment completed.",
                data={
                    "bundle": {
                        "run_id": "experiment-0001",
                        "state": "failed",
                        "execution_state": "completed",
                        "validation_state": "needs_review",
                    },
                    "experiment": {"project_root": str(project_root)},
                },
            ),
        )
    )

    outcome = store.get_run_outcome(run.id)
    assert outcome.execution_state == "completed"
    assert outcome.validation_state == "needs_review"
    assert outcome.report_state == "complete"
    assert outcome.deliverable_state == "incomplete"
    assert outcome.failed_check_count == 1
    assert outcome.unmet_deliverables == ("current",)
    result_event = [
        event for event in events.list_after(conversation.id, 0)
        if event.kind == "result_ready"
    ][-1]
    assert result_event.payload["overall_state"] == "needs_attention"
    assert result_event.payload["failed_check_count"] == 1


def test_successful_action_observation_records_action_scoped_changed_paths(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    workspace = tmp_path / "repository"
    workspace.mkdir()
    target = workspace / "generated.txt"
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=workspace,
    )
    action = _terminal_action("python generate.py", risk=SecurityRisk.LOW)

    bridge(action)
    target.write_text("generated\n")
    bridge(
        ObservationEvent(
            tool_name="terminal",
            tool_call_id=action.tool_call_id,
            action_id=action.id,
            observation=_TestObservation.from_text("generated"),
        )
    )

    completed = events.list_after(conversation.id, 0)[-1]
    assert completed.kind == "tool_call_completed"
    assert completed.payload["affected_paths"] == ["generated.txt"]


def test_overlapping_mutating_actions_do_not_claim_each_others_files(
    tmp_path: Path,
) -> None:
    store, events, conversations, conversation, run = _services(tmp_path)
    workspace = tmp_path / "repository"
    workspace.mkdir()
    bridge = AgentEventBridge(
        conversation.id,
        run.id,
        store,
        events,
        conversations,
        workspace=workspace,
    )
    first = _terminal_action("python first.py", risk=SecurityRisk.LOW)
    second = _terminal_action("python second.py", risk=SecurityRisk.LOW).model_copy(
        update={"tool_call_id": "call-2"}
    )

    bridge(first)
    bridge(second)
    (workspace / "shared.txt").write_text("changed\n")
    for action in (first, second):
        bridge(
            ObservationEvent(
                tool_name="terminal",
                tool_call_id=action.tool_call_id,
                action_id=action.id,
                observation=_TestObservation.from_text("done"),
            )
        )

    completed = [
        event
        for event in events.list_after(conversation.id, 0)
        if event.kind == "tool_call_completed"
    ]
    assert len(completed) == 2
    assert all(event.payload["attribution_uncertain"] is True for event in completed)
    assert all("affected_paths" not in event.payload for event in completed)
