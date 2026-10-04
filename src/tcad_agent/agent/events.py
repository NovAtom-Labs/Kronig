"""Stable, redacted product events derived from OpenHands SDK events."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from openhands.sdk.agent.stream_context import (
    StreamAborted,
    StreamDelta,
    StreamProgress,
    StreamStarted,
)
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    ConversationStateUpdateEvent,
    Event,
    InterruptEvent,
    MessageEvent,
    ObservationEvent,
    PauseEvent,
)
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.llm import content_to_str
from openhands.sdk.security import SecurityRisk
from openhands.tools.file_editor.definition import FileEditorAction
from openhands.tools.task.definition import TaskAction, TaskObservation
from openhands.tools.task_tracker.definition import TaskTrackerAction
from openhands.tools.terminal.definition import TerminalAction
from pydantic import JsonValue

from tcad_agent.agent.policy import (
    action_summary,
    approval_explanation,
    classify_action,
    command_tokens,
    executable_name,
    permission_category,
)
from tcad_agent.agent.tools import TcadDomainAction, TcadDomainObservation
from tcad_agent.experiments.models import PreparedExperiment
from tcad_agent.ide.changes import WorkspaceChangeTracker
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import (
    PermissionCategory,
    RunState,
    WorkspaceBaseline,
    is_run_grantable,
)
from tcad_agent.ide.outcomes import derive_run_outcome
from tcad_agent.ide.store import SqliteIDEStore

MAX_EVENT_TEXT = 16_000
_SECRET_ENV_NAMES = (
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret)\s*[:=]\s*[^\s,;]+"),
)


def structured_action_metadata(event: ActionEvent) -> dict[str, JsonValue]:
    """Return evidence fields derived from typed actions, never summary text."""

    action = event.action
    if isinstance(action, FileEditorAction):
        return {
            "phase": "inspect" if action.command == "view" else "edit",
            "affected_paths": [str(action.path)],
        }
    if isinstance(action, TaskAction):
        return {"phase": "delegate", "subagent": action.subagent_type}
    if isinstance(action, TcadDomainAction):
        phases = {
            "describe_spec": "inspect",
            "validate_spec": "validate",
            "prepare_experiment": "plan",
            "execute_experiment": "execute",
            "execute_approved_plan": "execute",
            "validate_result": "validate",
            "inspect_bundle": "inspect",
            "read_canonical_summary": "inspect",
            "validate_bundle": "validate",
            "search_knowledge": "inspect",
            "search_web": "inspect",
            "fetch_source": "inspect",
            "build_report": "report",
        }
        metadata: dict[str, JsonValue] = {
            "phase": phases.get(action.operation, "unknown")
        }
        if action.operation in {
            "validate_spec",
            "validate_result",
            "validate_bundle",
        }:
            metadata["evidence_kind"] = "validation"
        elif action.operation in {"execute_experiment", "execute_approved_plan"}:
            metadata["evidence_kind"] = "simulation"
        elif action.operation in {"search_knowledge", "search_web", "fetch_source"}:
            metadata["evidence_kind"] = "research"
            metadata["research_scope"] = (
                "local" if action.operation == "search_knowledge" else "web"
            )
        return metadata
    if isinstance(action, TerminalAction):
        try:
            tokens = command_tokens(action.command)
        except ValueError:
            tokens = []
        if len(tokens) >= 4 and tokens[0] == "cd" and tokens[2] == "&&":
            tokens = tokens[3:]
        if tokens and tokens[-1] == "2>&1":
            tokens.pop()
        executable = executable_name(tokens[0]) if tokens else ""
        inspection_commands = {
            "cat",
            "diff",
            "find",
            "grep",
            "head",
            "ls",
            "pwd",
            "rg",
            "sed",
            "tail",
            "wc",
        }
        validation_commands = {"mypy", "pytest"}
        if executable == "git" and len(tokens) > 1 and tokens[1] in {
            "diff",
            "log",
            "show",
            "status",
        }:
            return {"phase": "inspect"}
        if executable in inspection_commands:
            return {"phase": "inspect"}
        if executable in validation_commands:
            return {
                "phase": "validate",
                "evidence_kind": "validation",
                "validation_scope": "workspace",
            }
        ruff_mutates = any(
            token in {"--add-noqa", "--fix", "--fix-only"}
            or token.startswith(("--fix=", "--fix-only="))
            for token in tokens[2:]
        )
        if executable == "ruff" and tokens[1:2] == ["check"] and not ruff_mutates:
            return {
                "phase": "validate",
                "evidence_kind": "validation",
                "validation_scope": "workspace",
            }
        python_executable = re.fullmatch(r"python(?:\d+(?:\.\d+)?)?", executable)
        if python_executable and tokens[1:3] == ["-m", "pytest"]:
            return {
                "phase": "validate",
                "evidence_kind": "validation",
                "validation_scope": "workspace",
            }
        if (
            python_executable
            and len(tokens) > 1
            and Path(tokens[1]).name == "check.py"
        ):
            return {
                "phase": "validate",
                "evidence_kind": "validation",
                "validation_scope": "workspace",
            }
        return {"phase": "execute"}
    phases = {"task_tracker": "plan", "think": "plan", "finish": "report"}
    return {"phase": phases.get(event.tool_name, "unknown")}


def safe_event_text(value: object, secrets: tuple[str, ...] = ()) -> str:
    """Clip and redact a value before it crosses the product event boundary."""

    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _CREDENTIAL_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > MAX_EVENT_TEXT:
        return f"{text[: MAX_EVENT_TEXT - 20]}...[output clipped]"
    return text


class AgentEventBridge:
    """Convert SDK-specific callbacks to durable, UI-safe product events."""

    def __init__(
        self,
        conversation_id: UUID,
        run_id: UUID,
        store: SqliteIDEStore,
        events: EventFeed,
        conversations: ConversationService,
        *,
        workspace: Path | None = None,
        permission_grants: set[PermissionCategory] | set[str] | None = None,
        secret_values: tuple[str, ...] | None = None,
    ) -> None:
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.store = store
        self.events = events
        self.conversations = conversations
        self.workspace = workspace.resolve() if workspace is not None else None
        raw_grants = permission_grants if permission_grants is not None else set()
        normalized_grants = {PermissionCategory(value) for value in raw_grants}
        raw_grants.clear()
        raw_grants.update(normalized_grants)
        self.permission_grants = cast(set[PermissionCategory], raw_grants)
        self.secret_values = secret_values or tuple(
            value
            for name in _SECRET_ENV_NAMES
            if (value := os.getenv(name)) is not None
        )
        self._approval_actions: set[str] = set()
        self._action_baselines: dict[str, WorkspaceBaseline] = {}
        self._action_metadata: dict[str, dict[str, JsonValue]] = {}
        self._ambiguous_actions: set[str] = set()
        self._change_tracker = WorkspaceChangeTracker()
        self._plan_pause: Callable[[], None] | None = None
        self._result_pause: Callable[[], None] | None = None

    def bind_plan_pause(self, callback: Callable[[], None]) -> None:
        """Bind the runtime pause used to enforce the prepared-plan review gate."""

        self._plan_pause = callback

    def bind_result_pause(self, callback: Callable[[], None]) -> None:
        """Bind the runtime pause used to hand typed results back to the product."""

        self._result_pause = callback

    def __call__(self, event: Event) -> None:
        if isinstance(event, ActionEvent):
            self._action(event)
        elif isinstance(event, ObservationEvent):
            self._observation(event)
        elif isinstance(event, MessageEvent):
            self._message(event)
        elif isinstance(event, PauseEvent):
            self.events.append(self.conversation_id, "run_paused", self._base(event))
        elif isinstance(event, InterruptEvent):
            self.events.append(
                self.conversation_id, "run_interrupted", self._base(event)
            )
        elif isinstance(event, AgentErrorEvent | ConversationErrorEvent):
            detail = getattr(event, "error", None) or getattr(event, "detail", "")
            self.events.append(
                self.conversation_id,
                "agent_error",
                {**self._base(event), "detail": self._safe(detail)},
            )
        elif isinstance(event, ConversationStateUpdateEvent):
            self.events.append(
                self.conversation_id,
                "runtime_state_changed",
                {
                    **self._base(event),
                    "key": self._safe(event.key),
                    "value": self._safe(event.value),
                },
            )

    def on_stream(self, frame: StreamProgress) -> None:
        """Expose content-free inference lifecycle while discarding every token."""

        if isinstance(frame, StreamStarted):
            self.events.append(
                self.conversation_id,
                "agent_progress_started",
                {
                    "run_id": str(self.run_id),
                    "item_id": frame.item_id,
                    "attempt": frame.attempt,
                },
            )
        elif isinstance(frame, StreamAborted):
            self.events.append(
                self.conversation_id,
                "agent_progress_interrupted",
                {
                    "run_id": str(self.run_id),
                    "item_id": frame.item_id,
                    "attempt": frame.attempt,
                },
            )
        elif isinstance(frame, StreamDelta):
            return

    def _action(self, event: ActionEvent) -> None:
        policy_workspace = self.workspace or Path.cwd()
        risk = (
            classify_action(policy_workspace, event)
            if self.workspace is not None
            else event.security_risk
        )
        category = permission_category(policy_workspace, event)
        metadata = structured_action_metadata(event)
        self._action_metadata[event.id] = metadata
        payload: dict[str, JsonValue] = {
            **self._base(event),
            **metadata,
            "action_id": event.id,
            "risk": risk.value,
            "permission_category": category.value,
            "summary": self._safe(action_summary(event)),
            "tool_call_id": event.tool_call_id,
            "tool_name": event.tool_name,
        }
        normalized = self._normalized_action(event)
        if normalized:
            payload["arguments"] = normalized
        if self.workspace is not None and metadata.get("phase") in {
            "plan",
            "edit",
            "execute",
            "delegate",
        }:
            try:
                if self._action_baselines:
                    self._ambiguous_actions.update(self._action_baselines)
                    self._ambiguous_actions.add(event.id)
                self._action_baselines[event.id] = self._change_tracker.capture(
                    self.workspace
                )
            except OSError:
                pass
        self.events.append(self.conversation_id, "tool_call_started", payload)
        grant_applies = is_run_grantable(category) and category in self.permission_grants
        if risk is SecurityRisk.HIGH and grant_applies:
            self.events.append(
                self.conversation_id,
                "permission_grant_used",
                {
                    **self._base(event),
                    "action_id": event.id,
                    "permission_category": category.value,
                    "scope": "run",
                    "tool_name": event.tool_name,
                },
            )
        if (
            risk is SecurityRisk.HIGH
            and not grant_applies
            and event.id not in self._approval_actions
        ):
            self._approval_actions.add(event.id)
            self.store.create_approval(
                self.run_id,
                event.id,
                event.tool_name,
                risk.value,
                approval_explanation(policy_workspace, event, category),
                normalized,
                permission_category=category,
            )

    def _observation(self, event: ObservationEvent) -> None:
        metadata = self._action_metadata.pop(event.action_id, {})
        observation_failed = event.observation.is_error or (
            isinstance(event.observation, TcadDomainObservation)
            and event.observation.status != "ok"
        )
        visible_output = self._safe(event.observation.text)
        artifact_paths: list[str] = []
        prepared_plan: PreparedExperiment | None = None
        result_ready: dict[str, JsonValue] | None = None
        if (
            not observation_failed
            and isinstance(event.observation, TcadDomainObservation)
            and event.observation.code == "experiment_prepared"
        ):
            prepared_plan = PreparedExperiment.model_validate(
                event.observation.data["prepared"]
            )
            artifact_data = event.observation.data.get("plan_artifacts", {})
            if not isinstance(artifact_data, dict) or self.workspace is None:
                raise ValueError("prepared experiment is missing workspace plan artifacts")
            plan_path = Path(str(artifact_data.get("plan", ""))).resolve()
            structured_path = Path(
                str(artifact_data.get("structured_plan", ""))
            ).resolve()
            if not plan_path.is_relative_to(self.workspace) or not structured_path.is_relative_to(
                self.workspace
            ):
                raise ValueError("prepared plan artifacts escaped the selected workspace")
            self.store.save_prepared_plan(
                self.run_id,
                prepared_plan,
                plan_path=plan_path,
                structured_plan_path=structured_path,
            )
            artifact_paths = [
                plan_path.relative_to(self.workspace).as_posix(),
                structured_path.relative_to(self.workspace).as_posix(),
            ]
            project_path = plan_path.parent.relative_to(self.workspace).as_posix()
            visible_output = (
                f"Experiment project created at {project_path}. "
                "The approval plan is ready for review."
            )
        if (
            not observation_failed
            and isinstance(event.observation, TcadDomainObservation)
            and event.observation.code == "experiment_executed"
        ):
            data = event.observation.data
            bundle_data = data.get("bundle")
            project_data = data.get("experiment")
            if (
                not isinstance(bundle_data, dict)
                or not isinstance(project_data, dict)
                or self.workspace is None
            ):
                raise ValueError("completed experiment is missing managed result metadata")
            bundle_run_id = str(bundle_data.get("run_id", "")).strip()
            execution_state = str(bundle_data.get("execution_state", "failed"))
            validation_state = str(bundle_data.get("validation_state", "failed"))
            project_root = Path(str(project_data.get("project_root", ""))).resolve()
            if not bundle_run_id or not project_root.is_relative_to(self.workspace):
                raise ValueError("completed experiment metadata escaped the workspace")
            projected_paths: list[Path] = []
            for key in (
                "report_path",
                "result_path",
                "validation_path",
                "traceability_path",
            ):
                value = project_data.get(key)
                if value is None or value == "":
                    continue
                candidate = Path(str(value)).resolve()
                if not candidate.is_relative_to(self.workspace):
                    raise ValueError("completed experiment artifact escaped the workspace")
                projected_paths.append(candidate)
            artifact_paths = [
                path.relative_to(self.workspace).as_posix() for path in projected_paths
            ]
            if execution_state not in {"failed", "completed"}:
                raise ValueError("completed experiment has an invalid execution state")
            if validation_state not in {"passed", "needs_review", "failed"}:
                raise ValueError("completed experiment has an invalid validation state")
            self.store.save_experiment_result(
                self.run_id,
                bundle_run_id=bundle_run_id,
                project_root=project_root,
                execution_state=cast(Literal["failed", "completed"], execution_state),
                validation_state=cast(
                    Literal["passed", "needs_review", "failed"], validation_state
                ),
            )
            outcome_values = derive_run_outcome(
                run_id=self.run_id,
                project_root=project_root,
                execution_state=cast(
                    Literal["failed", "completed"], execution_state
                ),
                validation_state=cast(
                    Literal["passed", "needs_review", "failed"], validation_state
                ),
            )
            outcome = self.store.save_run_outcome(**outcome_values)
            try:
                approved_plan = self.store.get_prepared_plan(self.run_id)
            except RuntimeError:
                approved_plan = None
            if approved_plan is not None and approved_plan.status == "approved":
                self.store.consume_prepared_plan(
                    self.run_id, approved_plan.plan_digest
                )
            result_ready = {
                "run_id": str(self.run_id),
                "bundle_run_id": bundle_run_id,
                "execution_state": execution_state,
                "validation_state": validation_state,
                "deliverable_state": outcome.deliverable_state,
                "report_state": outcome.report_state,
                "overall_state": outcome.overall_state,
                "failed_check_count": outcome.failed_check_count,
                "unmet_deliverables": list(outcome.unmet_deliverables),
            }
            project_path = project_root.relative_to(self.workspace).as_posix()
            visible_output = (
                f"Simulation evidence published to {project_path}. "
                "Open the Results Workbench to review it."
            )
        payload: dict[str, JsonValue] = {
            **self._base(event),
            "action_id": event.action_id,
            "is_error": observation_failed,
            "output": visible_output,
            "tool_call_id": event.tool_call_id,
            "tool_name": event.tool_name,
        }
        if prepared_plan is not None:
            payload["plan_digest"] = prepared_plan.plan_digest
            payload["plan_ready"] = True
        if artifact_paths:
            payload["artifact_paths"] = cast(JsonValue, artifact_paths)
        if isinstance(event.observation, TaskObservation):
            payload.update(
                {
                    "task_id": event.observation.task_id,
                    "subagent": event.observation.subagent,
                    "task_status": event.observation.status,
                }
            )
        baseline = self._action_baselines.pop(event.action_id, None)
        if event.action_id in self._ambiguous_actions:
            payload["attribution_uncertain"] = True
            self._ambiguous_actions.discard(event.action_id)
        elif baseline is not None and self.workspace is not None:
            try:
                action_changes = self._change_tracker.compare(self.workspace, baseline)
            except (OSError, ValueError):
                pass
            else:
                payload["affected_paths"] = [
                    change.path for change in action_changes.files
                ]
        if (
            not observation_failed
            and metadata.get("evidence_kind") == "validation"
            and metadata.get("validation_scope") == "workspace"
            and self.workspace is not None
        ):
            try:
                run_baseline = self.store.get_run_baseline(self.run_id)
                validated_changes = self._change_tracker.compare(
                    self.workspace, run_baseline
                )
            except (OSError, RuntimeError, ValueError):
                payload["validation_incomplete"] = True
            else:
                if validated_changes.baseline_truncated:
                    payload["validation_incomplete"] = True
                payload["validated_files"] = {
                    change.path: change.after_sha256
                    for change in validated_changes.files
                    if change.after_sha256 is not None and not change.uncertain
                }
        self.events.append(
            self.conversation_id,
            "tool_call_completed",
            payload,
        )
        if result_ready is not None:
            self.events.append(self.conversation_id, "result_ready", result_ready)
            if self._result_pause is not None:
                self._result_pause()
        if prepared_plan is not None and self._plan_pause is not None:
            self._plan_pause()

    def _message(self, event: MessageEvent) -> None:
        if event.source != "agent" or event.llm_message.role != "assistant":
            return
        content = self._safe("\n".join(content_to_str(event.llm_message.content))).strip()
        if self.store.get_run(self.run_id).state is RunState.WAITING_FOR_PLAN_APPROVAL:
            return
        if content:
            self.conversations.add_assistant_message(self.conversation_id, content)

    def _normalized_action(self, event: ActionEvent) -> dict[str, JsonValue]:
        action = event.action
        if isinstance(action, TerminalAction):
            return {"command": self._safe(action.command)}
        if isinstance(action, FileEditorAction):
            return {"command": action.command, "path": self._safe(action.path)}
        if isinstance(action, TaskAction):
            return {
                "description": self._safe(action.description or "delegated task"),
                "subagent_type": action.subagent_type,
            }
        if isinstance(action, TaskTrackerAction) and action.command == "plan":
            return {
                "tasks": [
                    {
                        "title": self._safe(item.title),
                        "status": item.status,
                    }
                    for item in action.task_list
                ]
            }
        if isinstance(action, TcadDomainAction):
            result: dict[str, JsonValue] = {"operation": action.operation}
            if action.backend is not None:
                result["backend"] = self._safe(action.backend)
            return result
        return {}

    def _safe(self, value: object) -> str:
        return safe_event_text(value, self.secret_values)

    def _base(self, event: Event) -> dict[str, JsonValue]:
        return {"run_id": str(self.run_id), "sdk_event_id": event.id}


def json_mapping(value: Mapping[str, object]) -> dict[str, JsonValue]:
    """Narrow a known JSON-safe mapping for callers constructing product events."""

    return cast(dict[str, JsonValue], dict(value))
