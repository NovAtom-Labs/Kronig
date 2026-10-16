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
from tcad_agent.prompting.errors import ResearcherInputRequiredError
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
        self.state = SimpleNamespace(execution_status=ConversationExecutionStatus.IDLE)
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


class RecoverableAuthorityFailureModel:
    """Require one clarification, then expose a researcher-owned field violation."""

    def __init__(self) -> None:
        self.calls = 0

    def prepare(self, **kwargs) -> PreparationDecision:
        del kwargs
        self.calls += 1
        if self.calls == 1:
            return clarification()
        raise ResearcherInputRequiredError(
            ("study.sequence",),
            "evidence cannot choose researcher-owned field study.sequence",
        )


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


def test_reused_question_id_does_not_replace_another_fields_answer(tmp_path):
    first = clarification()
    second = first.model_copy(
        update={
            "questions": (
                first.questions[0].model_copy(
                    update={
                        "field_path": "contacts.gate.work_function",
                        "prompt": "Gate work function?",
                    }
                ),
            ),
            "unresolved_critical": ("contacts.gate.work_function",),
            "intent": ready().intent,
        }
    )
    services, conversation, _, supervisor = setup(tmp_path, [first, second, ready()])
    run = supervisor.start(conversation.id, "Inspect the research request")
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    supervisor.answer_clarification(
        run.id, record.revision, (ClarificationAnswer(question_id="temperature", answer="300 K"),)
    )
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    supervisor.answer_clarification(
        run.id, record.revision, (ClarificationAnswer(question_id="temperature", answer="4.23 eV"),)
    )
    assert supervisor.join(run.id, timeout=3)
    answers = services.store.get_prompt_preparation(run.id).answers
    assert len(answers) == 2
    assert [(a.field_path, a.answer) for a in answers] == [
        ("study.temperature", "300 K"),
        ("contacts.gate.work_function", "4.23 eV"),
    ]
    assert answers[0].question_prompt == "What temperature should be used?"
    assert answers[0].question_revision < answers[1].question_revision


def test_client_cannot_rebind_answer_to_another_scientific_input(tmp_path):
    import pytest

    from tcad_agent.ide.store import IDEStoreError

    services, conversation, _, supervisor = setup(tmp_path, [clarification(), ready()])
    run = supervisor.start(conversation.id, "Inspect the research request")
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    forged = ClarificationAnswer.model_construct(
        question_id="temperature",
        answer="300 K",
        field_path="contacts.gate.work_function",
    )
    with pytest.raises(IDEStoreError, match="binding"):
        supervisor.answer_clarification(run.id, record.revision, (forged,))


def test_accepted_answers_can_be_replayed_after_preparation_finishes(tmp_path):
    services, conversation, factory, supervisor = setup(tmp_path, [clarification(), ready()])
    run = supervisor.start(conversation.id, "Inspect the research request")
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    answers = (ClarificationAnswer(question_id="temperature", answer="300 K"),)
    supervisor.answer_clarification(run.id, record.revision, answers)
    assert supervisor.join(run.id, timeout=3)
    acknowledged = supervisor.answer_clarification(run.id, record.revision, answers)
    assert acknowledged.id == run.id
    assert len(factory.created) == 1
    assert (
        len(
            [
                event
                for event in services.events.list_after(conversation.id, 0)
                if event.kind == "clarification_answered"
            ]
        )
        == 1
    )
    assert len(services.store.get_prompt_preparation(run.id).answers) == 1


def test_concurrent_identical_answer_requests_launch_only_one_preparation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    services, conversation, factory, supervisor = setup(tmp_path, [clarification(), ready()])
    run = supervisor.start(conversation.id, "Inspect the research request")
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    answers = (ClarificationAnswer(question_id="temperature", answer="300 K"),)
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [
            pool.submit(supervisor.answer_clarification, run.id, record.revision, answers)
            for _ in range(2)
        ]
        assert all(request.result(timeout=5).id == run.id for request in requests)
    assert supervisor.join(run.id, timeout=3)
    assert len(factory.created) == 1
    assert (
        len(
            [
                event
                for event in services.events.list_after(conversation.id, 0)
                if event.kind == "clarification_answered"
            ]
        )
        == 1
    )


