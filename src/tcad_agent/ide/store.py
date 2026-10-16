"""SQLite persistence for local IDE workspaces."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import JsonValue

from tcad_agent.experiments.models import PreparedExperiment
from tcad_agent.ide.migrations import migrate_schema
from tcad_agent.ide.models import (
    AgentRunRecord,
    ApprovalDecision,
    ApprovalRequestRecord,
    ConversationMessage,
    ConversationRecord,
    ConversationState,
    ExperimentResultRecord,
    GitSnapshot,
    IDEEvent,
    PermissionCategory,
    PlanApprovalMode,
    PreparedPlanRecord,
    RepositorySnapshot,
    RunOutcomeRecord,
    RunState,
    WorkspaceBaseline,
    WorkspaceChangeSet,
    WorkspaceRecord,
    is_run_grantable,
)
from tcad_agent.prompting.clarifications import bind_answers
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    CompiledAgentRequest,
    PreparationDecision,
    PromptPreparationRecord,
)

RUN_OWNED_TABLES = (
    "clarification_receipts",
    "approval_requests",
    "run_permission_grants",
    "run_change_baselines",
    "run_change_manifests",
    "prompt_preparations",
    "prepared_plans",
    "experiment_results",
    "run_outcomes",
)


class IDEStoreError(RuntimeError):
    pass


class ClarificationLimitError(IDEStoreError):
    pass


class WorkspaceNotFoundError(IDEStoreError):
    pass


class ConversationNotFoundError(IDEStoreError):
    pass


class MessageNotFoundError(IDEStoreError):
    pass


class SqliteIDEStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    canonical_root TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    git_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_opened_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id),
                    title TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ide_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    sdk_conversation_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approval_requests (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES agent_runs(id),
                    action_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    permission_category TEXT NOT NULL DEFAULT 'unrecognized_action',
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision TEXT,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation
                ON agent_runs(conversation_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_approvals_run_pending
                ON approval_requests(run_id, decision, created_at);

                CREATE TABLE IF NOT EXISTS run_permission_grants (
                    run_id TEXT NOT NULL REFERENCES agent_runs(id),
                    permission_category TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, permission_category)
                );

                CREATE TABLE IF NOT EXISTS run_change_baselines (
                    run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
                    baseline_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_change_manifests (
                    run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
                    manifest_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prompt_preparations (
                    run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
                    original_prompt TEXT NOT NULL,
                    answers_json TEXT NOT NULL,
                    decision_json TEXT,
                    compiled_request_json TEXT,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clarification_receipts (
                    run_id TEXT NOT NULL REFERENCES agent_runs(id),
                    question_revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, question_revision)
                );

                CREATE TABLE IF NOT EXISTS prepared_plans (
                    run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
                    plan_digest TEXT NOT NULL,
                    prepared_json TEXT NOT NULL,
                    plan_path TEXT NOT NULL,
                    structured_plan_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approval_mode TEXT,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS experiment_results (
                    run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
                    bundle_run_id TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    execution_state TEXT NOT NULL,
                    validation_state TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS run_outcomes (
                    run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
                    execution_state TEXT NOT NULL,
                    validation_state TEXT NOT NULL,
                    deliverable_state TEXT NOT NULL,
                    report_state TEXT NOT NULL,
                    overall_state TEXT NOT NULL,
                    failed_check_count INTEGER NOT NULL,
                    unmet_deliverables_json TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            migrate_schema(connection)

    def open_workspace(self, snapshot: RepositorySnapshot) -> WorkspaceRecord:
        now = datetime.now(UTC)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                INSERT INTO workspaces (
                    id,
                    canonical_root,
                    display_name,
                    git_json,
                    revision,
                    created_at,
                    last_opened_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(canonical_root) DO UPDATE SET
                    display_name = excluded.display_name,
                    git_json = excluded.git_json,
                    revision = workspaces.revision + 1,
                    last_opened_at = excluded.last_opened_at
                RETURNING *
                """,
                (
                    str(uuid4()),
                    str(snapshot.root),
                    snapshot.display_name,
                    snapshot.git.model_dump_json(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            ).fetchone()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        if row is None:
            raise IDEStoreError("workspace upsert returned no record")
        return self._workspace(row)

    def get_workspace(self, workspace_id: UUID) -> WorkspaceRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM workspaces WHERE id = ?", (str(workspace_id),)
            ).fetchone()
        if row is None:
            raise WorkspaceNotFoundError(f"workspace does not exist: {workspace_id}")
        return self._workspace(row)

    def list_workspaces(self) -> tuple[WorkspaceRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM workspaces
                ORDER BY last_opened_at DESC, id ASC
                """
            ).fetchall()
        return tuple(self._workspace(row) for row in rows)

    def save_run_baseline(
        self, run_id: UUID, baseline: WorkspaceBaseline
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO run_change_baselines (
                    run_id, baseline_json, created_at
                ) VALUES (?, ?, ?)
                """,
                (
                    str(run_id),
                    baseline.model_dump_json(),
                    baseline.captured_at.isoformat(),
                ),
            )

    def get_run_baseline(self, run_id: UUID) -> WorkspaceBaseline:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT baseline_json
                FROM run_change_baselines
                WHERE run_id = ?
                """,
                (str(run_id),),
            ).fetchone()
        if row is None:
            raise IDEStoreError(f"run baseline does not exist: {run_id}")
        return WorkspaceBaseline.model_validate_json(row["baseline_json"])

    def save_run_change_manifest(
        self, run_id: UUID, manifest: WorkspaceChangeSet
    ) -> None:
        """Persist the first terminal manifest as immutable run evidence."""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO run_change_manifests (
                    run_id, manifest_json, created_at
                ) VALUES (?, ?, ?)
                """,
                (
                    str(run_id),
                    manifest.model_dump_json(),
                    manifest.generated_at.isoformat(),
                ),
            )

    def get_run_change_manifest(
        self, run_id: UUID
    ) -> WorkspaceChangeSet | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT manifest_json
                FROM run_change_manifests
                WHERE run_id = ?
                """,
                (str(run_id),),
            ).fetchone()
        if row is None:
            return None
        return WorkspaceChangeSet.model_validate_json(row["manifest_json"])

    def create_conversation(
        self, workspace_id: UUID, title: str
    ) -> ConversationRecord:
        now = datetime.now(UTC)
        conversation_id = uuid4()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(conversation_id),
                    str(workspace_id),
                    title,
                    ConversationState.IDLE.value,
                    0,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return self.get_conversation(conversation_id)

    def get_conversation(self, conversation_id: UUID) -> ConversationRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (str(conversation_id),)
            ).fetchone()
        if row is None:
            raise ConversationNotFoundError(
                f"conversation does not exist: {conversation_id}"
            )
        return self._conversation(row)

    def list_conversations(
        self, workspace_id: UUID
    ) -> tuple[ConversationRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversations
                WHERE workspace_id = ?
                ORDER BY updated_at DESC, id ASC
                """,
                (str(workspace_id),),
            ).fetchall()
        return tuple(self._conversation(row) for row in rows)

    def delete_conversation_tree(self, conversation_id: UUID) -> None:
        """Delete one internal session and every record owned by it."""

        key = str(conversation_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT id FROM conversations WHERE id = ?", (key,)
            ).fetchone()
            if current is None:
                raise ConversationNotFoundError(
                    f"conversation does not exist: {conversation_id}"
                )
            run_ids = "SELECT id FROM agent_runs WHERE conversation_id = ?"
            for table in RUN_OWNED_TABLES:
                connection.execute(
                    f"DELETE FROM {table} WHERE run_id IN ({run_ids})", (key,)
                )
            connection.execute(
                "DELETE FROM agent_runs WHERE conversation_id = ?", (key,)
            )
            connection.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?", (key,)
            )
            connection.execute(
                "DELETE FROM ide_events WHERE conversation_id = ?", (key,)
            )
            connection.execute("DELETE FROM conversations WHERE id = ?", (key,))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def append_message(
        self,
        conversation_id: UUID,
        role: Literal["user", "assistant", "system"],
        content: str,
    ) -> ConversationMessage:
        now = datetime.now(UTC)
        message_id = uuid4()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT id FROM conversations WHERE id = ?", (str(conversation_id),)
            ).fetchone()
            if current is None:
                raise ConversationNotFoundError(
                    f"conversation does not exist: {conversation_id}"
                )
            connection.execute(
                """
                INSERT INTO conversation_messages VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(message_id),
                    str(conversation_id),
                    role,
                    content,
                    now.isoformat(),
                ),
            )
            connection.execute(
                """
                UPDATE conversations
                SET revision = revision + 1, updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), str(conversation_id)),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return ConversationMessage(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=now,
        )

    def list_messages(
        self, conversation_id: UUID
    ) -> tuple[ConversationMessage, ...]:
        self.get_conversation(conversation_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversation_messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (str(conversation_id),),
            ).fetchall()
        return tuple(self._message(row) for row in rows)

    def get_message(self, message_id: UUID) -> ConversationMessage:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_messages WHERE id = ?",
                (str(message_id),),
            ).fetchone()
        if row is None:
            raise MessageNotFoundError(f"message does not exist: {message_id}")
        return self._message(row)

    def create_run(
        self, conversation_id: UUID, sdk_conversation_id: UUID
    ) -> AgentRunRecord:
        self.get_conversation(conversation_id)
        now = datetime.now(UTC)
        run_id = uuid4()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    id, conversation_id, sdk_conversation_id, state, revision,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    str(run_id),
                    str(conversation_id),
                    str(sdk_conversation_id),
                    RunState.QUEUED.value,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        run = self.get_run(run_id)
        self.append_event(
            conversation_id,
            "run_created",
            {"run_id": str(run.id), "state": run.state.value},
        )
        return run

    def create_prompt_preparation(
        self, run_id: UUID, original_prompt: str
    ) -> PromptPreparationRecord:
        self.get_run(run_id)
        prompt = original_prompt.strip()
        if not prompt:
            raise IDEStoreError("prompt preparation requires a non-empty prompt")
        now = datetime.now(UTC)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO prompt_preparations (
                        run_id, original_prompt, answers_json, decision_json,
                        compiled_request_json, revision, created_at, updated_at
                    ) VALUES (?, ?, '[]', NULL, NULL, 0, ?, ?)
                    """,
                    (str(run_id), prompt, now.isoformat(), now.isoformat()),
                )
        except sqlite3.IntegrityError as error:
            raise IDEStoreError(
                f"prompt preparation already exists for run {run_id}"
            ) from error
        return self.get_prompt_preparation(run_id)

    def save_prepared_plan(
        self,
        run_id: UUID,
        prepared: PreparedExperiment,
        *,
        plan_path: Path,
        structured_plan_path: Path,
    ) -> PreparedPlanRecord:
        now = datetime.now(UTC)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute(
                "SELECT * FROM agent_runs WHERE id = ?", (str(run_id),)
            ).fetchone()
            if run is None:
                raise IDEStoreError(f"agent run does not exist: {run_id}")
            existing = connection.execute(
                "SELECT * FROM prepared_plans WHERE run_id = ?", (str(run_id),)
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO prepared_plans (
                        run_id, plan_digest, prepared_json, plan_path,
                        structured_plan_path, status, approval_mode, revision,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', NULL, 0, ?, ?)
                    """,
                    (
                        str(run_id),
                        prepared.plan_digest,
                        prepared.model_dump_json(),
                        str(plan_path.resolve()),
                        str(structured_plan_path.resolve()),
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            elif existing["status"] == "revision_requested":
                connection.execute(
                    """
                    UPDATE prepared_plans
                    SET plan_digest = ?, prepared_json = ?, plan_path = ?,
                        structured_plan_path = ?, status = 'pending',
                        approval_mode = NULL, revision = revision + 1,
                        updated_at = ?
                    WHERE run_id = ? AND revision = ?
                    """,
                    (
                        prepared.plan_digest,
                        prepared.model_dump_json(),
                        str(plan_path.resolve()),
                        str(structured_plan_path.resolve()),
                        now.isoformat(),
                        str(run_id),
                        existing["revision"],
                    ),
                )
            else:
                raise IDEStoreError(f"prepared plan already exists for run {run_id}")
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET state = ?, revision = revision + 1, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    RunState.WAITING_FOR_PLAN_APPROVAL.value,
                    now.isoformat(),
                    str(run_id),
                    run["revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise IDEStoreError(f"stale run revision for {run_id}")
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise IDEStoreError(f"prepared plan already exists for run {run_id}") from error
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        record = self.get_prepared_plan(run_id)
        run_record = self.get_run(run_id)
        self.append_event(
            run_record.conversation_id,
            "plan_ready",
            {
                "run_id": str(run_id),
                "plan_digest": prepared.plan_digest,
                "plan_path": str(record.plan_path),
                "revision": record.revision,
            },
        )
        return record

    def get_prepared_plan(self, run_id: UUID) -> PreparedPlanRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM prepared_plans WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        if row is None:
            raise IDEStoreError(f"prepared plan does not exist: {run_id}")
        return self._prepared_plan(row)

    def save_experiment_result(
        self,
        run_id: UUID,
        *,
        bundle_run_id: str,
        project_root: Path,
        execution_state: Literal["failed", "completed"],
        validation_state: Literal["passed", "needs_review", "failed"],
    ) -> ExperimentResultRecord:
        now = datetime.now(UTC)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO experiment_results (
                        run_id, bundle_run_id, project_root, execution_state,
                        validation_state, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(run_id),
                        bundle_run_id,
                        str(project_root.resolve()),
                        execution_state,
                        validation_state,
                        now.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise IDEStoreError(f"experiment result already exists for run {run_id}") from error
        return self.get_experiment_result(run_id)

    def get_experiment_result(self, run_id: UUID) -> ExperimentResultRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM experiment_results WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        if row is None:
            raise IDEStoreError(f"experiment result does not exist: {run_id}")
        return self._experiment_result(row)

    def list_experiment_results_for_workspace(
        self, workspace_id: UUID
    ) -> tuple[ExperimentResultRecord, ...]:
        self.get_workspace(workspace_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT experiment_results.*
                FROM experiment_results
                JOIN agent_runs ON agent_runs.id = experiment_results.run_id
                JOIN conversations ON conversations.id = agent_runs.conversation_id
                WHERE conversations.workspace_id = ?
                ORDER BY experiment_results.created_at DESC,
                         experiment_results.run_id DESC
                """,
                (str(workspace_id),),
            ).fetchall()
        return tuple(self._experiment_result(row) for row in rows)

    def save_run_outcome(
        self,
        run_id: UUID,
        *,
        execution_state: Literal["failed", "completed"],
        validation_state: Literal["passed", "needs_review", "failed"],
        deliverable_state: Literal["complete", "incomplete"],
        report_state: Literal["complete", "missing", "failed"],
        overall_state: Literal["completed", "needs_attention", "failed"],
        failed_check_count: int,
        unmet_deliverables: tuple[str, ...],
        project_root: Path,
    ) -> RunOutcomeRecord:
        self.get_run(run_id)
        now = datetime.now(UTC)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_outcomes (
                    run_id, execution_state, validation_state, deliverable_state,
                    report_state, overall_state, failed_check_count,
                    unmet_deliverables_json, project_root, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    execution_state = excluded.execution_state,
                    validation_state = excluded.validation_state,
                    deliverable_state = excluded.deliverable_state,
                    report_state = excluded.report_state,
                    overall_state = excluded.overall_state,
                    failed_check_count = excluded.failed_check_count,
                    unmet_deliverables_json = excluded.unmet_deliverables_json,
                    project_root = excluded.project_root,
                    updated_at = excluded.updated_at
                """,
                (
                    str(run_id),
                    execution_state,
                    validation_state,
                    deliverable_state,
                    report_state,
                    overall_state,
                    failed_check_count,
                    json.dumps(unmet_deliverables),
                    str(project_root.resolve()),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return self.get_run_outcome(run_id)

    def get_run_outcome(self, run_id: UUID) -> RunOutcomeRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM run_outcomes WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        if row is None:
            raise IDEStoreError(f"run outcome does not exist: {run_id}")
        return self._run_outcome(row)

    def find_run_outcome(self, run_id: UUID) -> RunOutcomeRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM run_outcomes WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        return self._run_outcome(row) if row is not None else None

    def approve_prepared_plan(
        self,
        run_id: UUID,
        expected_revision: int,
        plan_digest: str,
        *,
        mode: PlanApprovalMode,
    ) -> PreparedPlanRecord:
        now = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE prepared_plans
                SET status = 'approved', approval_mode = ?,
                    revision = revision + 1, updated_at = ?
                WHERE run_id = ? AND revision = ? AND plan_digest = ?
                  AND status = 'pending'
                """,
                (
                    mode.value,
                    now.isoformat(),
                    str(run_id),
                    expected_revision,
                    plan_digest,
                ),
            )
        if cursor.rowcount != 1:
            raise IDEStoreError(f"stale or already resolved prepared plan for {run_id}")
        return self.get_prepared_plan(run_id)

    def consume_prepared_plan(self, run_id: UUID, plan_digest: str) -> PreparedPlanRecord:
        now = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE prepared_plans
                SET status = 'consumed', revision = revision + 1, updated_at = ?
                WHERE run_id = ? AND plan_digest = ? AND status = 'approved'
                """,
                (now.isoformat(), str(run_id), plan_digest),
            )
        if cursor.rowcount != 1:
            raise IDEStoreError(
                f"prepared plan is not approved or was already executed for {run_id}"
            )
        return self.get_prepared_plan(run_id)

    def request_plan_revision(
        self, run_id: UUID, expected_revision: int
    ) -> PreparedPlanRecord:
        now = datetime.now(UTC)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE prepared_plans
                SET status = 'revision_requested', revision = revision + 1,
                    updated_at = ?
                WHERE run_id = ? AND revision = ? AND status = 'pending'
                """,
                (now.isoformat(), str(run_id), expected_revision),
            )
            if cursor.rowcount != 1:
                raise IDEStoreError(f"stale or resolved prepared plan for {run_id}")
            run = connection.execute(
                "SELECT * FROM agent_runs WHERE id = ?", (str(run_id),)
            ).fetchone()
            if run is None:
                raise IDEStoreError(f"agent run does not exist: {run_id}")
            run_cursor = connection.execute(
                """
                UPDATE agent_runs
                SET state = ?, revision = revision + 1, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    RunState.QUEUED.value,
                    now.isoformat(),
                    str(run_id),
                    run["revision"],
                ),
            )
            if run_cursor.rowcount != 1:
                raise IDEStoreError(f"stale run revision for {run_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_prepared_plan(run_id)

    def pending_plan_for_workspace(
        self, workspace_id: UUID
    ) -> PreparedPlanRecord | None:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT prepared_plans.*
                FROM prepared_plans
                JOIN agent_runs ON agent_runs.id = prepared_plans.run_id
                JOIN conversations ON conversations.id = agent_runs.conversation_id
                WHERE conversations.workspace_id = ?
                  AND prepared_plans.status = 'pending'
                ORDER BY prepared_plans.created_at DESC
                """,
                (str(workspace_id),),
            ).fetchall()
        if len(rows) > 1:
            raise IDEStoreError("more than one prepared plan is pending")
        return self._prepared_plan(rows[0]) if rows else None

    def get_prompt_preparation(self, run_id: UUID) -> PromptPreparationRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM prompt_preparations WHERE run_id = ?",
                (str(run_id),),
            ).fetchone()
        if row is None:
            raise IDEStoreError(f"prompt preparation does not exist: {run_id}")
        return self._prompt_preparation(row)

    def clarification_decisions(self, run_id: UUID) -> tuple[PreparationDecision, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT decision_json FROM clarification_receipts WHERE run_id = ? "
                "ORDER BY question_revision", (str(run_id),),
            ).fetchall()
        return tuple(PreparationDecision.model_validate_json(row[0]) for row in rows)

    def accept_clarification(
        self, run_id: UUID, expected_revision: int, answers: tuple[ClarificationAnswer, ...],
        *, max_rounds: int = 8,
    ) -> tuple[PromptPreparationRecord, bool]:
        """Atomically accept once, bind provenance and queue work; exact replay is read-only."""
        payload = json.dumps(sorted(
            (answer.question_id, answer.answer.strip()) for answer in answers
        ), separators=(",", ":"))
        connection = self._connect()
        accepted = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            receipt = connection.execute(
                "SELECT payload_json, decision_json FROM clarification_receipts "
                "WHERE run_id = ? AND question_revision = ?", (str(run_id), expected_revision),
            ).fetchone()
            if receipt is not None:
                if payload != receipt["payload_json"]:
                    raise IDEStoreError("stale clarification revision contains different answers")
                decision = PreparationDecision.model_validate_json(receipt["decision_json"])
                bind_answers(answers, decision.questions, expected_revision)
            else:
                row = connection.execute(
                    "SELECT * FROM prompt_preparations WHERE run_id = ?", (str(run_id),)
                ).fetchone()
                run = connection.execute(
                    "SELECT state FROM agent_runs WHERE id = ?", (str(run_id),)
                ).fetchone()
                if row is None or row["revision"] != expected_revision:
                    raise IDEStoreError("stale prompt preparation revision")
                if run is None or run["state"] != RunState.WAITING_FOR_USER.value:
                    raise IDEStoreError("stale clarification: run is no longer waiting for answers")
                record = self._prompt_preparation(row)
                decision = record.decision
                if decision is None or decision.status != "clarification":
                    raise IDEStoreError("run has no active clarification questions")
                ids = [answer.question_id for answer in answers]
                if any(not answer.answer.strip() for answer in answers):
                    raise IDEStoreError("clarification answers must be non-empty")
                known = {question.id for question in decision.questions}
                required = {question.id for question in decision.questions if question.required}
                if (len(set(ids)) != len(ids) or not set(ids).issubset(known)
                        or not required.issubset(ids)):
                    raise IDEStoreError("clarification answers do not match the active questions")
                rounds = connection.execute(
                    "SELECT COUNT(*) FROM clarification_receipts WHERE run_id = ?", (str(run_id),)
                ).fetchone()[0]
                if rounds >= max_rounds:
                    raise ClarificationLimitError(
                        "The clarification round limit was reached. No further model call was "
                        "started. Your accepted answers are retained; revise the request."
                    )
                combined = (
                    *record.answers, *bind_answers(answers, decision.questions, expected_revision)
                )
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    "UPDATE prompt_preparations SET answers_json = ?, revision = revision + 1, "
                    "updated_at = ? WHERE run_id = ? AND revision = ?",
                    (json.dumps([answer.model_dump(mode="json") for answer in combined]), now,
                     str(run_id), expected_revision),
                )
                connection.execute(
                    "INSERT INTO clarification_receipts VALUES (?, ?, ?, ?)",
                    (str(run_id), expected_revision, payload, decision.model_dump_json()),
                )
                connection.execute(
                    "UPDATE agent_runs SET state = ?, revision = revision + 1, updated_at = ? "
                    "WHERE id = ?", (RunState.QUEUED.value, now, str(run_id)),
                )
                accepted = True
            connection.commit()
        except (ValueError, KeyError) as exc:
            connection.rollback()
            raise IDEStoreError(f"Invalid clarification binding: {exc}") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_prompt_preparation(run_id), accepted

    def update_prompt_preparation(
        self,
        run_id: UUID,
        expected_revision: int,
        *,
        answers: tuple[ClarificationAnswer, ...],
        decision: PreparationDecision | None,
        compiled_request: CompiledAgentRequest | None,
    ) -> PromptPreparationRecord:
        now = datetime.now(UTC)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM prompt_preparations WHERE run_id = ?",
                (str(run_id),),
            ).fetchone()
            if row is None:
                raise IDEStoreError(f"prompt preparation does not exist: {run_id}")
            if row["compiled_request_json"] is not None:
                raise IDEStoreError("compiled prompt preparation is immutable")
            cursor = connection.execute(
                """
                UPDATE prompt_preparations
                SET answers_json = ?, decision_json = ?, compiled_request_json = ?,
                    revision = revision + 1, updated_at = ?
                WHERE run_id = ? AND revision = ?
                """,
                (
                    json.dumps(
                        [answer.model_dump(mode="json") for answer in answers],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    decision.model_dump_json() if decision is not None else None,
                    (
                        compiled_request.model_dump_json()
                        if compiled_request is not None
                        else None
                    ),
                    now.isoformat(),
                    str(run_id),
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise IDEStoreError(f"stale prompt preparation revision for {run_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_prompt_preparation(run_id)

    def get_run(self, run_id: UUID) -> AgentRunRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE id = ?", (str(run_id),)
            ).fetchone()
        if row is None:
            raise IDEStoreError(f"agent run does not exist: {run_id}")
        return self._run(row)

    def list_runs(self, conversation_id: UUID) -> tuple[AgentRunRecord, ...]:
        self.get_conversation(conversation_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agent_runs
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (str(conversation_id),),
            ).fetchall()
        return tuple(self._run(row) for row in rows)

    def list_runs_for_workspace(
        self, workspace_id: UUID
    ) -> tuple[AgentRunRecord, ...]:
        self.get_workspace(workspace_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT agent_runs.*
                FROM agent_runs
                JOIN conversations
                  ON conversations.id = agent_runs.conversation_id
                WHERE conversations.workspace_id = ?
                ORDER BY agent_runs.created_at ASC, agent_runs.id ASC
                """,
                (str(workspace_id),),
            ).fetchall()
        return tuple(self._run(row) for row in rows)

    def list_runs_in_states(
        self, states: set[RunState]
    ) -> tuple[AgentRunRecord, ...]:
        if not states:
            return ()
        values = tuple(state.value for state in states)
        placeholders = ",".join("?" for _ in values)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM agent_runs
                WHERE state IN ({placeholders})
                ORDER BY created_at ASC, id ASC
                """,
                values,
            ).fetchall()
        return tuple(self._run(row) for row in rows)

    def transition_run(
        self, run_id: UUID, expected_revision: int, state: RunState
    ) -> AgentRunRecord:
        now = datetime.now(UTC)
        terminal = state in {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.BLOCKED,
            RunState.CANCELLED,
        }
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET state = ?, revision = revision + 1, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (state.value, now.isoformat(), str(run_id), expected_revision),
            )
            if cursor.rowcount != 1:
                raise IDEStoreError(f"stale run revision for {run_id}")
            if terminal:
                connection.execute(
                    "DELETE FROM run_permission_grants WHERE run_id = ?",
                    (str(run_id),),
                )
                connection.execute(
                    """
                    UPDATE prepared_plans
                    SET approval_mode = NULL, revision = revision + 1, updated_at = ?
                    WHERE run_id = ? AND approval_mode IS NOT NULL
                    """,
                    (now.isoformat(), str(run_id)),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        run = self.get_run(run_id)
        self.append_event(
            run.conversation_id,
            "run_state_changed",
            {"run_id": str(run.id), "state": run.state.value},
        )
        return run

    def create_approval(
        self,
        run_id: UUID,
        action_id: str,
        tool_name: str,
        risk: str,
        summary: str,
        payload: dict[str, JsonValue],
        *,
        permission_category: PermissionCategory | str = (
            PermissionCategory.UNRECOGNIZED_ACTION
        ),
    ) -> ApprovalRequestRecord:
        payload_json = self._payload_json(payload)
        now = datetime.now(UTC)
        approval_id = uuid4()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run_row = connection.execute(
                "SELECT * FROM agent_runs WHERE id = ?", (str(run_id),)
            ).fetchone()
            if run_row is None:
                raise IDEStoreError(f"agent run does not exist: {run_id}")
            connection.execute(
                """
                INSERT INTO approval_requests (
                    id, run_id, action_id, tool_name, risk, permission_category, summary,
                    payload_json, decision, revision, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, NULL)
                """,
                (
                    str(approval_id),
                    str(run_id),
                    action_id,
                    tool_name,
                    risk,
                    PermissionCategory(permission_category).value,
                    summary,
                    payload_json,
                    now.isoformat(),
                ),
            )
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET state = ?, revision = revision + 1, updated_at = ?
                WHERE id = ? AND revision = ?
                """,
                (
                    RunState.WAITING_FOR_APPROVAL.value,
                    now.isoformat(),
                    str(run_id),
                    run_row["revision"],
                ),
            )
            if cursor.rowcount != 1:
                raise IDEStoreError(f"stale run revision for {run_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        approval = self.get_approval(approval_id)
        run = self.get_run(run_id)
        self.append_event(
            run.conversation_id,
            "approval_requested",
            {
                "approval_id": str(approval.id),
                "run_id": str(run_id),
                "risk": approval.risk,
                "permission_category": approval.permission_category.value,
                "summary": approval.summary,
                "tool_name": approval.tool_name,
            },
        )
        return approval

    def list_run_permission_grants(self, run_id: UUID) -> tuple[str, ...]:
        self.get_run(run_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT permission_category
                FROM run_permission_grants
                WHERE run_id = ?
                ORDER BY permission_category ASC
                """,
                (str(run_id),),
            ).fetchall()
        return tuple(row["permission_category"] for row in rows)

    def grant_run_permission(
        self, run_id: UUID, category: PermissionCategory
    ) -> None:
        if not is_run_grantable(category):
            raise IDEStoreError(
                f"permission category cannot be granted for a run: {category.value}"
            )
        self.get_run(run_id)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO run_permission_grants (
                    run_id, permission_category, created_at
                ) VALUES (?, ?, ?)
                """,
                (str(run_id), category.value, datetime.now(UTC).isoformat()),
            )

    def resolve_approval_with_grant(
        self,
        approval_id: UUID,
        expected_revision: int,
    ) -> ApprovalRequestRecord:
        """Approve one action and grant its category for the same run atomically."""

        now = datetime.now(UTC)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM approval_requests WHERE id = ?",
                (str(approval_id),),
            ).fetchone()
            if (
                row is None
                or row["revision"] != expected_revision
                or row["decision"] is not None
            ):
                raise IDEStoreError(f"stale approval revision for {approval_id}")
            category = PermissionCategory(row["permission_category"])
            if not is_run_grantable(category):
                raise IDEStoreError(
                    f"permission category cannot be granted for a run: {category.value}"
                )
            matching_rows = connection.execute(
                """
                SELECT id FROM approval_requests
                WHERE run_id = ? AND permission_category = ? AND decision IS NULL
                ORDER BY created_at ASC, id ASC
                """,
                (row["run_id"], row["permission_category"]),
            ).fetchall()
            cursor = connection.execute(
                """
                UPDATE approval_requests
                SET decision = ?, revision = revision + 1, resolved_at = ?
                WHERE run_id = ? AND permission_category = ? AND decision IS NULL
                """,
                (
                    ApprovalDecision.APPROVE.value,
                    now.isoformat(),
                    row["run_id"],
                    row["permission_category"],
                ),
            )
            if cursor.rowcount != len(matching_rows):
                raise IDEStoreError(f"stale approval revision for {approval_id}")
            connection.execute(
                """
                INSERT OR IGNORE INTO run_permission_grants (
                    run_id, permission_category, created_at
                ) VALUES (?, ?, ?)
                """,
                (row["run_id"], row["permission_category"], now.isoformat()),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        approval = self.get_approval(approval_id)
        run = self.get_run(approval.run_id)
        self.append_event(
            run.conversation_id,
            "permission_grant_created",
            {
                "approval_id": str(approval.id),
                "permission_category": approval.permission_category.value,
                "run_id": str(run.id),
                "scope": "run",
            },
        )
        for matching in matching_rows:
            self.append_event(
                run.conversation_id,
                "approval_resolved",
                {
                    "approval_id": matching["id"],
                    "decision": ApprovalDecision.APPROVE.value,
                    "permission_category": approval.permission_category.value,
                    "run_id": str(run.id),
                },
            )
        return approval

    def resolve_approval_batch(
        self,
        approval_id: UUID,
        expected_revision: int,
        decision: ApprovalDecision,
    ) -> tuple[ApprovalRequestRecord, ...]:
        """Resolve the complete pending SDK action batch anchored by one approval."""

        now = datetime.now(UTC)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            anchor = connection.execute(
                "SELECT * FROM approval_requests WHERE id = ?",
                (str(approval_id),),
            ).fetchone()
            if (
                anchor is None
                or anchor["revision"] != expected_revision
                or anchor["decision"] is not None
            ):
                raise IDEStoreError(f"stale approval revision for {approval_id}")
            rows = connection.execute(
                """
                SELECT id FROM approval_requests
                WHERE run_id = ? AND decision IS NULL
                ORDER BY created_at ASC, id ASC
                """,
                (anchor["run_id"],),
            ).fetchall()
            cursor = connection.execute(
                """
                UPDATE approval_requests
                SET decision = ?, revision = revision + 1, resolved_at = ?
                WHERE run_id = ? AND decision IS NULL
                """,
                (decision.value, now.isoformat(), anchor["run_id"]),
            )
            if cursor.rowcount != len(rows):
                raise IDEStoreError(f"stale approval batch for {approval_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        approvals = tuple(self.get_approval(UUID(row["id"])) for row in rows)
        run = self.get_run(approvals[0].run_id)
        for approval in approvals:
            self.append_event(
                run.conversation_id,
                "approval_resolved",
                {
                    "approval_id": str(approval.id),
                    "decision": decision.value,
                    "run_id": str(run.id),
                },
            )
        return approvals

    def get_approval(self, approval_id: UUID) -> ApprovalRequestRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM approval_requests WHERE id = ?", (str(approval_id),)
            ).fetchone()
        if row is None:
            raise IDEStoreError(f"approval request does not exist: {approval_id}")
        return self._approval(row)

    def list_pending_approvals(
        self, conversation_id: UUID
    ) -> tuple[ApprovalRequestRecord, ...]:
        self.get_conversation(conversation_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT approval_requests.*
                FROM approval_requests
                JOIN agent_runs ON agent_runs.id = approval_requests.run_id
                WHERE agent_runs.conversation_id = ?
                  AND approval_requests.decision IS NULL
                  AND agent_runs.state = ?
                ORDER BY approval_requests.created_at ASC, approval_requests.id ASC
                """,
                (str(conversation_id), RunState.WAITING_FOR_APPROVAL.value),
            ).fetchall()
        return tuple(self._approval(row) for row in rows)

    def resolve_approval(
        self,
        approval_id: UUID,
        expected_revision: int,
        decision: ApprovalDecision,
    ) -> ApprovalRequestRecord:
        now = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE approval_requests
                SET decision = ?, revision = revision + 1, resolved_at = ?
                WHERE id = ? AND revision = ? AND decision IS NULL
                """,
                (
                    decision.value,
                    now.isoformat(),
                    str(approval_id),
                    expected_revision,
                ),
            )
        if cursor.rowcount != 1:
            raise IDEStoreError(f"stale approval revision for {approval_id}")
        approval = self.get_approval(approval_id)
        run = self.get_run(approval.run_id)
        self.append_event(
            run.conversation_id,
            "approval_resolved",
            {
                "approval_id": str(approval.id),
                "decision": decision.value,
                "run_id": str(run.id),
            },
        )
        return approval

    def append_event(
        self,
        conversation_id: UUID,
        kind: str,
        payload: dict[str, JsonValue],
    ) -> IDEEvent:
        self.get_conversation(conversation_id)
        now = datetime.now(UTC)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ide_events (
                    conversation_id, kind, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    str(conversation_id),
                    kind,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    now.isoformat(),
                ),
            )
            event_id = cursor.lastrowid
        if event_id is None:
            raise IDEStoreError("event insert returned no identifier")
        return IDEEvent(
            id=event_id,
            conversation_id=conversation_id,
            kind=kind,
            payload=payload,
            created_at=now,
        )

    def list_events_after(
        self, conversation_id: UUID, after_id: int, limit: int
    ) -> tuple[IDEEvent, ...]:
        self.get_conversation(conversation_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM ide_events
                WHERE conversation_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (str(conversation_id), after_id, limit),
            ).fetchall()
        return tuple(self._event(row) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _workspace(row: sqlite3.Row) -> WorkspaceRecord:
        return WorkspaceRecord(
            id=UUID(row["id"]),
            root=Path(row["canonical_root"]),
            display_name=row["display_name"],
            git=GitSnapshot.model_validate_json(row["git_json"]),
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_opened_at=datetime.fromisoformat(row["last_opened_at"]),
        )

    @staticmethod
    def _conversation(row: sqlite3.Row) -> ConversationRecord:
        return ConversationRecord(
            id=UUID(row["id"]),
            workspace_id=UUID(row["workspace_id"]),
            title=row["title"],
            state=ConversationState(row["state"]),
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _message(row: sqlite3.Row) -> ConversationMessage:
        role = cast(Literal["user", "assistant", "system"], row["role"])
        return ConversationMessage(
            id=UUID(row["id"]),
            conversation_id=UUID(row["conversation_id"]),
            role=role,
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _event(row: sqlite3.Row) -> IDEEvent:
        payload = cast(dict[str, JsonValue], json.loads(row["payload_json"]))
        return IDEEvent(
            id=row["id"],
            conversation_id=UUID(row["conversation_id"]),
            kind=row["kind"],
            payload=payload,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _run(row: sqlite3.Row) -> AgentRunRecord:
        return AgentRunRecord(
            id=UUID(row["id"]),
            conversation_id=UUID(row["conversation_id"]),
            sdk_conversation_id=UUID(row["sdk_conversation_id"]),
            state=RunState(row["state"]),
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _approval(row: sqlite3.Row) -> ApprovalRequestRecord:
        decision = row["decision"]
        return ApprovalRequestRecord(
            id=UUID(row["id"]),
            run_id=UUID(row["run_id"]),
            action_id=row["action_id"],
            tool_name=row["tool_name"],
            risk=row["risk"],
            permission_category=PermissionCategory(row["permission_category"]),
            summary=row["summary"],
            payload=cast(dict[str, JsonValue], json.loads(row["payload_json"])),
            decision=ApprovalDecision(decision) if decision is not None else None,
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=(
                datetime.fromisoformat(row["resolved_at"])
                if row["resolved_at"] is not None
                else None
            ),
        )

    @staticmethod
    def _prompt_preparation(row: sqlite3.Row) -> PromptPreparationRecord:
        answers = tuple(
            ClarificationAnswer.model_validate(item)
            for item in json.loads(row["answers_json"])
        )
        decision = row["decision_json"]
        compiled_request = row["compiled_request_json"]
        return PromptPreparationRecord(
            run_id=UUID(row["run_id"]),
            original_prompt=row["original_prompt"],
            answers=answers,
            decision=(
                PreparationDecision.model_validate_json(decision)
                if decision is not None
                else None
            ),
            compiled_request=(
                CompiledAgentRequest.model_validate_json(compiled_request)
                if compiled_request is not None
                else None
            ),
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _prepared_plan(row: sqlite3.Row) -> PreparedPlanRecord:
        mode = row["approval_mode"]
        return PreparedPlanRecord(
            run_id=UUID(row["run_id"]),
            plan_digest=row["plan_digest"],
            prepared=cast(dict[str, JsonValue], json.loads(row["prepared_json"])),
            plan_path=Path(row["plan_path"]),
            structured_plan_path=Path(row["structured_plan_path"]),
            status=row["status"],
            approval_mode=PlanApprovalMode(mode) if mode is not None else None,
            revision=row["revision"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _experiment_result(row: sqlite3.Row) -> ExperimentResultRecord:
        return ExperimentResultRecord(
            run_id=UUID(row["run_id"]),
            bundle_run_id=row["bundle_run_id"],
            project_root=Path(row["project_root"]),
            execution_state=row["execution_state"],
            validation_state=row["validation_state"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _run_outcome(row: sqlite3.Row) -> RunOutcomeRecord:
        return RunOutcomeRecord(
            run_id=UUID(row["run_id"]),
            execution_state=row["execution_state"],
            validation_state=row["validation_state"],
            deliverable_state=row["deliverable_state"],
            report_state=row["report_state"],
            overall_state=row["overall_state"],
            failed_check_count=row["failed_check_count"],
            unmet_deliverables=tuple(json.loads(row["unmet_deliverables_json"])),
            project_root=Path(row["project_root"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _payload_json(payload: dict[str, JsonValue]) -> str:
        try:
            encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise IDEStoreError("approval payload must be JSON-safe") from error
        if len(encoded.encode("utf-8")) > 16_000:
            raise IDEStoreError("approval payload must not exceed 16000 bytes")
        return encoded
