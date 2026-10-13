from pathlib import Path
from uuid import UUID

import pytest

from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import AgentRunRecord, ApprovalDecision, RunState
from tcad_agent.ide.sessions import WorkspaceSessionBusyError, WorkspaceSessionService
from tcad_agent.ide.store import IDEStoreError, SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager


class RecordingSupervisor:
    def __init__(self, store: SqliteIDEStore) -> None:
        self.store = store
        self.stopped: list[UUID] = []
        self.denied_before_delete: list[ApprovalDecision] = []
        self.joined = True

    def active_run_for_workspace(self, workspace_id: UUID) -> AgentRunRecord | None:
        active = {
            RunState.QUEUED,
            RunState.RUNNING,
            RunState.WAITING_FOR_APPROVAL,
            RunState.WAITING_FOR_USER,
            RunState.PAUSED,
        }
        return next(
            (
                run
                for run in reversed(self.store.list_runs_for_workspace(workspace_id))
                if run.state in active
            ),
            None,
        )

    def stop(self, run_id: UUID) -> AgentRunRecord:
        run = self.store.get_run(run_id)
        for approval in self.store.list_pending_approvals(run.conversation_id):
            resolved = self.store.resolve_approval(
                approval.id, approval.revision, ApprovalDecision.DENY
            )
            assert resolved.decision is not None
            self.denied_before_delete.append(resolved.decision)
        current = self.store.get_run(run_id)
        cancelled = self.store.transition_run(run_id, current.revision, RunState.CANCELLED)
        self.stopped.append(run_id)
        return cancelled

    def join(self, run_id: UUID, timeout: float | None = None) -> bool:
        del run_id, timeout
        return self.joined


def _services(
    tmp_path: Path,
) -> tuple[
    SqliteIDEStore,
    WorkspaceManager,
    ConversationService,
    WorkspaceSessionService,
    RecordingSupervisor,
]:
    runtime_root = tmp_path / "runtime"
    store = SqliteIDEStore(runtime_root / "ide.sqlite3")
    events = EventFeed(store)
    workspaces = WorkspaceManager(store)
    conversations = ConversationService(store, events)
    sessions = WorkspaceSessionService(workspaces, conversations, runtime_root)
    supervisor = RecordingSupervisor(store)
    sessions.bind_supervisor(supervisor)
    return store, workspaces, conversations, sessions, supervisor


def test_open_creates_one_untitled_internal_session_for_workspace(
    tmp_path: Path,
) -> None:
    store, workspaces, _conversations, sessions, _supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = workspaces.open(repository)

    session = sessions.open(workspace.id)

    assert session.workspace_id == workspace.id
    assert sessions.current() == session
    internal = store.list_conversations(workspace.id)
    assert len(internal) == 1
    assert internal[0].id == session.id


def test_open_same_workspace_returns_current_session(tmp_path: Path) -> None:
    store, workspaces, _conversations, sessions, _supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = workspaces.open(repository)

    first = sessions.open(workspace.id)
    second = sessions.open(workspace.id)

    assert second == first
    assert len(store.list_conversations(workspace.id)) == 1