def test_changed_stale_answer_is_not_treated_as_an_exact_replay(tmp_path):
    import pytest

    from tcad_agent.ide.store import IDEStoreError

    services, conversation, _, supervisor = setup(tmp_path, [clarification(), ready()])
    run = supervisor.start(conversation.id, "Inspect the research request")
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    supervisor.answer_clarification(
        run.id, record.revision, (ClarificationAnswer(question_id="temperature", answer="300 K"),)
    )
    assert supervisor.join(run.id, timeout=3)
    with pytest.raises(IDEStoreError, match="stale"):
        supervisor.answer_clarification(
            run.id,
            record.revision,
            (ClarificationAnswer(question_id="temperature", answer="310 K"),),
        )


def test_whitespace_only_answer_does_not_start_another_preparation(tmp_path):
    import pytest

    from tcad_agent.ide.store import IDEStoreError

    services, conversation, factory, supervisor = setup(tmp_path, [clarification(), ready()])
    run = supervisor.start(conversation.id, "Inspect the research request")
    assert supervisor.join(run.id, timeout=3)
    before = services.store.get_prompt_preparation(run.id)
    with pytest.raises(IDEStoreError, match="non-empty"):
        supervisor.answer_clarification(run.id, before.revision, (
            ClarificationAnswer(question_id="temperature", answer="   "),))
    assert services.store.get_prompt_preparation(run.id) == before
    assert not factory.created


def test_preparation_round_budget_blocks_more_calls_without_discarding_answers(
    tmp_path, monkeypatch
):
    import pytest

    from tcad_agent.ide.store import IDEStoreError

    monkeypatch.setenv("AGENT_KRONIG_MAX_CLARIFICATION_ROUNDS", "1")
    second = clarification().model_copy(
        update={
            "questions": (
                clarification()
                .questions[0]
                .model_copy(update={"id": "geometry", "field_path": "regions.structure"}),
            ),
            "unresolved_critical": ("regions.structure",),
        }
    )
    services, conversation, _, supervisor = setup(tmp_path, [clarification(), second, ready()])
    run = supervisor.start(conversation.id, "Inspect the research request")
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    supervisor.answer_clarification(
        run.id, record.revision, (ClarificationAnswer(question_id="temperature", answer="300 K"),)
    )
    assert supervisor.join(run.id, timeout=3)
    record = services.store.get_prompt_preparation(run.id)
    with pytest.raises(IDEStoreError, match="round limit"):
        supervisor.answer_clarification(
            run.id,
            record.revision,
            (ClarificationAnswer(question_id="geometry", answer="2 um silicon"),),
        )
    assert services.store.get_prompt_preparation(run.id).answers == record.answers


def test_scientific_agent_chat_finish_without_result_is_not_success(tmp_path):
    decision = ready()
    decision = decision.model_copy(
        update={
            "intent": decision.intent.model_copy(
                update={"selected_capabilities": ("study.equilibrium",)}
            )
        }
    )
    services, conversation, _factory, supervisor = setup(tmp_path, [decision])
    run = supervisor.start(conversation.id, "Run and show the scientific result")
    supervisor.join(run.id, timeout=3)
    assert services.store.get_run(run.id).state is RunState.BLOCKED
    assert any(
        event.kind == "run_blocked" for event in services.events.list_after(conversation.id, 0)
    )


def test_cancel_after_compilation_never_admits_runtime(tmp_path):
    services, conversation, factory, supervisor = setup(tmp_path, [ready()])
    append = services.events.append

    def cancel_on_compilation(conversation_id, kind, payload):
        event = append(conversation_id, kind, payload)
        if kind == "prompt_compiled":
            supervisor.stop(UUID(payload["run_id"]))
        return event

    services.events.append = cancel_on_compilation
    run = supervisor.start(conversation.id, "Run the study")
    supervisor.join(run.id, timeout=3)
    assert services.store.get_run(run.id).state is RunState.CANCELLED
    assert factory.created == []


