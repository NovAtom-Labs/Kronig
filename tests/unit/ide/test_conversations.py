from pathlib import Path

from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.store import SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager


def test_conversation_messages_and_events_survive_restart(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    database = tmp_path / "ide.sqlite3"
    first_store = SqliteIDEStore(database)
    workspace = WorkspaceManager(first_store).open(root)
    first_service = ConversationService(first_store, EventFeed(first_store))
    conversation = first_service.create(workspace.id, "PN junction")
    message = first_service.add_user_message(conversation.id, "Inspect the repository")

    second_store = SqliteIDEStore(database)
    second_service = ConversationService(second_store, EventFeed(second_store))

    assert second_service.get(conversation.id).title == "PN junction"
    assert second_service.messages(conversation.id) == (message,)
    events = EventFeed(second_store).list_after(conversation.id, after_id=0)
    assert [event.kind for event in events] == [
        "conversation_created",
        "message_created",
    ]


def test_assistant_message_is_persisted_with_lifecycle_event(tmp_path: Path) -> None:
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    service = ConversationService(store, EventFeed(store))
    conversation = service.create(workspace.id, "Agent task")

    message = service.add_assistant_message(conversation.id, "Tests pass")

    assert service.messages(conversation.id) == (message,)
    assert message.role == "assistant"
    events = EventFeed(store).list_after(conversation.id, after_id=0)
    assert [event.kind for event in events] == [
        "conversation_created",
        "message_created",
    ]
    assert events[-1].payload == {
        "message_id": str(message.id),
        "role": "assistant",
    }
