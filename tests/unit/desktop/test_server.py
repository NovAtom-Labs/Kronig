import socket
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import tcad_agent.desktop.server as desktop_server
from tcad_agent.desktop.auth import DesktopAuth
from tcad_agent.desktop.config import DesktopLaunchConfig
from tcad_agent.desktop.server import (
    bind_desktop_socket,
    create_desktop_app,
    readiness_record,
    serve_desktop,
)
from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.models import AgentRunRecord, ApprovalDecision, RunState
from tcad_agent.ide.store import IDEStoreError, SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import IDEServices


def _desktop_config(data_dir: Path) -> DesktopLaunchConfig:
    return DesktopLaunchConfig(
        host="127.0.0.1",
        port=0,
        launch_token="x" * 43,
        data_dir=data_dir,
    )


def test_readiness_record_has_fixed_protocol_fields(tmp_path: Path) -> None:
    config = DesktopLaunchConfig(
        host="127.0.0.1",
        port=0,
        launch_token="x" * 43,
        data_dir=tmp_path,
    )

    assert readiness_record(
        config,
        url="http://127.0.0.1:49152",
        pid=312,
        fingerprint="a1b2c3d4",
    ) == {
        "protocol": 1,
        "url": "http://127.0.0.1:49152",
        "pid": 312,
        "runtime_fingerprint": "a1b2c3d4",
    }


def test_desktop_socket_uses_loopback_and_operating_system_port(tmp_path: Path) -> None:
    config = DesktopLaunchConfig(
        host="127.0.0.1",
        port=0,
        launch_token="x" * 43,
        data_dir=tmp_path,
    )

    listener = bind_desktop_socket(config)
    try:
        host, port = listener.getsockname()
        assert host == "127.0.0.1"
        assert isinstance(port, int) and port > 0
        with socket.create_connection((host, port), timeout=0.2):
            pass
    finally:
        listener.close()