def test_open_different_workspace_releases_previous_session_tree(
    tmp_path: Path,
) -> None:
    store, workspaces, conversations, sessions, _supervisor = _services(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_workspace = workspaces.open(first_root)
    second_workspace = workspaces.open(second_root)
    first = sessions.open(first_workspace.id)
    conversations.add_user_message(first.id, "Temporary message")

    second = sessions.open(second_workspace.id)

    with pytest.raises(IDEStoreError):
        store.get_conversation(first.id)
    assert second.workspace_id == second_workspace.id
    assert sessions.current() == second


def test_open_different_workspace_refuses_while_live_run_exists(
    tmp_path: Path,
) -> None:
    store, workspaces, _conversations, sessions, _supervisor = _services(tmp_path)
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_workspace = workspaces.open(first_root)
    second_workspace = workspaces.open(second_root)
    first = sessions.open(first_workspace.id)
    store.create_run(first.id, first.id)

    with pytest.raises(WorkspaceSessionBusyError, match="active agent run"):
        sessions.open(second_workspace.id)

    assert sessions.current() == first
    assert store.get_conversation(first.id).id == first.id


def test_release_refuses_while_live_run_exists(tmp_path: Path) -> None:
    store, workspaces, _conversations, sessions, _supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = workspaces.open(repository)
    session = sessions.open(workspace.id)
    store.create_run(session.id, session.id)

    with pytest.raises(WorkspaceSessionBusyError, match="active agent run"):
        sessions.release()

    assert sessions.current() == session


def test_release_clears_terminal_session_and_openhands_state(
    tmp_path: Path,
) -> None:
    store, workspaces, _conversations, sessions, _supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = workspaces.open(repository)
    session = sessions.open(workspace.id)
    run = store.create_run(session.id, session.id)
    store.transition_run(run.id, run.revision, RunState.COMPLETED)
    openhands_state = tmp_path / "runtime" / "openhands" / session.id.hex
    openhands_state.mkdir(parents=True)
    (openhands_state / "events.jsonl").write_text("temporary", encoding="utf-8")

    sessions.release()

    assert sessions.current() is None
    assert not openhands_state.exists()
    with pytest.raises(IDEStoreError):
        store.get_conversation(session.id)


def test_release_rejects_symlinked_openhands_root_without_external_deletion(
    tmp_path: Path,
) -> None:
    store, workspaces, _conversations, sessions, _supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = workspaces.open(repository)
    session = sessions.open(workspace.id)
    external = tmp_path / "external-openhands"
    external_session = external / session.id.hex
    external_session.mkdir(parents=True)
    sentinel = external_session / "events.jsonl"
    sentinel.write_text("preserve", encoding="utf-8")
    (tmp_path / "runtime" / "openhands").symlink_to(external, target_is_directory=True)

    with pytest.raises(RuntimeError, match="escaped runtime storage"):
        sessions.release()

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert sessions.current() == session
    assert store.get_conversation(session.id).id == session.id


def test_shutdown_denies_approvals_cancels_nonterminal_run_and_clears_state(
    tmp_path: Path,
) -> None:
    store, workspaces, _conversations, sessions, supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = workspaces.open(repository)
    session = sessions.open(workspace.id)
    run = store.create_run(session.id, session.id)
    approval = store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "Send changes to a remote repository",
        {"command": "git push"},
    )

    sessions.shutdown()

    assert supervisor.stopped == [run.id]
    assert supervisor.denied_before_delete == [ApprovalDecision.DENY]
    assert sessions.current() is None
    with pytest.raises(IDEStoreError):
        store.get_approval(approval.id)
    with pytest.raises(IDEStoreError):
        store.get_conversation(session.id)


def test_shutdown_keeps_session_until_cancelled_runtime_thread_stops(
    tmp_path: Path,
) -> None:
    store, workspaces, _conversations, sessions, supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    repository.mkdir()
    workspace = workspaces.open(repository)
    session = sessions.open(workspace.id)
    run = store.create_run(session.id, session.id)
    supervisor.joined = False

    with pytest.raises(WorkspaceSessionBusyError, match="still stopping"):
        sessions.shutdown()

    assert supervisor.stopped == [run.id]
    assert sessions.current() == session
    assert store.get_conversation(session.id).id == session.id

    supervisor.joined = True
    sessions.shutdown()

    assert sessions.current() is None
    with pytest.raises(IDEStoreError):
        store.get_conversation(session.id)


def test_release_preserves_repository_files_and_generated_artifacts(
    tmp_path: Path,
) -> None:
    _store, workspaces, _conversations, sessions, _supervisor = _services(tmp_path)
    repository = tmp_path / "repository"
    artifact = repository / "results" / "equilibrium.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"validated":true}', encoding="utf-8")
    workspace = workspaces.open(repository)
    sessions.open(workspace.id)

    sessions.release()

    assert artifact.read_text(encoding="utf-8") == '{"validated":true}'
