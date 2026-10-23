import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.migrations import LATEST_SCHEMA_VERSION
from tcad_agent.ide.models import (
    ApprovalDecision,
    BaselineFile,
    PermissionCategory,
    PlanApprovalMode,
    RunState,
    WorkspaceBaseline,
    WorkspaceChangeSet,
)
from tcad_agent.ide.store import RUN_OWNED_TABLES, IDEStoreError, SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager


def test_store_operations_close_database_handles_without_garbage_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Retaining real connections exposes leaks deterministically on every OS.
    # Windows cannot remove session files while any of these handles is open.
    connections = []
    native_connect = sqlite3.connect

    def connect(*args, **kwargs):
        connection = native_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    assert store.get_workspace(workspace.id).root == tmp_path.resolve()
    with pytest.raises(IDEStoreError):
        store.get_workspace(uuid4())

    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_workspace_survives_store_reconstruction(tmp_path: Path) -> None:
    root = tmp_path / "plain-directory"
    root.mkdir()
    database = tmp_path / "ide.sqlite3"
    created = WorkspaceManager(SqliteIDEStore(database)).open(root)

    reopened = WorkspaceManager(SqliteIDEStore(database)).get(created.id)

    assert reopened.root == root.resolve()
    assert reopened.git.available is False


def test_store_applies_versioned_migrations_idempotently(tmp_path: Path) -> None:
    database = tmp_path / "ide.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE legacy_marker (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO legacy_marker (value) VALUES ('preserve-me')")
        connection.execute("PRAGMA user_version = 0")

    SqliteIDEStore(database)
    SqliteIDEStore(database)

    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        applied = connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        legacy = connection.execute("SELECT value FROM legacy_marker").fetchone()[0]

    assert version == LATEST_SCHEMA_VERSION
    assert applied == [(1,), (2,), (3,)]
    assert legacy == "preserve-me"


