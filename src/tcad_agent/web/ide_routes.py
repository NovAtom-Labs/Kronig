"""HTTP and event-stream routes for the Linux-local repository IDE."""

from __future__ import annotations

import asyncio
import os
import platform
import shutil
import subprocess
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from tcad_agent.agent.supervisor import AgentRunConflictError, AgentSupervisor
from tcad_agent.bundles.export import BundleArchiveService, BundleExportRecord
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.ide.changes import WorkspaceChangeTracker, attribute_changes
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed, format_sse
from tcad_agent.ide.models import (
    AgentRunRecord,
    ApprovalRequestRecord,
    ConversationMessage,
    ExperimentProjectSummary,
    PreparedPlanRecord,
    RunState,
    WorkspaceChangeSet,
    WorkspaceEntry,
    WorkspaceFilePreview,
    WorkspaceRecord,
    WorkspaceSessionRecord,
    WorkspaceTextFile,
)
from tcad_agent.ide.repository import WorkspaceFileConflictError
from tcad_agent.ide.result_catalog import SavedResultCatalog, SavedResultListing
from tcad_agent.ide.results import (
    WorkspaceResultComparison,
    WorkspaceResultError,
    WorkspaceResultReader,
    WorkspaceResultView,
)
from tcad_agent.ide.sessions import WorkspaceSessionBusyError, WorkspaceSessionService
from tcad_agent.ide.store import IDEStoreError, MessageNotFoundError, SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.prompting.models import PromptPreparationRecord
from tcad_agent.recovery.models import RecoveryAction
from tcad_agent.recovery.proposals import RecoveryProposalService, recovery_failures_from_report
from tcad_agent.results.models import CanonicalResult
from tcad_agent.results.query import (
    DatasetQueryError,
    DatasetQueryResult,
    query_dataset,
)
from tcad_agent.runtime.paths import RuntimePaths
from tcad_agent.validation.assessment import assess_result
from tcad_agent.validation.policy import validation_policy_digest
from tcad_agent.web.schemas import (
    AnswerClarificationRequest,
    ApprovePlanRequest,
    CreateMessageRequest,
    DenyAgentApprovalRequest,
    ExportBundleRequest,
    OpenWorkspaceRequest,
    RecoveryReviewRequest,
    ResolveAgentApprovalRequest,
    RevisePlanRequest,
    SaveWorkspaceFileRequest,
    StartAgentRunRequest,
)


class DirectoryPickerUnavailable(RuntimeError):
    """Raised when the host cannot present a graphical directory chooser."""


