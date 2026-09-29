from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from openhands.sdk.conversation import ConversationExecutionStatus

from tcad_agent.agent.supervisor import AgentSupervisor
from tcad_agent.ide.changes import WorkspaceChangeTracker
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import RunState
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.context import LocalEvidenceCollector, WorkspaceContextCollector
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    ClarificationQuestion,
    IntentField,
    IntentOrigin,
    PreparationDecision,
    ResolvedResearchIntent,
)
from tcad_agent.prompting.service import PromptPreparationService, ScriptedPreparationModel
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import IDEServices


class EmptyKnowledgeIndex:
    def search(self, query: str, filters=None, limit: int = 5):
        del query, filters, limit
        return ()


class FinishedConversation:
    def __init__(self, conversation_id: UUID) -> None:
        self.id = conversation_id
        self.state = SimpleNamespace(
            execution_status=ConversationExecutionStatus.IDLE
        )
        self.messages: list[str] = []

    def send_message(self, message: str, sender: str | None = None) -> None:
        del sender
        self.messages.append(message)

    def run(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.FINISHED

    def pause(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.PAUSED

    def interrupt(self) -> None:
        self.state.execution_status = ConversationExecutionStatus.PAUSED

    def reject_pending_actions(self, reason: str = "User rejected") -> None:
        del reason


class CapturingRuntimeFactory:
    def __init__(self) -> None:
        self.created: list[FinishedConversation] = []

    def create(self, workspace: Path, conversation_id: UUID, callback):
        del callback
        assert workspace.is_dir()
        conversation = FinishedConversation(conversation_id)
        self.created.append(conversation)
        return conversation


def setup(tmp_path: Path, decisions: list[PreparationDecision]):
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    workspaces = WorkspaceManager(store)
    workspace = workspaces.open(tmp_path)
    conversations = ConversationService(store, events)
    conversation = conversations.create(workspace.id, "Prepared run")
    services = SimpleNamespace(
        store=store,
        events=events,
        workspaces=workspaces,
        conversations=conversations,
        changes=WorkspaceChangeTracker(),
        runtime_root=tmp_path / ".runtime",
    )
    preparation = PromptPreparationService(
        model=ScriptedPreparationModel(decisions),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "a" * 64},
    )
    runtime = CapturingRuntimeFactory()
    supervisor = AgentSupervisor(services, runtime, preparation=preparation)
    return services, conversation, runtime, supervisor


def clarification() -> PreparationDecision:
    return PreparationDecision(
        status="clarification",
        summary="Temperature is missing.",
        questions=(
            ClarificationQuestion(
                id="temperature",
                field_path="study.temperature",
                prompt="What temperature should be used?",
                reason="Carrier statistics depend on temperature.",
            ),
        ),
        unresolved_critical=("study.temperature",),
    )


def ready() -> PreparationDecision:
    return PreparationDecision(
        status="ready",
        summary="The request is ready.",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Run the requested study at 300 K.",
            fields=(
                IntentField(
                    path="study.temperature",
                    value="300 K",
                    origin=IntentOrigin.RESEARCHER,
                ),
            ),
        ),
    )


def test_supervisor_waits_for_answers_then_executes_compiled_request(
    tmp_path: Path,
) -> None:
    services, conversation, runtime, supervisor = setup(
        tmp_path, [clarification(), ready()]
    )

    run = supervisor.start(conversation.id, "Simulate the requested structure")
    supervisor.join(run.id, timeout=3)

    waiting = services.store.get_run(run.id)
    preparation = services.store.get_prompt_preparation(run.id)
    assert waiting.state is RunState.WAITING_FOR_USER
    assert preparation.decision.status == "clarification"
    assert runtime.created == []

    resumed = supervisor.answer_clarification(
        run.id,
        preparation.revision,
        (ClarificationAnswer(question_id="temperature", answer="300 K"),),
    )
    assert resumed.id == run.id
    supervisor.join(run.id, timeout=3)

    assert services.store.get_run(run.id).state is RunState.COMPLETED
    assert len(runtime.created) == 1
    sent = runtime.created[0].messages[0]
    assert '"kind":"agent_kronig.compiled_request"' in sent
    assert sent != "Simulate the requested structure"
    messages = services.store.list_messages(conversation.id)
    assert messages[0].content == "Simulate the requested structure"
    assert "300 K" in messages[1].content


def test_complete_request_compiles_without_clarification(tmp_path: Path) -> None:
    services, conversation, runtime, supervisor = setup(tmp_path, [ready()])

    run = supervisor.start(conversation.id, "Run the fully specified study at 300 K")
    supervisor.join(run.id, timeout=3)

    assert services.store.get_run(run.id).state is RunState.COMPLETED
    preparation = services.store.get_prompt_preparation(run.id)
    assert preparation.compiled_request is not None
    kinds = [event.kind for event in services.events.iter_after(conversation.id, 0)]
    assert "prompt_compiled" in kinds
    assert len(runtime.created) == 1


def test_http_clarification_lifecycle_resumes_the_same_run(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    preparation = PromptPreparationService(
        model=ScriptedPreparationModel([clarification(), ready()]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "a" * 64},
    )
    runtime = CapturingRuntimeFactory()
    supervisor = AgentSupervisor(services, runtime, preparation=preparation)
    web = TestClient(create_app(ide=services, agent_supervisor=supervisor))
    root = tmp_path / "repo"
    root.mkdir()
    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    web.post(session_url)
    message = web.post(
        f"{session_url}/messages",
        json={"content": "Simulate the requested structure"},
    ).json()
    started = web.post(f"{session_url}/runs", json={"message_id": message["id"]})
    run_id = UUID(started.json()["id"])
    supervisor.join(run_id, timeout=3)

    preparation_response = web.get(f"/api/runs/{run_id}/preparation")
    assert preparation_response.status_code == 200
    pending = preparation_response.json()
    assert pending["decision"]["questions"][0]["id"] == "temperature"

    answered = web.post(
        f"/api/runs/{run_id}/clarifications",
        json={
            "expected_revision": pending["revision"],
            "answers": [{"question_id": "temperature", "answer": "300 K"}],
        },
    )
    assert answered.status_code == 202
    assert answered.json()["id"] == str(run_id)
    supervisor.join(run_id, timeout=3)
    assert store.get_run(run_id).state is RunState.COMPLETED