def test_create_desktop_app_uses_temporary_runtime_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime_root = tmp_path / "sessions" / "session-one"
    runtime_root.mkdir(parents=True)
    services = object()
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        desktop_server, "build_default_ide_services", lambda: services
    )

    def capture_create_app(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(desktop_server, "create_app", capture_create_app)

    create_desktop_app(_desktop_config(tmp_path), runtime_root)

    assert desktop_server.os.environ["TCAD_WORKSPACE"] == str(runtime_root)
    assert captured["ide"] is services


def test_serve_desktop_owns_storage_inside_data_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    runtime_root = tmp_path / "sessions" / "session-one"

    class FakeLock:
        def __init__(self, data_dir: Path) -> None:
            assert data_dir == tmp_path

        def __enter__(self) -> None:
            events.append("lock-enter")

        def __exit__(self, *_args: object) -> None:
            events.append("lock-exit")

    class FakeStorage:
        def __init__(self) -> None:
            self.runtime_root = runtime_root

        @classmethod
        def prepare(cls, data_dir: Path) -> "FakeStorage":
            assert data_dir == tmp_path
            assert events == ["lock-enter"]
            events.append("storage-prepare")
            return cls()

        def cleanup(self) -> None:
            events.append("storage-cleanup")

    class FakeListener:
        def getsockname(self) -> tuple[str, int]:
            return ("127.0.0.1", 45123)

        def close(self) -> None:
            events.append("listener-close")

    class FakeServer:
        def __init__(self, _config: object) -> None:
            pass

        def run(self, *, sockets: list[object]) -> None:
            assert len(sockets) == 1
            events.append("server-run")

    monkeypatch.setattr(desktop_server, "DataDirectoryLock", FakeLock)
    monkeypatch.setattr(desktop_server, "DesktopSessionStorage", FakeStorage, raising=False)
    monkeypatch.setattr(desktop_server, "bind_desktop_socket", lambda _config: FakeListener())
    monkeypatch.setattr(desktop_server.uvicorn, "Config", lambda app, **_kwargs: app)
    monkeypatch.setattr(desktop_server.uvicorn, "Server", FakeServer)

    def capture_app(_config: DesktopLaunchConfig, root: Path) -> object:
        assert root == runtime_root
        events.append("app-create")
        return object()

    monkeypatch.setattr(desktop_server, "create_desktop_app", capture_app)

    serve_desktop(_desktop_config(tmp_path))

    assert events == [
        "lock-enter",
        "storage-prepare",
        "app-create",
        "server-run",
        "listener-close",
        "storage-cleanup",
        "lock-exit",
    ]


def test_serve_desktop_cleans_storage_after_startup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cleaned = False

    class FakeStorage:
        runtime_root = tmp_path / "sessions" / "session-one"

        @classmethod
        def prepare(cls, _data_dir: Path) -> "FakeStorage":
            return cls()

        def cleanup(self) -> None:
            nonlocal cleaned
            cleaned = True

    monkeypatch.setattr(desktop_server, "DesktopSessionStorage", FakeStorage, raising=False)
    monkeypatch.setattr(
        desktop_server,
        "bind_desktop_socket",
        lambda _config: (_ for _ in ()).throw(OSError("bind failed")),
    )

    with pytest.raises(OSError, match="bind failed"):
        serve_desktop(_desktop_config(tmp_path))

    assert cleaned is True


def test_desktop_status_reports_active_run_state(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    client = TestClient(create_app(ide=services))
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    conversation = services.conversations.create(workspace.id, "Desktop status")
    run = store.create_run(conversation.id, uuid4())

    assert client.get("/api/desktop/status").json() == {"active": True}

    store.transition_run(run.id, run.revision, RunState.COMPLETED)
    assert client.get("/api/desktop/status").json() == {"active": False}


@pytest.mark.parametrize(
    "quiescent_state",
    [
        RunState.WAITING_FOR_APPROVAL,
        RunState.WAITING_FOR_USER,
        RunState.PAUSED,
    ],
)
def test_desktop_status_does_not_block_on_persisted_quiescent_run(
    tmp_path: Path, quiescent_state: RunState
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    client = TestClient(create_app(ide=services))
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    conversation = services.conversations.create(workspace.id, "Persisted run")
    run = store.create_run(conversation.id, uuid4())
    if quiescent_state is RunState.PAUSED:
        run = store.transition_run(run.id, run.revision, RunState.RUNNING)
    store.transition_run(run.id, run.revision, quiescent_state)

    assert client.get("/api/desktop/status").json() == {"active": False}


def test_desktop_shutdown_allows_persisted_approval_wait(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    token = "desktop-token-" + "w" * 32
    client = TestClient(
        create_app(ide=services, desktop_auth=DesktopAuth(token)),
        follow_redirects=False,
    )
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    conversation = services.conversations.create(workspace.id, "Approval wait")
    run = store.create_run(conversation.id, uuid4())
    store.transition_run(run.id, run.revision, RunState.WAITING_FOR_APPROVAL)

    response = client.post(
        "/api/desktop/prepare-shutdown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"ready": True}


def test_desktop_shutdown_cancels_active_workspace_session(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    token = "desktop-token-" + "e" * 32

    class ShutdownSupervisor:
        def __init__(self) -> None:
            self.denied: list[ApprovalDecision] = []

        def active_run_for_workspace(
            self, workspace_id: UUID
        ) -> AgentRunRecord | None:
            return next(
                (
                    run
                    for run in store.list_runs_for_workspace(workspace_id)
                    if run.state
                    in {
                        RunState.QUEUED,
                        RunState.RUNNING,
                        RunState.WAITING_FOR_APPROVAL,
                    }
                ),
                None,
            )

        def stop(self, run_id: UUID) -> AgentRunRecord:
            run = store.get_run(run_id)
            for approval in store.list_pending_approvals(run.conversation_id):
                resolved = store.resolve_approval(
                    approval.id, approval.revision, ApprovalDecision.DENY
                )
                assert resolved.decision is not None
                self.denied.append(resolved.decision)
            current = store.get_run(run_id)
            return store.transition_run(
                run_id, current.revision, RunState.CANCELLED
            )

        def join(self, run_id: UUID, timeout: float | None = None) -> bool:
            del run_id, timeout
            return True

    supervisor = ShutdownSupervisor()
    client = TestClient(
        create_app(
            ide=services,
            agent_supervisor=supervisor,  # type: ignore[arg-type]
            desktop_auth=DesktopAuth(token),
        ),
        follow_redirects=False,
    )
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    session = services.sessions.open(workspace.id)
    run = store.create_run(session.id, session.id)
    approval = store.create_approval(
        run.id,
        "action-1",
        "terminal",
        "HIGH",
        "Send changes to a remote repository",
        {"command": "git push"},
    )

    response = client.post(
        "/api/desktop/prepare-shutdown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"ready": True}
    assert supervisor.denied == [ApprovalDecision.DENY]
    assert services.sessions.current() is None
    with pytest.raises(IDEStoreError):
        store.get_approval(approval.id)


def test_desktop_shutdown_refuses_to_delete_session_while_runtime_stops(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    services = IDEServices(
        workspaces=WorkspaceManager(store),
        conversations=ConversationService(store, events),
        events=events,
    )
    token = "desktop-token-" + "t" * 32

    class SlowShutdownSupervisor:
        def active_run_for_workspace(
            self, workspace_id: UUID
        ) -> AgentRunRecord | None:
            return next(iter(store.list_runs_for_workspace(workspace_id)), None)

        def stop(self, run_id: UUID) -> AgentRunRecord:
            run = store.get_run(run_id)
            return store.transition_run(
                run_id, run.revision, RunState.CANCELLED
            )

        def join(self, run_id: UUID, timeout: float | None = None) -> bool:
            del run_id, timeout
            return False

    client = TestClient(
        create_app(
            ide=services,
            agent_supervisor=SlowShutdownSupervisor(),  # type: ignore[arg-type]
            desktop_auth=DesktopAuth(token),
        )
    )
    root = tmp_path / "repo"
    root.mkdir()
    workspace = services.workspaces.open(root)
    session = services.sessions.open(workspace.id)
    store.create_run(session.id, session.id)

    response = client.post(
        "/api/desktop/prepare-shutdown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "desktop_work_active",
        "message": "The agent run is still stopping. Try closing Agent Kronig again.",
    }
    assert services.sessions.current() == session
    assert store.get_conversation(session.id).id == session.id
