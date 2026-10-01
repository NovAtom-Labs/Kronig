from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import UUID

import pytest
from openhands.sdk.conversation import ConversationExecutionStatus
from openhands.sdk.event import ActionEvent, MessageEvent, ObservationEvent
from openhands.sdk.event import Event as OpenHandsEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.llm.message import MessageToolCall
from openhands.sdk.security import SecurityRisk
from openhands.sdk.tool import Observation
from openhands.tools.terminal.definition import TerminalAction

from tcad_agent.agent.supervisor import AgentRunConflictError, AgentSupervisor
from tcad_agent.agent.tools import TcadDomainAction, TcadDomainObservation
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.artifacts import ExperimentPlanArtifactWriter
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.ide.changes import WorkspaceChangeTracker
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import ApprovalDecision, PlanApprovalMode, RunState
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager


class _TestObservation(Observation):
    pass


def tool_start() -> ActionEvent:
    return ActionEvent(
        thought=[],
        action=TerminalAction(command="pytest -q"),
        tool_name="terminal",
        tool_call_id="call-1",
        tool_call=MessageToolCall(
            id="call-1", name="terminal", arguments="{}", origin="completion"
        ),
        llm_response_id="response-1",
        security_risk=SecurityRisk.LOW,
    )


def tool_finish(action: ActionEvent) -> ObservationEvent:
    return ObservationEvent(
        tool_name="terminal",
        tool_call_id=action.tool_call_id,
        action_id=action.id,
        observation=_TestObservation.from_text("186 passed"),
    )


def assistant(content: str) -> MessageEvent:
    return MessageEvent(
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text=content)]),
    )


@dataclass
class ScriptedState:
    execution_status: ConversationExecutionStatus = ConversationExecutionStatus.IDLE