def test_cancel_during_runtime_creation_never_sends_or_launches(tmp_path):
    services, conversation, factory, supervisor = setup(tmp_path, [ready()])
    create = factory.create

    def cancelled_create(workspace, conversation_id, bridge):
        runtime = create(workspace, conversation_id, bridge)
        supervisor.stop(bridge.run_id)
        return runtime

    factory.create = cancelled_create
    run = supervisor.start(conversation.id, "Run the study")
    supervisor.join(run.id, timeout=3)
    assert services.store.get_run(run.id).state is RunState.CANCELLED
    assert factory.created[0].messages == []


def test_supervisor_waits_for_answers_then_executes_compiled_request(
    tmp_path: Path,
) -> None:
    services, conversation, runtime, supervisor = setup(tmp_path, [clarification(), ready()])

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

    assert services.store.get_run(run.id).state is RunState.BLOCKED
    assert len(runtime.created) == 1
    sent = runtime.created[0].messages[0]
    assert '"kind":"agent_kronig.compiled_request"' in sent
    assert sent != "Simulate the requested structure"
    messages = services.store.list_messages(conversation.id)
    assert messages[0].content == "Simulate the requested structure"
    assert "300 K" in messages[1].content


def test_invalid_researcher_authority_returns_to_targeted_clarification(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    workspaces = WorkspaceManager(store)
    workspace = workspaces.open(tmp_path)
    conversations = ConversationService(store, events)
    conversation = conversations.create(workspace.id, "Recoverable preparation")
    services = SimpleNamespace(
        store=store,
        events=events,
        workspaces=workspaces,
        conversations=conversations,
        changes=WorkspaceChangeTracker(),
        runtime_root=tmp_path / ".runtime",
    )
    preparation = PromptPreparationService(
        model=RecoverableAuthorityFailureModel(),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "a" * 64},
    )
    supervisor = AgentSupervisor(
        services,
        CapturingRuntimeFactory(),
        preparation=preparation,
    )

    run = supervisor.start(conversation.id, "Simulate the requested structure")
    supervisor.join(run.id, timeout=3)
    pending = store.get_prompt_preparation(run.id)
    supervisor.answer_clarification(
        run.id,
        pending.revision,
        (ClarificationAnswer(question_id="temperature", answer="300 K"),),
    )
    supervisor.join(run.id, timeout=3)

    recovered = store.get_prompt_preparation(run.id)
    assert store.get_run(run.id).state is RunState.WAITING_FOR_USER
    assert recovered.decision is not None
    assert recovered.decision.status == "clarification"
    assert recovered.decision.questions[0].field_path == "study.sequence"
    assert recovered.decision.questions[0].id == "confirm_study_sequence"
    kinds = [event.kind for event in events.iter_after(conversation.id, 0)]
    assert kinds.count("clarification_required") == 2
    assert "run_failed" not in kinds


def test_complete_request_compiles_without_clarification(tmp_path: Path) -> None:
    services, conversation, runtime, supervisor = setup(tmp_path, [ready()])

    run = supervisor.start(conversation.id, "Run the fully specified study at 300 K")
    supervisor.join(run.id, timeout=3)

    # This fake runtime only finishes chat; compilation is not a simulation.
    assert services.store.get_run(run.id).state is RunState.BLOCKED
    preparation = services.store.get_prompt_preparation(run.id)
    assert preparation.compiled_request is not None
    kinds = [event.kind for event in services.events.iter_after(conversation.id, 0)]
    assert "prompt_compiled" in kinds
    phases = [
        event.payload["phase"]
        for event in services.events.iter_after(conversation.id, 0)
        if event.kind == "prompt_preparation_progress"
    ]
    assert phases == [
        "reviewing_workspace",
        "consulting_local_knowledge",
        "reasoning_about_scientific_intent",
        "compiling_request",
    ]
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
    assert store.get_run(run_id).state is RunState.BLOCKED

    duplicate = web.post(
        f"/api/runs/{run_id}/clarifications",
        json={
            "expected_revision": pending["revision"],
            "answers": [{"question_id": "temperature", "answer": "300 K"}],
        },
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == str(run_id)
