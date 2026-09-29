"""Persistent background supervision for repository-scoped OpenHands runs."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from openhands.sdk.conversation import ConversationExecutionStatus
from openhands.sdk.event import Event

from tcad_agent.agent.events import AgentEventBridge, safe_event_text
from tcad_agent.ide.changes import WorkspaceChangeTracker, attribute_changes
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import (
    AgentRunRecord,
    ApprovalDecision,
    PermissionCategory,
    RunState,
    WorkspaceBaseline,
)
from tcad_agent.ide.store import IDEStoreError, SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.prompting.models import ClarificationAnswer
from tcad_agent.prompting.service import PromptPreparationService


class AgentRunConflictError(IDEStoreError):
    """Raised when a workspace already has a write-capable active run."""


class RuntimeState(Protocol):
    execution_status: ConversationExecutionStatus


class RuntimeConversation(Protocol):
    id: UUID
    state: RuntimeState

    def send_message(self, message: str, sender: str | None = None) -> None: ...

    def run(self) -> None: ...

    def pause(self) -> None: ...

    def interrupt(self) -> None: ...

    def reject_pending_actions(self, reason: str = "User rejected") -> None: ...


class RuntimeFactory(Protocol):
    def create(
        self,
        workspace: Path,
        conversation_id: UUID,
        callback: Callable[[Event], None],
    ) -> RuntimeConversation: ...


class SupervisorServices(Protocol):
    @property
    def store(self) -> SqliteIDEStore: ...

    @property
    def events(self) -> EventFeed: ...

    @property
    def workspaces(self) -> WorkspaceManager: ...

    @property
    def conversations(self) -> ConversationService: ...

    @property
    def runtime_root(self) -> Path: ...

    @property
    def changes(self) -> WorkspaceChangeTracker: ...


_ACTIVE_STATES = {
    RunState.QUEUED,
    RunState.RUNNING,
    RunState.WAITING_FOR_APPROVAL,
    RunState.WAITING_FOR_USER,
    RunState.PAUSED,
}


class AgentSupervisor:
    """Own background agent threads and keep the database as source of truth."""

    def __init__(
        self,
        services: SupervisorServices,
        runtime: RuntimeFactory,
        *,
        preparation: PromptPreparationService | None = None,
    ) -> None:
        self.services = services
        self.runtime_factory = runtime
        self.preparation = preparation
        self._guard = threading.RLock()
        self._threads: dict[UUID, threading.Thread] = {}
        self._runtimes: dict[UUID, RuntimeConversation] = {}
        self._permission_grants: dict[UUID, set[PermissionCategory]] = {}
        self._workspace_locks: dict[Path, threading.Lock] = {}
        self._recover_interrupted_runs()

    def start(
        self,
        conversation_id: UUID,
        prompt: str,
        *,
        persist_message: bool = True,
    ) -> AgentRunRecord:
        conversation = self.services.conversations.get(conversation_id)
        workspace = self.services.workspaces.get(conversation.workspace_id)
        with self._guard:
            if any(
                run.state in _ACTIVE_STATES
                for run in self.services.store.list_runs_for_workspace(workspace.id)
            ):
                raise AgentRunConflictError(
                    "the workspace already has an active agent run"
                )
            if persist_message:
                self.services.conversations.add_user_message(conversation_id, prompt)
            run = self.services.store.create_run(conversation_id, conversation_id)
            baseline_warning: str | None = None
            try:
                tracker = getattr(self.services, "changes", WorkspaceChangeTracker())
                baseline = tracker.capture(workspace.root)
            except Exception as error:
                baseline_warning = safe_event_text(error)
                baseline = WorkspaceBaseline(
                    root=workspace.root,
                    captured_at=datetime.now(UTC),
                    truncated=True,
                    files={},
                )
            self.services.store.save_run_baseline(run.id, baseline)
            if baseline_warning is not None:
                self.services.events.append(
                    conversation_id,
                    "change_baseline_warning",
                    {"run_id": str(run.id), "detail": baseline_warning},
                )
            if self.preparation is not None:
                self.services.store.create_prompt_preparation(run.id, prompt)
                self.services.events.append(
                    conversation_id,
                    "prompt_preparation_started",
                    {"run_id": str(run.id), "phase": "understanding_request"},
                )
                self._launch_preparation(run.id, workspace.root)
                return run
            try:
                return self._begin_execution(run, workspace.root, prompt)
            except Exception as error:
                failed = self._transition(run.id, RunState.FAILED)
                self.services.events.append(
                    failed.conversation_id,
                    "run_failed",
                    {"run_id": str(run.id), "detail": safe_event_text(error)},
                )
                raise

    def answer_clarification(
        self,
        run_id: UUID,
        expected_revision: int,
        answers: tuple[ClarificationAnswer, ...],
    ) -> AgentRunRecord:
        if self.preparation is None:
            raise IDEStoreError("prompt preparation is not configured")
        run = self.services.store.get_run(run_id)
        if run.state is not RunState.WAITING_FOR_USER:
            raise IDEStoreError("run is not waiting for clarification")
        preparation = self.services.store.get_prompt_preparation(run_id)
        if preparation.revision != expected_revision:
            raise IDEStoreError(f"stale prompt preparation revision for {run_id}")
        decision = preparation.decision
        if decision is None or decision.status != "clarification":
            raise IDEStoreError("run has no active clarification questions")
        by_id = {answer.question_id: answer for answer in answers}
        if len(by_id) != len(answers):
            raise IDEStoreError("clarification answers must have unique question ids")
        known = {question.id for question in decision.questions}
        required = {question.id for question in decision.questions if question.required}
        if not set(by_id).issubset(known) or not required.issubset(by_id):
            raise IDEStoreError("clarification answers do not match the active questions")
        combined = (*preparation.answers, *answers)
        updated = self.services.store.update_prompt_preparation(
            run_id,
            expected_revision,
            answers=combined,
            decision=None,
            compiled_request=None,
        )
        rendered = ["Clarification answers"]
        question_by_id = {question.id: question for question in decision.questions}
        for answer in answers:
            rendered.extend(
                (f"- {question_by_id[answer.question_id].prompt}", f"  {answer.answer}")
            )
        self.services.conversations.add_user_message(
            run.conversation_id, "\n".join(rendered)
        )
        queued = self._transition(run_id, RunState.QUEUED)
        self.services.events.append(
            run.conversation_id,
            "clarification_answered",
            {
                "run_id": str(run_id),
                "answer_count": len(answers),
                "preparation_revision": updated.revision,
            },
        )
        conversation = self.services.conversations.get(run.conversation_id)
        workspace = self.services.workspaces.get(conversation.workspace_id)
        self._launch_preparation(run_id, workspace.root)
        return queued

    def approve(self, approval_id: UUID, expected_revision: int) -> AgentRunRecord:
        approval = self.services.store.resolve_approval(
            approval_id, expected_revision, ApprovalDecision.APPROVE
        )
        return self._continue_if_ready(approval.run_id)

    def approve_category(
        self, approval_id: UUID, expected_revision: int
    ) -> AgentRunRecord:
        approval = self.services.store.resolve_approval_with_grant(
            approval_id, expected_revision
        )
        self._grants_for(approval.run_id).add(approval.permission_category)
        return self._continue_if_ready(approval.run_id)

    def deny(
        self, approval_id: UUID, expected_revision: int, reason: str
    ) -> AgentRunRecord:
        approvals = self.services.store.resolve_approval_batch(
            approval_id, expected_revision, ApprovalDecision.DENY
        )
        approval = approvals[0]
        runtime = self._runtime_for(approval.run_id)
        runtime.reject_pending_actions(safe_event_text(reason))
        return self._continue(approval.run_id, runtime=runtime)

    def _continue_if_ready(self, run_id: UUID) -> AgentRunRecord:
        run = self.services.store.get_run(run_id)
        pending = self.services.store.list_pending_approvals(run.conversation_id)
        if any(approval.run_id == run_id for approval in pending):
            return run
        return self._continue(run_id)

    def pause(self, run_id: UUID) -> AgentRunRecord:
        runtime = self._runtime_for(run_id)
        runtime.pause()
        paused = self._transition(run_id, RunState.PAUSED)
        self.services.events.append(
            paused.conversation_id, "run_paused", {"run_id": str(run_id)}
        )
        return paused

    def resume(self, run_id: UUID) -> AgentRunRecord:
        return self._continue(run_id)

    def stop(self, run_id: UUID) -> AgentRunRecord:
        run = self.services.store.get_run(run_id)
        with self._guard:
            runtime = self._runtimes.get(run_id)
        if runtime is not None:
            runtime.interrupt()
        for approval in self.services.store.list_pending_approvals(
            run.conversation_id
        ):
            if approval.run_id == run_id:
                self.services.store.resolve_approval(
                    approval.id,
                    approval.revision,
                    ApprovalDecision.DENY,
                )
        self._persist_change_manifest(run_id)
        cancelled = self._transition(run_id, RunState.CANCELLED)
        self.services.events.append(
            cancelled.conversation_id,
            "run_cancelled",
            {"run_id": str(run_id)},
        )
        return cancelled

    def active_run_for_workspace(
        self, workspace_id: UUID
    ) -> AgentRunRecord | None:
        """Return the live writer for one workspace, if one exists."""

        active = (
            run
            for run in reversed(
                self.services.store.list_runs_for_workspace(workspace_id)
            )
            if run.state in _ACTIVE_STATES
        )
        return next(active, None)

    def join(self, run_id: UUID, timeout: float | None = None) -> bool:
        """Wait for one runtime thread and report whether it has stopped."""

        deadline = None if timeout is None else time.monotonic() + timeout
        previous: threading.Thread | None = None
        while True:
            with self._guard:
                thread = self._threads.get(run_id)
            if thread is None:
                return True
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
            if thread.is_alive():
                return False
            with self._guard:
                current = self._threads.get(run_id)
            if current is thread or current is previous:
                return True
            previous = thread
            if deadline is not None and time.monotonic() >= deadline:
                return current is None or not current.is_alive()

    def _continue(
        self, run_id: UUID, *, runtime: RuntimeConversation | None = None
    ) -> AgentRunRecord:
        run = self.services.store.get_run(run_id)
        conversation = self.services.conversations.get(run.conversation_id)
        workspace = self.services.workspaces.get(conversation.workspace_id)
        active_runtime = runtime or self._runtime_for(run_id)
        running = self._transition(run_id, RunState.RUNNING)
        self._launch(running, workspace.root, runtime=active_runtime)
        return running

    def _runtime_for(self, run_id: UUID) -> RuntimeConversation:
        with self._guard:
            if runtime := self._runtimes.get(run_id):
                return runtime
            run = self.services.store.get_run(run_id)
            conversation = self.services.conversations.get(run.conversation_id)
            workspace = self.services.workspaces.get(conversation.workspace_id)
            permission_grants = self._grants_for(run.id)
            bridge = AgentEventBridge(
                conversation.id,
                run.id,
                self.services.store,
                self.services.events,
                self.services.conversations,
                workspace=workspace.root,
                permission_grants=permission_grants,
            )
            runtime = self.runtime_factory.create(
                workspace.root, run.sdk_conversation_id, bridge
            )
            self._runtimes[run_id] = runtime
            return runtime

    def _grants_for(self, run_id: UUID) -> set[PermissionCategory]:
        with self._guard:
            existing = self._permission_grants.get(run_id)
            if existing is not None:
                return existing
            restored = {
                PermissionCategory(value)
                for value in self.services.store.list_run_permission_grants(run_id)
            }
            self._permission_grants[run_id] = restored
            return restored

    def _begin_execution(
        self, run: AgentRunRecord, workspace: Path, compiled_prompt: str
    ) -> AgentRunRecord:
        permission_grants = self._grants_for(run.id)
        bridge = AgentEventBridge(
            run.conversation_id,
            run.id,
            self.services.store,
            self.services.events,
            self.services.conversations,
            workspace=workspace,
            permission_grants=permission_grants,
        )
        runtime = self.runtime_factory.create(
            workspace, run.sdk_conversation_id, bridge
        )
        with self._guard:
            self._runtimes[run.id] = runtime
        runtime.send_message(compiled_prompt)
        running = self._transition(run.id, RunState.RUNNING)
        self.services.events.append(
            run.conversation_id, "run_started", {"run_id": str(run.id)}
        )
        self._launch(running, workspace)
        return running

    def _launch_preparation(self, run_id: UUID, workspace: Path) -> None:
        thread = threading.Thread(
            target=self._prepare,
            args=(run_id, workspace),
            name=f"agent-kronig-preparation-{run_id}",
            daemon=True,
        )
        with self._guard:
            self._threads[run_id] = thread
        thread.start()

    def _prepare(self, run_id: UUID, workspace: Path) -> None:
        if self.preparation is None:
            return
        try:
            record = self.services.store.get_prompt_preparation(run_id)
            self.services.events.append(
                self.services.store.get_run(run_id).conversation_id,
                "prompt_preparation_progress",
                {"run_id": str(run_id), "phase": "checking_local_evidence"},
            )
            outcome = self.preparation.prepare(
                root=workspace,
                original_prompt=record.original_prompt,
                answers=record.answers,
            )
            current_run = self.services.store.get_run(run_id)
            if current_run.state is RunState.CANCELLED:
                return
            updated = self.services.store.update_prompt_preparation(
                run_id,
                record.revision,
                answers=record.answers,
                decision=outcome.decision,
                compiled_request=outcome.compiled_request,
            )
            if outcome.decision.status == "clarification":
                waiting = self._transition(run_id, RunState.WAITING_FOR_USER)
                self.services.events.append(
                    waiting.conversation_id,
                    "clarification_required",
                    {
                        "run_id": str(run_id),
                        "preparation_revision": updated.revision,
                        "question_count": len(outcome.decision.questions),
                        "questions": [
                            question.model_dump(mode="json")
                            for question in outcome.decision.questions
                        ],
                    },
                )
                return
            if outcome.decision.status == "blocked":
                self.services.conversations.add_assistant_message(
                    current_run.conversation_id, outcome.decision.summary
                )
                blocked = self._transition(run_id, RunState.BLOCKED)
                self.services.events.append(
                    blocked.conversation_id,
                    "run_blocked",
                    {"run_id": str(run_id), "detail": outcome.decision.summary},
                )
                return
            compiled = outcome.compiled_request
            if compiled is None:
                raise IDEStoreError("ready preparation did not compile")
            self.services.events.append(
                current_run.conversation_id,
                "prompt_compiled",
                {
                    "run_id": str(run_id),
                    "compiler_version": compiled.compiler_version,
                    "original_sha256": compiled.original_sha256,
                    "compiled_sha256": compiled.compiled_sha256,
                    "evidence_count": len(compiled.evidence),
                    "warning_count": len(compiled.decision.warnings),
                },
            )
            self._begin_execution(current_run, workspace, compiled.compiled_prompt)
        except Exception as error:
            current = self.services.store.get_run(run_id)
            if current.state is RunState.CANCELLED:
                return
            failed = self._transition(run_id, RunState.FAILED)
            self.services.events.append(
                failed.conversation_id,
                "run_failed",
                {"run_id": str(run_id), "detail": safe_event_text(error)},
            )

    def _launch(
        self,
        run: AgentRunRecord,
        workspace: Path,
        *,
        runtime: RuntimeConversation | None = None,
    ) -> None:
        canonical = workspace.resolve()
        lock = self._workspace_locks.setdefault(canonical, threading.Lock())
        if not lock.acquire(blocking=False):
            raise AgentRunConflictError("the workspace already has a running writer")
        active_runtime = runtime or self._runtimes[run.id]
        thread = threading.Thread(
            target=self._execute,
            args=(run.id, active_runtime, lock),
            name=f"agent-kronig-agent-{run.id}",
            daemon=True,
        )
        self._threads[run.id] = thread
        thread.start()

    def _execute(
        self,
        run_id: UUID,
        runtime: RuntimeConversation,
        workspace_lock: threading.Lock,
    ) -> None:
        try:
            runtime.run()
            current = self.services.store.get_run(run_id)
            if current.state is RunState.CANCELLED:
                return
            status = runtime.state.execution_status
            if status is ConversationExecutionStatus.WAITING_FOR_CONFIRMATION:
                if current.state is not RunState.WAITING_FOR_APPROVAL:
                    self._transition(run_id, RunState.WAITING_FOR_APPROVAL)
                return
            if status is ConversationExecutionStatus.PAUSED:
                if current.state is not RunState.PAUSED:
                    self._transition(run_id, RunState.PAUSED)
                return
            if status is ConversationExecutionStatus.STUCK:
                self._persist_change_manifest(run_id)
                final = self._transition(run_id, RunState.BLOCKED)
                kind = "run_blocked"
            elif status is ConversationExecutionStatus.ERROR:
                self._persist_change_manifest(run_id)
                final = self._transition(run_id, RunState.FAILED)
                kind = "run_failed"
            else:
                self._persist_change_manifest(run_id)
                final = self._transition(run_id, RunState.COMPLETED)
                kind = "run_completed"
            self.services.events.append(
                final.conversation_id, kind, {"run_id": str(run_id)}
            )
        except Exception as error:
            current = self.services.store.get_run(run_id)
            if current.state is not RunState.CANCELLED:
                self._persist_change_manifest(run_id)
                failed = self._transition(run_id, RunState.FAILED)
                self.services.events.append(
                    failed.conversation_id,
                    "run_failed",
                    {"run_id": str(run_id), "detail": safe_event_text(error)},
                )
        finally:
            workspace_lock.release()

    def _persist_change_manifest(self, run_id: UUID) -> None:
        """Freeze bounded workspace evidence before a run reaches a terminal state."""

        if self.services.store.get_run_change_manifest(run_id) is not None:
            return
        run = self.services.store.get_run(run_id)
        try:
            conversation = self.services.conversations.get(run.conversation_id)
            workspace = self.services.workspaces.get(conversation.workspace_id)
            baseline = self.services.store.get_run_baseline(run_id)
            tracker = getattr(self.services, "changes", WorkspaceChangeTracker())
            change_set = tracker.compare(workspace.root, baseline).model_copy(
                update={"run_id": run_id}
            )
            run_events = tuple(
                event
                for event in self.services.events.iter_after(run.conversation_id, 0)
                if event.payload.get("run_id") == str(run_id)
            )
            manifest = attribute_changes(change_set, run_events, root=workspace.root)
            self.services.store.save_run_change_manifest(run_id, manifest)
        except (IDEStoreError, OSError, ValueError) as error:
            self.services.events.append(
                run.conversation_id,
                "change_manifest_warning",
                {"run_id": str(run_id), "detail": safe_event_text(error)},
            )

    def _transition(self, run_id: UUID, state: RunState) -> AgentRunRecord:
        current = self.services.store.get_run(run_id)
        return self.services.store.transition_run(run_id, current.revision, state)

    def _recover_interrupted_runs(self) -> None:
        for run in self.services.store.list_runs_in_states(_ACTIVE_STATES):
            pending = tuple(
                approval
                for approval in self.services.store.list_pending_approvals(
                    run.conversation_id
                )
                if approval.run_id == run.id
            )
            if pending:
                anchor = pending[0]
                self.services.store.resolve_approval_batch(
                    anchor.id,
                    anchor.revision,
                    ApprovalDecision.DENY,
                )
            if run.state is not RunState.QUEUED:
                self._persist_change_manifest(run.id)
            current = self.services.store.get_run(run.id)
            cancelled = self.services.store.transition_run(
                run.id, current.revision, RunState.CANCELLED
            )
            self.services.events.append(
                cancelled.conversation_id,
                "run_cancelled",
                {
                    "run_id": str(run.id),
                    "detail": (
                        "The run ended because the previous application session ended."
                    ),
                },
            )