class ScriptedConversation:
    def __init__(
        self,
        conversation_id: UUID,
        callback,
        events: list[OpenHandsEvent],
        final_status: ConversationExecutionStatus,
        gate: Event | None = None,
    ) -> None:
        self.id = conversation_id
        self.callback = callback
        self.events = events
        self.final_status = final_status
        self.gate = gate
        self.state = ScriptedState()
        self.messages: list[str] = []
        self.rejections: list[str] = []

    def send_message(self, message: str, sender: str | None = None) -> None:
        del sender
        self.messages.append(message)

    def run(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.RUNNING
        if self.gate is not None:
            self.gate.wait(timeout=2)
        for item in self.events:
            self.callback(item)
            if self.state.execution_status is ConversationExecutionStatus.PAUSED:
                return
        self.state.execution_status = self.final_status

    def pause(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.PAUSED

    def interrupt(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.PAUSED

    def reject_pending_actions(self, reason: str = "User rejected") -> None:
        self.rejections.append(reason)


class ScriptedRuntimeFactory:
    def __init__(
        self,
        events: list[OpenHandsEvent],
        *,
        status: ConversationExecutionStatus = ConversationExecutionStatus.FINISHED,
        gate: Event | None = None,
    ) -> None:
        self.events = events
        self.status = status
        self.gate = gate
        self.created: list[ScriptedConversation] = []

    def create(self, workspace: Path, conversation_id: UUID, callback):
        assert workspace.is_dir()
        conversation = ScriptedConversation(
            conversation_id,
            callback,
            self.events,
            self.status,
            self.gate,
        )
        self.created.append(conversation)
        return conversation


class FailingRuntimeFactory:
    def create(self, workspace: Path, conversation_id: UUID, callback):
        del workspace, conversation_id, callback
        raise RuntimeError("model configuration is unavailable")


@pytest.fixture
def services(tmp_path: Path):
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    workspaces = WorkspaceManager(store)
    workspace = workspaces.open(tmp_path)
    conversations = ConversationService(store, events)
    conversation = conversations.create(workspace.id, "Agent task")
    return SimpleNamespace(
        store=store,
        events=events,
        workspaces=workspaces,
        conversations=conversations,
        changes=WorkspaceChangeTracker(),
        conversation=conversation,
        runtime_root=tmp_path / ".runtime",
    )


def test_start_captures_baseline_before_runtime_executes(services) -> None:
    observed = {"baseline_present": False}

    class BaselineObservingConversation(ScriptedConversation):
        def run(self) -> None:
            run = services.store.list_runs(services.conversation.id)[-1]
            observed["baseline_present"] = (
                services.store.get_run_baseline(run.id) is not None
            )
            super().run()

    class BaselineObservingFactory(ScriptedRuntimeFactory):
        def create(self, workspace: Path, conversation_id: UUID, callback):
            conversation = BaselineObservingConversation(
                conversation_id,
                callback,
                self.events,
                self.status,
                self.gate,
            )
            self.created.append(conversation)
            return conversation

    supervisor = AgentSupervisor(services, BaselineObservingFactory([]))

    run = supervisor.start(services.conversation.id, "repair and validate")
    supervisor.join(run.id, timeout=2)

    assert observed["baseline_present"] is True
    assert services.store.get_run_baseline(run.id).root == services.workspaces.get(
        services.conversation.workspace_id
    ).root


def test_supervisor_runs_in_background_and_persists_final_answer(services) -> None:
    action = tool_start()
    runtime = ScriptedRuntimeFactory(
        events=[action, tool_finish(action), assistant("Completed")]
    )
    supervisor = AgentSupervisor(services, runtime)

    run = supervisor.start(
        services.conversation.id, "Inspect and test the repository"
    )
    supervisor.join(run.id, timeout=2)

    assert services.store.get_run(run.id).state is RunState.COMPLETED
    assert services.store.get_run_change_manifest(run.id) is not None
    assert services.store.list_messages(services.conversation.id)[-1].content == "Completed"
    kinds = [
        event.kind
        for event in services.events.iter_after(services.conversation.id, 0)
    ]
    for expected in (
        "run_started",
        "tool_call_started",
        "tool_call_completed",
        "run_completed",
    ):
        assert expected in kinds


def test_contextual_approved_resumes_same_run_without_second_simulation_prompt(
    services,
    valid_spec: ExperimentSpec,
) -> None:
    workspace = services.workspaces.get(services.conversation.workspace_id).root
    supervisor = AgentSupervisor(services, ScriptedRuntimeFactory([]))
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    artifacts = ExperimentPlanArtifactWriter(workspace).write(prepared)
    action = ActionEvent(
        thought=[],
        action=TcadDomainAction(
            operation="prepare_experiment",
            payload=valid_spec.normalized(),
            backend="devsim",
        ),
        tool_name="tcad_domain",
        tool_call_id="prepare-1",
        tool_call=MessageToolCall(
            id="prepare-1", name="tcad_domain", arguments="{}", origin="completion"
        ),
        llm_response_id="response-prepare",
        security_risk=SecurityRisk.LOW,
    )
    observation = ObservationEvent(
        tool_name="tcad_domain",
        tool_call_id=action.tool_call_id,
        action_id=action.id,
        observation=TcadDomainObservation.from_text(
            text="large prepared payload",
            status="ok",
            code="experiment_prepared",
            message="ready",
            data={
                "prepared": prepared.model_dump(mode="json"),
                "plan_artifacts": {
                    "plan": str(artifacts.markdown_path),
                    "structured_plan": str(artifacts.json_path),
                },
            },
        ),
    )
    runtime = ScriptedRuntimeFactory([action, observation])
    supervisor = AgentSupervisor(services, runtime)

    run = supervisor.start(services.conversation.id, "Run a simulation")
    supervisor.join(run.id, timeout=2)
    assert services.store.get_run(run.id).state is RunState.WAITING_FOR_PLAN_APPROVAL
    assert runtime.created[0].state.execution_status is ConversationExecutionStatus.PAUSED
    runtime.created[0].events.clear()

    resumed = supervisor.approve_contextual_plan(
        services.conversation.workspace_id, "approved"
    )
    assert resumed is not None
    supervisor.join(run.id, timeout=2)

    assert resumed.id == run.id
    assert services.store.get_run(run.id).state is RunState.BLOCKED
    assert services.store.list_run_permission_grants(run.id) == ()
    assert prepared.plan_digest in runtime.created[0].messages[-1]
    assert '"operation":"execute_approved_plan"' in runtime.created[0].messages[-1]
    assert '"prepared":{' not in runtime.created[0].messages[-1]
    assert len(runtime.created[0].messages[-1]) < 2_000
    assert len(services.store.list_runs(services.conversation.id)) == 1


def test_plan_revision_resumes_same_run_with_bounded_instruction(
    services,
    valid_spec: ExperimentSpec,
) -> None:
    workspace = services.workspaces.get(services.conversation.workspace_id).root
    supervisor = AgentSupervisor(services, ScriptedRuntimeFactory([]))
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    artifacts = ExperimentPlanArtifactWriter(workspace).write(prepared)
    run = services.store.create_run(
        services.conversation.id,
        services.conversation.id,
    )
    pending = services.store.save_prepared_plan(
        run.id,
        prepared,
        plan_path=artifacts.markdown_path,
        structured_plan_path=artifacts.json_path,
    )
    runtime = ScriptedConversation(
        run.sdk_conversation_id,
        lambda _event: None,
        [],
        ConversationExecutionStatus.FINISHED,
    )
    supervisor._runtimes[run.id] = runtime

    resumed = supervisor.revise_plan(
        run.id,
        pending.revision,
        "Keep the same sweep but request current density only.",
    )
    supervisor.join(run.id, timeout=2)

    assert resumed.id == run.id
    assert len(services.store.list_runs(services.conversation.id)) == 1
    assert "request current density only" in runtime.messages[-1]
    assert services.store.get_prepared_plan(run.id).status == "revision_requested"


def test_approved_experiment_without_verified_outcome_cannot_complete(
    services,
    valid_spec: ExperimentSpec,
) -> None:
    workspace = services.workspaces.get(services.conversation.workspace_id).root
    supervisor = AgentSupervisor(services, ScriptedRuntimeFactory([]))
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    artifacts = ExperimentPlanArtifactWriter(workspace).write(prepared)
    run = services.store.create_run(
        services.conversation.id,
        services.conversation.id,
    )
    pending = services.store.save_prepared_plan(
        run.id,
        prepared,
        plan_path=artifacts.markdown_path,
        structured_plan_path=artifacts.json_path,
    )
    supervisor.approve_plan(
        run.id,
        pending.revision,
        pending.plan_digest,
        mode=PlanApprovalMode.UNATTENDED_LOCAL,
    )
    supervisor.join(run.id, timeout=2)

    assert services.store.get_run(run.id).state is RunState.BLOCKED
    assert any(
        event.kind == "run_blocked"
        and "verified experiment outcome" in str(event.payload.get("detail", ""))
        for event in services.events.iter_after(services.conversation.id, 0)
    )


def test_supervisor_rejects_a_second_active_writer(services) -> None:
    gate = Event()
    supervisor = AgentSupervisor(services, ScriptedRuntimeFactory([], gate=gate))
    first = supervisor.start(services.conversation.id, "Run tests")

    with pytest.raises(AgentRunConflictError):
        supervisor.start(services.conversation.id, "Edit files too")

    gate.set()
    supervisor.join(first.id, timeout=2)


def test_active_run_for_workspace_returns_only_live_work(services) -> None:
    gate = Event()
    supervisor = AgentSupervisor(services, ScriptedRuntimeFactory([], gate=gate))
    workspace_id = services.conversation.workspace_id

    run = supervisor.start(services.conversation.id, "Run tests")

    assert supervisor.active_run_for_workspace(workspace_id).id == run.id
    gate.set()
    supervisor.join(run.id, timeout=2)
    assert supervisor.active_run_for_workspace(workspace_id) is None


def test_runtime_initialization_failure_terminates_the_created_run(services) -> None:
    supervisor = AgentSupervisor(services, FailingRuntimeFactory())

    with pytest.raises(RuntimeError, match="model configuration is unavailable"):
        supervisor.start(services.conversation.id, "Run the TCAD study")

    (run,) = services.store.list_runs(services.conversation.id)
    assert run.state is RunState.FAILED
    events = services.events.iter_after(services.conversation.id, 0)
    assert any(
        event.kind == "run_failed"
        and event.payload["run_id"] == str(run.id)
        and event.payload["detail"] == "model configuration is unavailable"
        for event in events
    )


def test_approval_resumes_and_denial_rejects_pending_action(services) -> None:
    runtime = ScriptedRuntimeFactory(
        [], status=ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    supervisor = AgentSupervisor(services, runtime)
    run = supervisor.start(services.conversation.id, "Push changes")
    supervisor.join(run.id, timeout=2)
    approval = services.store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "terminal: git push",
        {"command": "git push"},
    )

    resumed = supervisor.deny(approval.id, approval.revision, "Keep changes local")
    supervisor.join(run.id, timeout=2)

    resolved = services.store.get_approval(approval.id)
    assert resolved.decision is ApprovalDecision.DENY
    assert runtime.created[0].rejections == ["Keep changes local"]
    assert resumed.id == run.id


def test_approve_category_grants_only_the_current_run(services) -> None:
    runtime = ScriptedRuntimeFactory(
        [], status=ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    supervisor = AgentSupervisor(services, runtime)
    run = supervisor.start(services.conversation.id, "Push changes")
    supervisor.join(run.id, timeout=2)
    approval = services.store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "Agent Kronig wants to change Git history or send changes online.",
        {"command": "git push"},
        permission_category="git_mutation",
    )

    resumed = supervisor.approve_category(approval.id, approval.revision)
    supervisor.join(run.id, timeout=2)

    assert resumed.id == run.id
    assert services.store.list_run_permission_grants(run.id) == ("git_mutation",)


def test_approve_once_keeps_batch_waiting_until_every_action_is_decided(services) -> None:
    runtime = ScriptedRuntimeFactory(
        [], status=ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    supervisor = AgentSupervisor(services, runtime)
    run = supervisor.start(services.conversation.id, "Inspect external references")
    supervisor.join(run.id, timeout=2)
    first = services.store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "Read the first reference",
        {"command": "cat /shared/first.txt"},
        permission_category="external_file_access",
    )
    second = services.store.create_approval(
        run.id,
        "action-2",
        "terminal",
        "HIGH",
        "Read the second reference",
        {"command": "cat /shared/second.txt"},
        permission_category="external_file_access",
    )

    still_waiting = supervisor.approve(first.id, first.revision)

    assert still_waiting.state is RunState.WAITING_FOR_APPROVAL
    remaining = services.store.list_pending_approvals(services.conversation.id)
    assert [item.id for item in remaining] == [second.id]
    assert len(runtime.created) == 1

    supervisor.approve(second.id, second.revision)
    supervisor.join(run.id, timeout=2)
    assert len(runtime.created) == 1


def test_approve_category_resolves_every_matching_action_in_current_batch(services) -> None:
    runtime = ScriptedRuntimeFactory(
        [], status=ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    supervisor = AgentSupervisor(services, runtime)
    run = supervisor.start(services.conversation.id, "Inspect external references")
    supervisor.join(run.id, timeout=2)
    approvals = [
        services.store.create_approval(
            run.id,
            f"action-{index}",
            "terminal",
            "HIGH",
            f"Read reference {index}",
            {"command": f"cat /shared/{index}.txt"},
            permission_category="external_file_access",
        )
        for index in range(1, 3)
    ]

    supervisor.approve_category(approvals[0].id, approvals[0].revision)
    supervisor.join(run.id, timeout=2)

    assert services.store.list_pending_approvals(services.conversation.id) == ()
    assert all(
        services.store.get_approval(item.id).decision is ApprovalDecision.APPROVE
        for item in approvals
    )
    assert services.store.list_run_permission_grants(run.id) == (
        "external_file_access",
    )


def test_denial_rejects_runtime_batch_and_clears_every_pending_record(services) -> None:
    runtime = ScriptedRuntimeFactory(
        [], status=ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    supervisor = AgentSupervisor(services, runtime)
    run = supervisor.start(services.conversation.id, "Request several risky actions")
    supervisor.join(run.id, timeout=2)
    approvals = [
        services.store.create_approval(
            run.id,
            f"action-{index}",
            "terminal",
            "HIGH",
            f"Risky action {index}",
            {"command": f"git push origin branch-{index}"},
            permission_category="git_mutation",
        )
        for index in range(1, 3)
    ]

    supervisor.deny(approvals[0].id, approvals[0].revision, "Do not run this batch")
    supervisor.join(run.id, timeout=2)

    assert services.store.list_pending_approvals(services.conversation.id) == ()
    assert all(
        services.store.get_approval(item.id).decision is ApprovalDecision.DENY
        for item in approvals
    )
    assert runtime.created[0].rejections == ["Do not run this batch"]


def test_stop_cancels_pending_approval(services) -> None:
    runtime = ScriptedRuntimeFactory(
        [], status=ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
    )
    supervisor = AgentSupervisor(services, runtime)
    run = supervisor.start(services.conversation.id, "Request a risky action")
    supervisor.join(run.id, timeout=2)
    approval = services.store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "terminal: git push",
        {"command": "git push"},
    )

    cancelled = supervisor.stop(run.id)

    assert cancelled.state is RunState.CANCELLED
    assert services.store.get_approval(approval.id).decision is ApprovalDecision.DENY
    assert services.store.list_pending_approvals(services.conversation.id) == ()


def test_restart_recovery_cancels_interrupted_running_run(services) -> None:
    run = services.store.create_run(
        services.conversation.id, services.conversation.id
    )
    services.store.transition_run(run.id, run.revision, RunState.RUNNING)

    AgentSupervisor(services, ScriptedRuntimeFactory([]))

    assert services.store.get_run(run.id).state is RunState.CANCELLED


def test_restart_recovery_cancels_run_that_never_finished_starting(services) -> None:
    run = services.store.create_run(
        services.conversation.id, services.conversation.id
    )

    AgentSupervisor(services, ScriptedRuntimeFactory([]))

    assert services.store.get_run(run.id).state is RunState.CANCELLED
    events = services.events.iter_after(services.conversation.id, 0)
    assert any(
        event.kind == "run_cancelled"
        and event.payload["run_id"] == str(run.id)
        and "previous application session ended" in str(event.payload["detail"])
        for event in events
    )


def test_restart_recovery_cancels_pending_approval_instead_of_resuming(services) -> None:
    run = services.store.create_run(
        services.conversation.id, services.conversation.id
    )
    approval = services.store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "terminal: git push",
        {"command": "git push"},
    )

    AgentSupervisor(services, ScriptedRuntimeFactory([]))

    assert services.store.get_run(run.id).state is RunState.CANCELLED
    assert services.store.get_approval(approval.id).decision is ApprovalDecision.DENY
    assert services.store.list_pending_approvals(services.conversation.id) == ()
