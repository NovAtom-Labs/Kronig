from pathlib import Path

from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed, format_sse
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager


def test_event_cursor_is_strictly_after_and_sse_has_an_id(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    root = tmp_path / "repo"
    root.mkdir()
    workspace = WorkspaceManager(store).open(root)
    conversation = ConversationService(store, EventFeed(store)).create(workspace.id, "Reference")
    feed = EventFeed(store)
    first = feed.append(conversation.id, "status_changed", {"status": "idle"})
    second = feed.append(conversation.id, "status_changed", {"status": "running"})

    assert feed.list_after(conversation.id, after_id=first.id) == (second,)
    assert format_sse(second).startswith(f"id: {second.id}\nevent: status_changed\ndata: ")
