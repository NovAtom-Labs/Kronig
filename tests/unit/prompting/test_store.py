from __future__ import annotations

from pathlib import Path

import pytest

from tcad_agent.ide.conversations import ConversationService
from tcad_agent.ide.events import EventFeed
from tcad_agent.ide.store import IDEStoreError, SqliteIDEStore
from tcad_agent.ide.workspaces import WorkspaceManager
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    ClarificationQuestion,
    EvidenceExcerpt,
    IntentField,
    IntentOrigin,
    PreparationDecision,
    ResolvedResearchIntent,
    WorkspaceContext,
)


def run_store(tmp_path: Path):
    store = SqliteIDEStore(tmp_path / "ide.sqlite3")
    workspace = WorkspaceManager(store).open(tmp_path)
    conversation = ConversationService(store, EventFeed(store)).create(
        workspace.id, "Prompt preparation"
    )
    return store, store.create_run(conversation.id, conversation.id)


def clarification() -> PreparationDecision:
    return PreparationDecision(
        status="clarification",
        summary="Temperature is required.",
        questions=(
            ClarificationQuestion(
                id="temperature",
                field_path="study.temperature",
                prompt="What temperature should be used?",
                reason="The result depends on temperature.",
            ),
        ),
        unresolved_critical=("study.temperature",),
    )


def test_prompt_preparation_round_trip_and_revision_guard(tmp_path: Path) -> None:
    store, run = run_store(tmp_path)
    created = store.create_prompt_preparation(run.id, "Run the requested study")

    updated = store.update_prompt_preparation(
        run.id,
        created.revision,
        answers=(ClarificationAnswer(question_id="temperature", answer="300 K"),),
        decision=clarification(),
        compiled_request=None,
    )

    restored = SqliteIDEStore(store.path).get_prompt_preparation(run.id)
    assert restored == updated
    assert restored.answers[0].answer == "300 K"
    with pytest.raises(IDEStoreError, match="stale"):
        store.update_prompt_preparation(
            run.id,
            created.revision,
            answers=(),
            decision=None,
            compiled_request=None,
        )


def test_prompt_preparation_cannot_change_after_compilation(tmp_path: Path) -> None:
    from tcad_agent.prompting.compiler import PromptCompiler

    store, run = run_store(tmp_path)
    created = store.create_prompt_preparation(run.id, "Run it")
    ready = PreparationDecision(
        status="ready",
        summary="Ready",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Run it",
            fields=(
                IntentField(
                    path="study.temperature",
                    value="300 K",
                    origin=IntentOrigin.RESEARCHER,
                ),
            ),
        ),
    )
    workspace = WorkspaceContext(
        display_name="repo",
        git_available=False,
        git_dirty=False,
        inventory_hash="a" * 64,
    )
    excerpts = (
        EvidenceExcerpt(
            id="source:1",
            title="Source",
            url="https://example.invalid/source",
            version="1",
            content_hash="b" * 64,
            reviewed=True,
            content="Evidence",
        ),
    )
    compiled = PromptCompiler().compile(
        original_prompt="Run it",
        answers=(),
        decision=ready,
        workspace=workspace,
        evidence=excerpts,
        capability_hashes={"devsim": "e" * 64},
    )
    saved = store.update_prompt_preparation(
        run.id,
        created.revision,
        answers=(),
        decision=ready,
        compiled_request=compiled,
    )

    with pytest.raises(IDEStoreError, match="immutable"):
        store.update_prompt_preparation(
            run.id,
            saved.revision,
            answers=(),
            decision=ready,
            compiled_request=compiled,
        )
