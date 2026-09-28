"""FastAPI surface for the local TCAD researcher workflow."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tcad_agent.agent.runtime import OpenHandsRuntimeFactory
from tcad_agent.agent.supervisor import AgentSupervisor
from tcad_agent.desktop.auth import (
    DesktopAuth,
    DesktopSessionMiddleware,
    DesktopShutdownGate,
    DesktopShutdownMiddleware,
)
from tcad_agent.ide.conversations import ConversationInputError
from tcad_agent.ide.models import RunState
from tcad_agent.ide.paths import WorkspacePathError
from tcad_agent.ide.sessions import WorkspaceSessionBusyError
from tcad_agent.ide.store import ConversationNotFoundError, WorkspaceNotFoundError
from tcad_agent.web.ide_routes import (
    AgentAPIError,
    IDEServices,
    build_default_ide_services,
    build_ide_router,
)
from tcad_agent.web.runtime import runtime_fingerprint


def create_app(
    *,
    runtime_id: str | None = None,
    ide: IDEServices | None = None,
    agent_supervisor: AgentSupervisor | None = None,
    desktop_auth: DesktopAuth | None = None,
) -> FastAPI:
    ide_services = ide or build_default_ide_services()
    active_supervisor = agent_supervisor or AgentSupervisor(
        ide_services, OpenHandsRuntimeFactory(ide_services.runtime_root)
    )
    ide_services.sessions.bind_supervisor(active_supervisor)
    active_runtime_id = runtime_id or runtime_fingerprint()
    package_root = Path(__file__).parent
    templates = Jinja2Templates(directory=package_root / "templates")
    app = FastAPI(title="NovAtom TCAD Agent", docs_url=None, redoc_url=None)
    shutdown_gate = DesktopShutdownGate()
    if desktop_auth is not None:
        app.add_middleware(DesktopShutdownMiddleware, gate=shutdown_gate)
        app.add_middleware(DesktopSessionMiddleware, auth=desktop_auth)
    app.mount("/static", StaticFiles(directory=package_root / "static"), name="static")
    app.include_router(build_ide_router(ide_services, active_supervisor))

    @app.exception_handler(AgentAPIError)
    async def agent_api_error(_request: Request, exc: AgentAPIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(WorkspacePathError)
    async def invalid_workspace_path(_request: Request, _exc: WorkspacePathError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "code": "invalid_workspace_path",
                "message": "The workspace path is unavailable or invalid.",
            },
        )

    @app.exception_handler(ConversationInputError)
    async def invalid_conversation_input(
        _request: Request, exc: ConversationInputError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"code": "invalid_conversation_input", "message": str(exc)},
        )

    @app.exception_handler(WorkspaceNotFoundError)
    async def workspace_not_found(_request: Request, _exc: WorkspaceNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "code": "workspace_not_found",
                "message": "The workspace was not found.",
            },
        )

    @app.exception_handler(ConversationNotFoundError)
    async def conversation_not_found(
        _request: Request, _exc: ConversationNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "code": "conversation_not_found",
                "message": "The conversation was not found.",
            },
        )

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": ("The request failed without exposing provider or credential details."),
            },
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "runtime_fingerprint": active_runtime_id}

    def has_active_work() -> bool:
        active_states = {
            RunState.QUEUED,
            RunState.RUNNING,
        }
        return bool(ide_services.store.list_runs_in_states(active_states))

    @app.get("/api/desktop/status")
    def desktop_status() -> dict[str, bool]:
        return {"active": has_active_work()}

    @app.post("/api/desktop/prepare-shutdown")
    def desktop_prepare_shutdown(request: Request) -> JSONResponse:
        if desktop_auth is None:
            raise HTTPException(status_code=404, detail="Desktop mode is unavailable.")
        authorization = request.headers.get("authorization", "")
        scheme, _, candidate = authorization.partition(" ")
        if scheme.lower() != "bearer" or not desktop_auth.is_control_token(candidate):
            return JSONResponse(
                status_code=403,
                content={
                    "code": "desktop_control_required",
                    "message": "Desktop lifecycle authentication failed.",
                },
            )
        try:
            ide_services.sessions.shutdown()
        except WorkspaceSessionBusyError as exc:
            return JSONResponse(
                status_code=409,
                content={
                    "code": "desktop_work_active",
                    "message": str(exc),
                },
            )
        if not shutdown_gate.commit_if_idle(has_active_work):
            return JSONResponse(
                status_code=409,
                content={
                    "code": "desktop_work_active",
                    "message": "Finish or stop active work before closing Agent Kronig.",
                },
            )
        return JSONResponse(content={"ready": True})

    @app.get("/desktop/bootstrap")
    def desktop_bootstrap(request: Request) -> Response:
        if desktop_auth is None:
            raise HTTPException(status_code=404, detail="Desktop mode is unavailable.")
        token = request.query_params.get("token", "")
        if not desktop_auth.consume_launch_token(token):
            raise HTTPException(status_code=403, detail="Invalid desktop launch token.")
        response = RedirectResponse("/", status_code=303)
        desktop_auth.attach_session(response)
        return response

    @app.get("/")
    def index(request: Request) -> Response:
        return templates.TemplateResponse(request, "ide.html", {})

    @app.get("/workspaces/{workspace_id}")
    def workspace_page(request: Request, workspace_id: UUID) -> Response:
        del workspace_id
        return templates.TemplateResponse(request, "ide.html", {})

    return app