def test_every_run_owned_foreign_key_is_in_the_cleanup_graph(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    with sqlite3.connect(store.path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        referencing = {
            table
            for table in tables
            if any(
                row[2] == "agent_runs"
                for row in connection.execute(f'PRAGMA foreign_key_list("{table}")')
            )
        }

    assert referencing == set(RUN_OWNED_TABLES)


def test_run_and_pending_approval_survive_store_reconstruction(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ide.sqlite3"
    store = SqliteIDEStore(database)
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    approval = store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "git commit",
        {"command": "git commit"},
    )

    restored = SqliteIDEStore(database)

    assert restored.get_run(run.id).state is RunState.WAITING_FOR_APPROVAL
    assert restored.list_pending_approvals(conversation.id) == (approval,)


def test_run_transitions_reject_a_stale_revision(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    running = store.transition_run(run.id, run.revision, RunState.RUNNING)

    with pytest.raises(IDEStoreError, match="stale run revision"):
        store.transition_run(run.id, run.revision, RunState.COMPLETED)

    assert store.get_run(run.id) == running


def test_prepared_plan_is_typed_pending_state_and_approved_once(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")

    pending = store.save_prepared_plan(
        run.id,
        prepared,
        plan_path=tmp_path / "experiments" / "study" / "PLAN.md",
        structured_plan_path=tmp_path / "experiments" / "study" / "plan.json",
    )

    assert pending.status == "pending"
    assert store.get_run(run.id).state is RunState.WAITING_FOR_PLAN_APPROVAL
    approved = store.approve_prepared_plan(
        run.id,
        pending.revision,
        pending.plan_digest,
        mode=PlanApprovalMode.UNATTENDED_LOCAL,
    )
    assert approved.status == "approved"
    assert approved.approval_mode is PlanApprovalMode.UNATTENDED_LOCAL
    with pytest.raises(IDEStoreError, match=r"stale|already"):
        store.approve_prepared_plan(
            run.id,
            pending.revision,
            pending.plan_digest,
            mode=PlanApprovalMode.REVIEW_EACH_RISK,
        )


def test_managed_experiment_result_is_persisted_by_agent_run(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)

    created = store.save_experiment_result(
        run.id,
        bundle_run_id="experiment-0001",
        project_root=tmp_path / "experiments" / "bias-study",
        execution_state="completed",
        validation_state="needs_review",
    )

    restored = SqliteIDEStore(store.path).get_experiment_result(run.id)
    assert restored == created
    assert restored.bundle_run_id == "experiment-0001"
    assert restored.validation_state == "needs_review"


def test_workspace_experiment_history_is_newest_first(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Research run")
    first = store.create_run(conversation.id, conversation.id)
    second = store.create_run(conversation.id, conversation.id)
    store.save_experiment_result(
        first.id,
        bundle_run_id="experiment-0001",
        project_root=tmp_path / "experiments" / "first-study",
        execution_state="completed",
        validation_state="passed",
    )
    store.save_experiment_result(
        second.id,
        bundle_run_id="experiment-0002",
        project_root=tmp_path / "experiments" / "second-study",
        execution_state="completed",
        validation_state="needs_review",
    )

    history = store.list_experiment_results_for_workspace(workspace.id)

    assert [record.bundle_run_id for record in history] == [
        "experiment-0002",
        "experiment-0001",
    ]


def test_structured_run_outcome_persists_independent_component_states(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)

    created = store.save_run_outcome(
        run.id,
        execution_state="completed",
        validation_state="needs_review",
        deliverable_state="incomplete",
        report_state="complete",
        overall_state="needs_attention",
        failed_check_count=2,
        unmet_deliverables=("electron_density",),
        project_root=tmp_path / "experiments" / "study",
    )

    restored = SqliteIDEStore(store.path).get_run_outcome(run.id)
    assert restored == created
    assert restored.overall_state == "needs_attention"
    assert restored.failed_check_count == 2
    assert restored.unmet_deliverables == ("electron_density",)


def test_pending_plan_can_be_revised_and_replaced(
    tmp_path: Path, valid_spec: ExperimentSpec
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)
    first_prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    first = store.save_prepared_plan(
        run.id,
        first_prepared,
        plan_path=tmp_path / "experiments" / "study" / "PLAN.md",
        structured_plan_path=tmp_path / "experiments" / "study" / "plan.json",
    )

    revising = store.request_plan_revision(run.id, first.revision)
    store.transition_run(
        run.id,
        store.get_run(run.id).revision,
        RunState.RUNNING,
    )
    revised_spec = valid_spec.model_copy(update={"name": "Revised study"})
    revised_prepared = ExperimentEngine().prepare(revised_spec, "devsim")
    second = store.save_prepared_plan(
        run.id,
        revised_prepared,
        plan_path=tmp_path / "experiments" / "revised-study" / "PLAN.md",
        structured_plan_path=tmp_path / "experiments" / "revised-study" / "plan.json",
    )

    assert revising.status == "revision_requested"
    assert second.status == "pending"
    assert second.plan_digest == revised_prepared.plan_digest
    assert second.revision > first.revision


def test_approval_resolution_is_optimistic_and_persisted(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    approval = store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "install package",
        {"command": "pip install package"},
    )

    resolved = store.resolve_approval(approval.id, approval.revision, ApprovalDecision.APPROVE)

    assert resolved.decision is ApprovalDecision.APPROVE
    assert resolved.resolved_at is not None
    assert store.list_pending_approvals(conversation.id) == ()
    with pytest.raises(IDEStoreError, match="stale approval revision"):
        store.resolve_approval(approval.id, approval.revision, ApprovalDecision.DENY)


def test_permission_category_grant_is_scoped_to_one_run_and_persisted(
    tmp_path: Path,
) -> None:
    database = tmp_path / "ide.sqlite3"
    store = SqliteIDEStore(database)
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    first_run = store.create_run(conversation.id, conversation.id)
    approval = store.create_approval(
        first_run.id,
        "action-1",
        "terminal",
        "HIGH",
        "Agent Kronig wants to change Git history or send changes online.",
        {"command": "git push"},
        permission_category="git_mutation",
    )

    resolved = store.resolve_approval_with_grant(
        approval.id,
        approval.revision,
    )
    restored = SqliteIDEStore(database)

    assert resolved.decision is ApprovalDecision.APPROVE
    assert restored.list_run_permission_grants(first_run.id) == ("git_mutation",)
    second_run = restored.create_run(conversation.id, conversation.id)
    assert restored.list_run_permission_grants(second_run.id) == ()

    with pytest.raises(IDEStoreError, match="stale approval revision"):
        restored.resolve_approval_with_grant(approval.id, approval.revision)


@pytest.mark.parametrize(
    "terminal_state",
    [
        RunState.COMPLETED,
        RunState.FAILED,
        RunState.BLOCKED,
        RunState.CANCELLED,
    ],
)
def test_terminal_run_expires_permission_and_plan_consent(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
    terminal_state: RunState,
) -> None:
    store = SqliteIDEStore(tmp_path / f"{terminal_state.value}.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Research run")
    run = store.create_run(conversation.id, conversation.id)
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    pending = store.save_prepared_plan(
        run.id,
        prepared,
        plan_path=tmp_path / "experiments" / "study" / "PLAN.md",
        structured_plan_path=tmp_path / "experiments" / "study" / "plan.json",
    )
    store.approve_prepared_plan(
        run.id,
        pending.revision,
        pending.plan_digest,
        mode=PlanApprovalMode.UNATTENDED_LOCAL,
    )
    store.grant_run_permission(run.id, PermissionCategory.SIMULATION_EXECUTION)
    waiting = store.get_run(run.id)

    store.transition_run(run.id, waiting.revision, terminal_state)

    assert store.list_run_permission_grants(run.id) == ()
    expired = store.get_prepared_plan(run.id)
    assert expired.approval_mode is None


def test_broad_unrecognized_permission_cannot_be_granted_for_a_run(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    approval = store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "Agent Kronig wants to perform a higher-risk action.",
        {"command": "unknown-tool && rm -rf /tmp/output"},
    )

    with pytest.raises(IDEStoreError, match="cannot be granted"):
        store.resolve_approval_with_grant(approval.id, approval.revision)

    assert store.get_approval(approval.id).decision is None


def test_terminal_run_does_not_expose_stale_pending_approval(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "install package",
        {"command": "pip install package"},
    )
    waiting = store.get_run(run.id)
    store.transition_run(run.id, waiting.revision, RunState.CANCELLED)

    assert store.list_pending_approvals(conversation.id) == ()


def test_run_baseline_is_persisted_and_first_capture_wins(tmp_path: Path) -> None:
    database = tmp_path / "ide.sqlite3"
    store = SqliteIDEStore(database)
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    captured_at = datetime.now(UTC)
    first = WorkspaceBaseline(
        root=tmp_path.resolve(),
        captured_at=captured_at,
        files={
            "model.py": BaselineFile(
                path="model.py",
                size=4,
                mtime_ns=1,
                sha256="0" * 64,
                content="test",
            )
        },
    )
    later = first.model_copy(update={"files": {}})

    store.save_run_baseline(run.id, first)
    store.save_run_baseline(run.id, later)
    restored = SqliteIDEStore(database).get_run_baseline(run.id)

    assert restored == first


def test_terminal_change_manifest_is_immutable(tmp_path: Path) -> None:
    database = tmp_path / "ide.sqlite3"
    store = SqliteIDEStore(database)
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Agent task")
    run = store.create_run(conversation.id, conversation.id)
    now = datetime.now(UTC)
    first = WorkspaceChangeSet(
        run_id=run.id,
        baseline_captured_at=now,
        generated_at=now,
        baseline_truncated=False,
        files=(),
    )
    later = first.model_copy(update={"baseline_truncated": True})

    store.save_run_change_manifest(run.id, first)
    store.save_run_change_manifest(run.id, later)

    assert SqliteIDEStore(database).get_run_change_manifest(run.id) == first


def test_delete_conversation_tree_removes_only_owned_session_records(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "runtime" / "ide.sqlite3")
    events = EventFeed(store)
    conversations = ConversationService(store, events)
    workspaces = WorkspaceManager(store)
    first_root = tmp_path / "first-repository"
    second_root = tmp_path / "second-repository"
    first_root.mkdir()
    second_root.mkdir()
    repository_file = first_root / "result.json"
    repository_file.write_text('{"status":"valid"}', encoding="utf-8")
    first_workspace = workspaces.open(first_root)
    second_workspace = workspaces.open(second_root)
    first = conversations.create(first_workspace.id, "Ephemeral session")
    second = conversations.create(second_workspace.id, "Other session")
    message = conversations.add_user_message(first.id, "Run the experiment")
    conversations.add_user_message(second.id, "Preserve this session")
    run = store.create_run(first.id, first.id)
    store.create_prompt_preparation(run.id, "Run the experiment")
    approval = store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "Push the generated files",
        {"command": "git push"},
        permission_category="git_mutation",
    )
    store.resolve_approval_with_grant(approval.id, approval.revision)
    store.save_run_baseline(
        run.id,
        WorkspaceBaseline(
            root=first_root.resolve(),
            captured_at=datetime.now(UTC),
            files={},
        ),
    )
    store.save_run_change_manifest(
        run.id,
        WorkspaceChangeSet(
            run_id=run.id,
            baseline_captured_at=datetime.now(UTC),
            generated_at=datetime.now(UTC),
            baseline_truncated=False,
            files=(),
        ),
    )
    events.append(first.id, "technical_activity", {"run_id": str(run.id)})

    store.delete_conversation_tree(first.id)

    with pytest.raises(IDEStoreError):
        store.get_conversation(first.id)
    with pytest.raises(IDEStoreError):
        store.get_message(message.id)
    with pytest.raises(IDEStoreError):
        store.get_run(run.id)
    with pytest.raises(IDEStoreError):
        store.get_approval(approval.id)
    with pytest.raises(IDEStoreError):
        store.get_run_baseline(run.id)
    with pytest.raises(IDEStoreError):
        store.list_events_after(first.id, 0, 100)
    with pytest.raises(IDEStoreError):
        store.list_run_permission_grants(run.id)
    assert store.get_run_change_manifest(run.id) is None
    with sqlite3.connect(store.path) as connection:
        for table in ("conversation_messages", "ide_events", "agent_runs"):
            assert (
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE conversation_id = ?",
                    (str(first.id),),
                ).fetchone()[0]
                == 0
            )
        for table in (
            "approval_requests",
            "run_permission_grants",
            "run_change_baselines",
            "run_change_manifests",
        ):
            assert (
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE run_id = ?", (str(run.id),)
                ).fetchone()[0]
                == 0
            )
    assert store.get_conversation(second.id).workspace_id == second_workspace.id
    assert store.get_workspace(first_workspace.id).root == first_root.resolve()
    assert repository_file.read_text(encoding="utf-8") == '{"status":"valid"}'