class AgentAPIError(RuntimeError):
    """Stable, sanitized error returned by the repository-agent API."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class IDEServices:
    workspaces: WorkspaceManager
    conversations: ConversationService
    events: EventFeed
    changes: WorkspaceChangeTracker = field(default_factory=WorkspaceChangeTracker)
    results: WorkspaceResultReader = field(default_factory=WorkspaceResultReader)
    bundle_archives: BundleArchiveService = field(default_factory=BundleArchiveService)
    store: SqliteIDEStore = field(init=False)
    runtime_root: Path = field(init=False)
    sessions: WorkspaceSessionService = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "store", self.conversations.store)
        object.__setattr__(self, "runtime_root", self.conversations.store.path.parent)
        object.__setattr__(
            self,
            "sessions",
            WorkspaceSessionService(
                self.workspaces,
                self.conversations,
                self.conversations.store.path.parent,
            ),
        )


def build_default_ide_services() -> IDEServices:
    runtime_root = Path(os.getenv("TCAD_WORKSPACE", str(Path.cwd() / ".tcad-agent"))).resolve()
    store = SqliteIDEStore(runtime_root / "ide.sqlite3")
    events = EventFeed(store)
    return IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )


def _event_cursor(request: Request, after: int) -> int:
    header = request.headers.get("last-event-id")
    if header is None:
        return after
    try:
        cursor = int(header)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid event cursor") from exc
    if cursor < 0:
        raise HTTPException(status_code=400, detail="invalid event cursor")
    return cursor


def select_directory() -> Path | None:
    """Return a locally selected directory, or None when selection is cancelled."""

    system = platform.system()
    commands: list[list[str]] = []

    if system == "Linux":
        if not (os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")):
            raise DirectoryPickerUnavailable(
                "A graphical desktop is required for the folder picker. "
                "Enter the repository path manually."
            )
        zenity = shutil.which("zenity")
        kdialog = shutil.which("kdialog")
        if zenity:
            commands.append(
                [
                    zenity,
                    "--file-selection",
                    "--directory",
                    "--title=Open repository folder",
                ]
            )
        if kdialog:
            commands.append([kdialog, "--getexistingdirectory", str(Path.home())])
    elif system == "Darwin":
        if osascript := shutil.which("osascript"):
            commands.append(
                [
                    osascript,
                    "-e",
                    'POSIX path of (choose folder with prompt "Open repository folder")',
                ]
            )
    elif system == "Windows":
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell:
            commands.append(
                [
                    powershell,
                    "-NoProfile",
                    "-Command",
                    (
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
                        "$dialog.Description = 'Open repository folder'; "
                        "if ($dialog.ShowDialog() -eq 'OK') { $dialog.SelectedPath }"
                    ),
                ]
            )

    if not commands:
        raise DirectoryPickerUnavailable(
            "No native folder picker is available. Enter the repository path manually."
        )

    for command in commands:
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            continue
        if completed.returncode == 1:
            return None
        if completed.returncode != 0:
            continue
        raw_path = completed.stdout.strip()
        if not raw_path:
            return None
        selected = Path(raw_path).expanduser().resolve()
        if selected.is_dir():
            return selected
        raise DirectoryPickerUnavailable(
            "The selected folder is unavailable. Choose another folder or enter its path."
        )

    raise DirectoryPickerUnavailable(
        "The native folder picker could not open. Enter the repository path manually."
    )


def build_ide_router(services: IDEServices, supervisor: AgentSupervisor) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/system/directories/select")
    def select_local_directory(request: Request) -> dict[str, str | None]:
        client_host = request.client.host if request.client else ""
        if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
            raise HTTPException(status_code=403, detail="Folder selection is local only.")
        try:
            selected = select_directory()
        except DirectoryPickerUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"path": str(selected) if selected is not None else None}

    @router.post("/workspaces", status_code=201)
    def open_workspace(payload: OpenWorkspaceRequest) -> WorkspaceRecord:
        return services.workspaces.open(Path(payload.path))

    @router.get("/workspaces")
    def list_workspaces() -> tuple[WorkspaceRecord, ...]:
        return services.workspaces.list()

    @router.get("/workspaces/{workspace_id}")
    def get_workspace(workspace_id: UUID) -> WorkspaceRecord:
        return services.workspaces.get(workspace_id)

    @router.get("/workspaces/{workspace_id}/entries")
    def workspace_entries(workspace_id: UUID, path: str = ".") -> tuple[WorkspaceEntry, ...]:
        return services.workspaces.entries(workspace_id, path)

    @router.get("/workspaces/{workspace_id}/experiments")
    def workspace_experiments(
        workspace_id: UUID,
    ) -> tuple[ExperimentProjectSummary, ...]:
        workspace = services.workspaces.get(workspace_id)
        root = workspace.root.resolve()
        summaries: list[ExperimentProjectSummary] = []
        for record in services.store.list_experiment_results_for_workspace(workspace_id):
            project = record.project_root.resolve(strict=False)
            if not project.is_relative_to(root):
                raise AgentAPIError(
                    409,
                    "invalid_result_project",
                    "A recorded experiment no longer belongs to this repository.",
                )
            relative = project.relative_to(root).as_posix()
            outcome = services.store.find_run_outcome(record.run_id)
            artifacts = {
                key: f"{relative}/{name}"
                for key, name in {
                    "plan": "PLAN.md",
                    "report": "REPORT.md",
                    "results": "results.json",
                    "validation": "validation.json",
                }.items()
                if (project / name).is_file()
            }
            summaries.append(
                ExperimentProjectSummary(
                    run_id=record.run_id,
                    bundle_run_id=record.bundle_run_id,
                    name=project.name,
                    project_path=relative,
                    execution_state=record.execution_state,
                    validation_state=record.validation_state,
                    failed_check_count=outcome.failed_check_count if outcome else None,
                    unmet_deliverables=outcome.unmet_deliverables if outcome else (),
                    artifacts=artifacts,
                )
            )
        return tuple(summaries)

    @router.get("/workspaces/{workspace_id}/saved-results")
    def saved_results(workspace_id: UUID) -> SavedResultListing:
        workspace = services.workspaces.get(workspace_id)
        try:
            return SavedResultCatalog(services.results).list(workspace.root)
        except WorkspaceResultError as exc:
            raise AgentAPIError(
                409,
                "invalid_result_catalog",
                "Saved evidence storage is unavailable or failed integrity checks.",
            ) from exc

    @router.get("/workspaces/{workspace_id}/saved-results/{bundle_run_id}")
    def saved_result(workspace_id: UUID, bundle_run_id: str) -> dict[str, object]:
        workspace = services.workspaces.get(workspace_id)
        try:
            view = SavedResultCatalog(services.results).read(workspace.root, bundle_run_id)
        except WorkspaceResultError as exc:
            raise AgentAPIError(
                409,
                "invalid_result_bundle",
                "The saved result is unavailable or failed provenance checks.",
            ) from exc
        payload = view.model_dump(mode="json")
        payload.update(saved_bundle_id=bundle_run_id, workspace_id=str(workspace_id))
        enrich_result(payload, view)
        return payload

    def enrich_result(payload: dict, view: WorkspaceResultView) -> None:
        payload["assessment"] = assess_result(
            view.result, spec=view.experiment, validation=view.validation
        ).model_dump(mode="json")
        actions = []
        policy_current = view.validation.validation_policy_digest == validation_policy_digest()
        for action in (
            RecoveryAction
            if policy_current and view.validation.acceptance_limits is not None
            else ()
        ):
            if action is RecoveryAction.STOP_AND_REPORT:
                continue
            for failure in recovery_failures_from_report(view.result, view.validation):
                try:
                    RecoveryProposalService().propose(
                        view.experiment,
                        action=action,
                        failure=failure,
                        original_bundle_id=view.manifest.run_id,
                        validation_limits=view.validation.acceptance_limits,
                        validation_policy_digest=view.validation.validation_policy_digest,
                    )
                    actions.append(action.value)
                    break
                except ValueError:
                    continue
        payload["recovery_actions"] = actions

    @router.post(
        "/workspaces/{workspace_id}/saved-results/{bundle_run_id}/recalculate", status_code=201
    )
    def recalculate_saved_result(workspace_id: UUID, bundle_run_id: str) -> AgentRunRecord:
        payload = saved_result(workspace_id, bundle_run_id)
        from tcad_agent.domain.models import ExperimentSpec

        original = ExperimentSpec.model_validate(payload["experiment"])
        candidate = original.model_copy(
            update={
                "name": f"{original.name} {uuid4().hex[:6]} recalculation",
                "metadata": {**original.metadata, "derived_from_bundle": bundle_run_id},
            }
        )
        prepared = ExperimentEngine().prepare(candidate, payload["manifest"]["backend"])
        session = current_session(workspace_id)
        try:
            return supervisor.review_prepared(
                session.id,
                prepared,
                f"Recalculate {original.name} from verified bundle {bundle_run_id}. "
                "Scientific inputs unchanged.",
            )
        except AgentRunConflictError as exc:
            raise AgentAPIError(
                409,
                "agent_run_conflict",
                "Finish or stop the active run before preparing another calculation.",
            ) from exc

    @router.post(
        "/workspaces/{workspace_id}/saved-results/{bundle_run_id}/recovery", status_code=201
    )
    def review_saved_recovery(
        workspace_id: UUID,
        bundle_run_id: str,
        request: RecoveryReviewRequest,
    ) -> dict[str, object]:
        saved_result(workspace_id, bundle_run_id)
        workspace = services.workspaces.get(workspace_id)
        view = SavedResultCatalog(services.results).read(workspace.root, bundle_run_id)
        if request.action is RecoveryAction.STOP_AND_REPORT:
            return {"stopped": True, "original_bundle_id": bundle_run_id}
        if (
            view.validation.acceptance_limits is None
            or view.validation.validation_policy_digest != validation_policy_digest()
        ):
            raise AgentAPIError(
                422,
                "recovery_limits_unavailable",
                "This result lacks the current recorded validation policy and acceptance limits. "
                "Recalculate it before preparing numerical recovery.",
            )
        proposal = None
        for failure in recovery_failures_from_report(view.result, view.validation):
            try:
                proposal = RecoveryProposalService().propose(
                    view.experiment,
                    action=request.action,
                    failure=failure,
                    original_bundle_id=bundle_run_id,
                    validation_limits=view.validation.acceptance_limits,
                    validation_policy_digest=view.validation.validation_policy_digest,
                )
                break
            except ValueError:
                continue
        if proposal is None:
            raise AgentAPIError(
                422,
                "recovery_not_applicable",
                "That numerical change is not supported by the recorded scientific failure.",
            )
        # Preserve the candidate's exact digest. A separate project suffix belongs to
        # artifact placement, not to the scientific experiment being compared.
        prepared = ExperimentEngine().prepare(
            proposal.candidate_spec, view.manifest.backend, recovery_proposal=proposal
        )
        session = current_session(workspace_id)
        try:
            run = supervisor.review_prepared(
                session.id,
                prepared,
                f"Review numerical recovery for {view.experiment.name}: {request.action.value}. "
                f"Original bundle {bundle_run_id} remains unchanged.",
            )
        except AgentRunConflictError as exc:
            raise AgentAPIError(
                409,
                "agent_run_conflict",
                "Finish or stop the active run before preparing recovery.",
            ) from exc
        return {"run": run.model_dump(mode="json"), "proposal": proposal.model_dump(mode="json")}

    @router.get("/workspaces/{workspace_id}/saved-results/{bundle_run_id}/datasets/{dataset_id}")
    def saved_result_dataset(
        workspace_id: UUID,
        bundle_run_id: str,
        dataset_id: str,
        max_points: Annotated[int, Query(ge=4, le=50_000)] = 2_000,
        slice_axis: str | None = None,
        slice_index: Annotated[int | None, Query(ge=0)] = None,
    ) -> DatasetQueryResult:
        payload = saved_result(workspace_id, bundle_run_id)
        try:
            return query_dataset(
                CanonicalResult.model_validate(payload["result"]),
                dataset_id,
                max_points=max_points,
                slice_axis=slice_axis,
                slice_index=slice_index,
            )
        except DatasetQueryError as exc:
            raise AgentAPIError(422, "invalid_dataset_query", str(exc)) from exc

    @router.post("/workspaces/{workspace_id}/saved-results/{bundle_run_id}/export", status_code=201)
    def export_saved_result(
        workspace_id: UUID,
        bundle_run_id: str,
        payload: ExportBundleRequest,
    ) -> BundleExportRecord:
        saved_result(workspace_id, bundle_run_id)
        workspace = services.workspaces.get(workspace_id)
        try:
            return services.bundle_archives.export(
                RuntimePaths.from_workspace(workspace.root).bundle_root / bundle_run_id,
                Path(payload.destination),
            )
        except (OSError, ValueError) as exc:
            raise AgentAPIError(
                409,
                "bundle_export_failed",
                "The verified bundle could not be exported to that destination.",
            ) from exc

    @router.get("/workspaces/{workspace_id}/files/preview")
    def workspace_file_preview(workspace_id: UUID, path: str) -> WorkspaceFilePreview:
        return services.workspaces.preview_file(workspace_id, path)

    @router.get("/workspaces/{workspace_id}/files/raw")
    def workspace_file_raw(workspace_id: UUID, path: str, download: bool = False) -> FileResponse:
        preview = services.workspaces.preview_file(workspace_id, path)
        if not download and preview.kind not in {"image", "pdf"}:
            raise HTTPException(
                status_code=415,
                detail="This file type can only be downloaded.",
            )
        target = services.workspaces.file_path(workspace_id, path)
        disposition = "attachment" if download else "inline"
        return FileResponse(
            target,
            media_type=preview.mime_type,
            content_disposition_type=disposition,
            filename=target.name,
            headers={
                "Cache-Control": "no-store",
                "Content-Security-Policy": "sandbox",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/workspaces/{workspace_id}/results")
    def workspace_results(workspace_id: UUID, path: str) -> WorkspaceResultView:
        workspace = services.workspaces.get(workspace_id)
        try:
            return services.results.read(workspace.root, path)
        except WorkspaceResultError as exc:
            raise AgentAPIError(
                409,
                "invalid_result_bundle",
                "The result bundle is incomplete, malformed, or failed provenance checks.",
            ) from exc

    @router.get("/workspaces/{workspace_id}/results/compare")
    def workspace_result_comparison(
        workspace_id: UUID, paths: Annotated[list[str], Query()]
    ) -> WorkspaceResultComparison:
        workspace = services.workspaces.get(workspace_id)
        if not 2 <= len(paths) <= services.results.comparison_limit:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Result comparison requires between 2 and "
                    f"{services.results.comparison_limit} paths."
                ),
            )
        try:
            return services.results.read_many(workspace.root, paths)
        except WorkspaceResultError as exc:
            raise AgentAPIError(
                409,
                "invalid_result_comparison",
                "Every comparison run must be a distinct verified result bundle.",
            ) from exc

    @router.get("/workspaces/{workspace_id}/files/content")
    def workspace_file_content(workspace_id: UUID, path: str) -> WorkspaceTextFile:
        return services.workspaces.editable_file(workspace_id, path)

    @router.put("/workspaces/{workspace_id}/files/content")
    def save_workspace_file(
        workspace_id: UUID, payload: SaveWorkspaceFileRequest
    ) -> WorkspaceTextFile:
        try:
            return services.workspaces.save_editable_file(
                workspace_id,
                payload.path,
                payload.content,
                payload.expected_sha256,
            )
        except WorkspaceFileConflictError as exc:
            raise AgentAPIError(
                409,
                "workspace_file_conflict",
                "The file changed after it was opened. Refresh before saving.",
            ) from exc

    def current_session(workspace_id: UUID) -> WorkspaceSessionRecord:
        session = services.sessions.current()
        if session is None or session.workspace_id != workspace_id:
            raise AgentAPIError(
                404,
                "workspace_session_not_found",
                "Open this workspace session before using the agent.",
            )
        return session

    @router.post("/workspaces/{workspace_id}/session")
    def open_workspace_session(workspace_id: UUID) -> WorkspaceSessionRecord:
        try:
            return services.sessions.open(workspace_id)
        except WorkspaceSessionBusyError as exc:
            raise AgentAPIError(
                409,
                "workspace_session_busy",
                "Finish or stop the active agent run before changing repositories.",
            ) from exc

    @router.get("/workspaces/{workspace_id}/session/messages")
    def list_session_messages(
        workspace_id: UUID,
    ) -> tuple[ConversationMessage, ...]:
        session = current_session(workspace_id)
        return services.conversations.messages(session.id)

    @router.post("/workspaces/{workspace_id}/session/messages", status_code=201)
    def create_session_message(
        workspace_id: UUID, payload: CreateMessageRequest
    ) -> ConversationMessage:
        session = current_session(workspace_id)
        return services.conversations.add_user_message(session.id, payload.content)

    @router.post("/workspaces/{workspace_id}/session/runs", status_code=202)
    def start_agent_run(workspace_id: UUID, payload: StartAgentRunRequest) -> AgentRunRecord:
        session = current_session(workspace_id)
        try:
            message = services.store.get_message(payload.message_id)
        except MessageNotFoundError as exc:
            raise AgentAPIError(404, "message_not_found", "The message was not found.") from exc
        if message.conversation_id != session.id or message.role != "user":
            raise AgentAPIError(
                400,
                "invalid_run_message",
                "The run must reference a user message in this workspace session.",
            )
        try:
            contextual = supervisor.approve_contextual_plan(workspace_id, message.content)
        except IDEStoreError as exc:
            raise AgentAPIError(
                409,
                "plan_approval_conflict",
                "The pending plan changed. Refresh it before approving.",
            ) from exc
        if contextual is not None:
            return contextual
        try:
            return supervisor.start(session.id, message.content, persist_message=False)
        except AgentRunConflictError as exc:
            raise AgentAPIError(
                409,
                "agent_run_conflict",
                "This workspace already has an active agent run.",
            ) from exc

    @router.get("/workspaces/{workspace_id}/session/runs/active")
    def active_agent_run(workspace_id: UUID) -> AgentRunRecord | None:
        current_session(workspace_id)
        return supervisor.active_run_for_workspace(workspace_id)

    @router.get("/runs/{run_id}/preparation")
    def prompt_preparation(run_id: UUID) -> PromptPreparationRecord:
        return services.store.get_prompt_preparation(run_id)

    @router.get("/runs/{run_id}/plan")
    def prepared_plan(run_id: UUID) -> PreparedPlanRecord:
        return services.store.get_prepared_plan(run_id)

    @router.get("/runs/{run_id}/result")
    def managed_run_result(run_id: UUID) -> dict[str, object]:
        run = services.store.get_run(run_id)
        conversation = services.conversations.get(run.conversation_id)
        workspace = services.workspaces.get(conversation.workspace_id)
        try:
            result = services.store.get_experiment_result(run_id)
        except IDEStoreError as exc:
            raise AgentAPIError(
                404,
                "result_not_ready",
                "No verified simulation result has been produced for this run.",
            ) from exc
        bundle_root = RuntimePaths.from_workspace(workspace.root).bundle_root / result.bundle_run_id
        try:
            view = services.results.read_bundle(bundle_root)
        except WorkspaceResultError as exc:
            raise AgentAPIError(
                409,
                "invalid_result_bundle",
                "The managed result is incomplete, malformed, or failed provenance checks.",
            ) from exc
        project_root = result.project_root.resolve()
        if not project_root.is_relative_to(workspace.root.resolve()):
            raise AgentAPIError(
                409,
                "invalid_result_project",
                "The result project no longer belongs to the selected repository.",
            )
        payload = view.model_dump(mode="json")
        payload["project_result_path"] = (
            (project_root / "results.json").relative_to(workspace.root.resolve()).as_posix()
        )
        payload["execution_state"] = result.execution_state
        payload["validation_state"] = result.validation_state
        payload["agent_run_id"] = str(run_id)
        payload["workspace_id"] = str(workspace.id)
        payload["saved_bundle_id"] = view.manifest.run_id
        enrich_result(payload, view)
        return payload

    @router.get("/runs/{run_id}/result/datasets/{dataset_id}")
    def managed_run_dataset(
        run_id: UUID,
        dataset_id: str,
        max_points: Annotated[int, Query(ge=4, le=50_000)] = 2_000,
        slice_axis: str | None = None,
        slice_index: Annotated[int | None, Query(ge=0)] = None,
    ) -> DatasetQueryResult:
        payload = managed_run_result(run_id)
        result = CanonicalResult.model_validate(payload["result"])
        try:
            return query_dataset(
                result,
                dataset_id,
                max_points=max_points,
                slice_axis=slice_axis,
                slice_index=slice_index,
            )
        except DatasetQueryError as exc:
            raise AgentAPIError(
                422,
                "invalid_dataset_query",
                str(exc),
            ) from exc

    @router.post(
        "/runs/{run_id}/bundle/export",
        status_code=201,
        response_model=BundleExportRecord,
    )
    def export_managed_bundle(run_id: UUID, payload: ExportBundleRequest) -> BundleExportRecord:
        run = services.store.get_run(run_id)
        conversation = services.conversations.get(run.conversation_id)
        workspace = services.workspaces.get(conversation.workspace_id)
        result = services.store.get_experiment_result(run_id)
        bundle_root = RuntimePaths.from_workspace(workspace.root).bundle_root / result.bundle_run_id
        try:
            return services.bundle_archives.export(bundle_root, Path(payload.destination))
        except (OSError, ValueError) as exc:
            raise AgentAPIError(
                409,
                "bundle_export_failed",
                "The verified reproducibility bundle could not be exported to that location.",
            ) from exc

    @router.post("/runs/{run_id}/plan/approve", status_code=202)
    def approve_prepared_plan(run_id: UUID, payload: ApprovePlanRequest) -> AgentRunRecord:
        try:
            return supervisor.approve_plan(
                run_id,
                payload.expected_revision,
                payload.plan_digest,
                mode=payload.mode,
            )
        except IDEStoreError as exc:
            raise AgentAPIError(
                409,
                "plan_approval_conflict",
                "The pending plan changed. Refresh it before approving.",
            ) from exc

    @router.post("/runs/{run_id}/plan/revise", status_code=202)
    def revise_prepared_plan(run_id: UUID, payload: RevisePlanRequest) -> AgentRunRecord:
        try:
            return supervisor.revise_plan(
                run_id,
                payload.expected_revision,
                payload.instruction,
            )
        except IDEStoreError as exc:
            raise AgentAPIError(
                409,
                "plan_revision_conflict",
                "The pending plan changed. Refresh it before requesting a revision.",
            ) from exc

    @router.post("/runs/{run_id}/clarifications", status_code=202)
    def answer_prompt_clarification(
        run_id: UUID, payload: AnswerClarificationRequest
    ) -> AgentRunRecord:
        try:
            return supervisor.answer_clarification(
                run_id, payload.expected_revision, payload.answers
            )
        except IDEStoreError as exc:
            detail = str(exc).lower()
            if "clarification round limit" in detail:
                raise AgentAPIError(409, "clarification_limit", str(exc)) from exc
            code = "stale_revision" if "stale" in detail else "invalid_clarification"
            status = 409 if code == "stale_revision" else 400
            raise AgentAPIError(
                status,
                code,
                (
                    "The clarification changed. Refresh and answer the current questions."
                    if code == "stale_revision"
                    else "The clarification answers do not match the active questions."
                ),
            ) from exc

    @router.get("/runs/{run_id}/changes")
    def run_changes(run_id: UUID) -> WorkspaceChangeSet:
        run = services.store.get_run(run_id)
        conversation = services.conversations.get(run.conversation_id)
        workspace = services.workspaces.get(conversation.workspace_id)
        try:
            baseline = services.store.get_run_baseline(run_id)
        except IDEStoreError:
            return WorkspaceChangeSet(
                run_id=run_id,
                baseline_captured_at=run.created_at,
                generated_at=run.updated_at,
                baseline_truncated=True,
                manifest_warning=(
                    "This run was created before change tracking was available. "
                    "No changed-file claims are shown."
                ),
                files=(),
            )
        terminal_states = {
            RunState.COMPLETED,
            RunState.FAILED,
            RunState.BLOCKED,
            RunState.CANCELLED,
        }
        if run.state in terminal_states:
            if manifest := services.store.get_run_change_manifest(run_id):
                return manifest
            return WorkspaceChangeSet(
                run_id=run_id,
                baseline_captured_at=baseline.captured_at,
                generated_at=run.updated_at,
                baseline_truncated=True,
                manifest_warning=(
                    "This run ended before immutable change evidence was recorded. "
                    "No changed-file claims are shown."
                ),
                files=(),
            )
        change_set = services.changes.compare(workspace.root, baseline).model_copy(
            update={"run_id": run_id},
        )
        run_events = tuple(
            event
            for event in services.events.iter_after(run.conversation_id, 0)
            if event.payload.get("run_id") == str(run_id)
        )
        return attribute_changes(change_set, run_events, root=workspace.root)

    @router.post("/runs/{run_id}/pause")
    def pause_agent_run(run_id: UUID) -> AgentRunRecord:
        return supervisor.pause(run_id)

    @router.post("/runs/{run_id}/resume")
    def resume_agent_run(run_id: UUID) -> AgentRunRecord:
        return supervisor.resume(run_id)

    @router.post("/runs/{run_id}/stop")
    def stop_agent_run(run_id: UUID) -> AgentRunRecord:
        return supervisor.stop(run_id)

    @router.get("/workspaces/{workspace_id}/session/approvals")
    def pending_approvals(
        workspace_id: UUID,
    ) -> tuple[ApprovalRequestRecord, ...]:
        session = current_session(workspace_id)
        return services.store.list_pending_approvals(session.id)

    def resolve_approval_error(exc: IDEStoreError) -> AgentAPIError:
        detail = str(exc).lower()
        if "cannot be granted" in detail:
            return AgentAPIError(
                400,
                "permission_category_not_grantable",
                "This action is too broad to approve by category. Approve only this action.",
            )
        code = "stale_revision" if "stale" in detail else "approval_not_found"
        status = 409 if code == "stale_revision" else 404
        message = (
            "The approval changed. Refresh before deciding again."
            if code == "stale_revision"
            else "The approval request was not found."
        )
        return AgentAPIError(status, code, message)

    @router.post("/approvals/{approval_id}/approve")
    def approve_agent_action(
        approval_id: UUID, payload: ResolveAgentApprovalRequest
    ) -> AgentRunRecord:
        try:
            return supervisor.approve(approval_id, payload.expected_revision)
        except IDEStoreError as exc:
            raise resolve_approval_error(exc) from exc

    @router.post("/approvals/{approval_id}/approve-category")
    def approve_agent_action_category(
        approval_id: UUID, payload: ResolveAgentApprovalRequest
    ) -> AgentRunRecord:
        try:
            return supervisor.approve_category(approval_id, payload.expected_revision)
        except IDEStoreError as exc:
            raise resolve_approval_error(exc) from exc

    @router.post("/approvals/{approval_id}/deny")
    def deny_agent_action(approval_id: UUID, payload: DenyAgentApprovalRequest) -> AgentRunRecord:
        try:
            return supervisor.deny(approval_id, payload.expected_revision, payload.reason)
        except IDEStoreError as exc:
            raise resolve_approval_error(exc) from exc

    @router.get("/workspaces/{workspace_id}/session/events")
    async def session_events(
        workspace_id: UUID,
        request: Request,
        after: int = Query(default=0, ge=0),
        follow: bool = True,
    ) -> StreamingResponse:
        cursor = _event_cursor(request, after)
        session = current_session(workspace_id)
        conversation_id = session.id

        if not follow:
            rows = services.events.iter_after(conversation_id, cursor)
            return StreamingResponse(
                (format_sse(event) for event in rows),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        async def stream() -> AsyncIterator[str]:
            active_cursor = cursor
            last_output = time.monotonic()
            while not await request.is_disconnected():
                rows = services.events.list_after(conversation_id, active_cursor)
                if rows:
                    for event in rows:
                        active_cursor = event.id
                        last_output = time.monotonic()
                        yield format_sse(event)
                    continue
                if time.monotonic() - last_output >= 15:
                    last_output = time.monotonic()
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.25)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
