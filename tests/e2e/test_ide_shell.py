from pathlib import Path

from fastapi.testclient import TestClient

from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import IDEServices


def test_workspace_route_restores_current_process_session_activity(
    tmp_path: Path,
) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    events = EventFeed(store)
    app = create_app(
        ide=IDEServices(
            workspaces=WorkspaceManager(store),
            conversations=ConversationService(store, events),
            events=events,
        )
    )
    web = TestClient(app)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "experiment.yaml").write_text("name: reference\n")

    workspace = web.post("/api/workspaces", json={"path": str(root)}).json()
    session_url = f"/api/workspaces/{workspace['id']}/session"
    web.post(session_url)
    posted = web.post(
        f"{session_url}/messages",
        json={"content": "Inspect the experiment definition"},
    )

    restored_page = web.get(f"/workspaces/{workspace['id']}")
    restored_messages = web.get(f"{session_url}/messages").json()
    restored_events = web.get(f"{session_url}/events?follow=false").text

    assert posted.status_code == 201
    assert restored_page.status_code == 200
    assert 'id="agent-panel"' in restored_page.text
    assert 'id="run-controls"' in restored_page.text
    assert 'id="pause-run"' in restored_page.text
    assert 'id="resume-run"' in restored_page.text
    assert 'id="stop-run"' in restored_page.text
    assert 'id="pending-approvals"' in restored_page.text
    assert 'src="/static/novatom-atom-mark.svg"' in restored_page.text
    assert '<span class="company-nov">Nov</span>' in restored_page.text
    assert '<span class="company-atom-text">Atom</span>' in restored_page.text
    assert 'id="explorer-resizer"' in restored_page.text
    assert 'id="agent-resizer"' in restored_page.text
    assert restored_page.text.count('role="separator"') == 2
    assert 'id="toggle-explorer-panel"' in restored_page.text
    assert 'class="edge-reveal edge-reveal-left"' in restored_page.text
    assert 'class="edge-reveal edge-reveal-right"' in restored_page.text
    assert 'id="close-workspace-browser"' in restored_page.text
    assert 'data-agent-view="chat"' in restored_page.text
    assert 'data-agent-view="activity"' in restored_page.text
    assert 'data-agent-view="changes"' in restored_page.text
    assert 'role="tablist"' in restored_page.text
    assert restored_page.text.count('role="tab"') == 3
    assert restored_page.text.count('role="tabpanel"') == 3
    assert 'id="agent-view-chat"' in restored_page.text
    assert 'id="agent-view-activity"' in restored_page.text
    assert 'id="agent-view-changes"' in restored_page.text
    assert 'id="session-state"' in restored_page.text
    assert 'id="session-messages"' in restored_page.text
    assert 'id="conversation-select"' not in restored_page.text
    assert 'id="create-conversation"' not in restored_page.text
    assert 'id="conversation-dialog"' not in restored_page.text
    assert 'id="agent-run-summary"' in restored_page.text
    assert 'id="agent-reasoning"' in restored_page.text
    assert 'id="agent-changes"' in restored_page.text
    assert 'src="/static/results-workbench.js?v=20260927-1"' in restored_page.text
    assert "Foundation slice" not in restored_page.text
    assert [message["content"] for message in restored_messages] == [
        "Inspect the experiment definition"
    ]
    assert "event: conversation_created" in restored_events
    assert "event: message_created" in restored_events


def test_results_workbench_asset_is_served_by_desktop_shell(tmp_path: Path) -> None:
    web = TestClient(create_app())

    response = web.get("/static/results-workbench.js")

    assert response.status_code == 200
    assert "AgentKronigResults" in response.text
    assert "results-workbench" in response.text
