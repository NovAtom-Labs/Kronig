from __future__ import annotations

from pathlib import Path

from tcad_agent.prompting.context import LocalEvidenceCollector, WorkspaceContextCollector


def test_workspace_context_is_bounded_and_excludes_credentials(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("research notes")
    (tmp_path / ".env").write_text("TOKEN=secret")
    (tmp_path / "private.pem").write_text("secret")
    (tmp_path / ".tcad-agent").mkdir()
    (tmp_path / ".tcad-agent" / "state.json").write_text("{}")
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("outside")
    (tmp_path / "escape").symlink_to(outside)

    context = WorkspaceContextCollector(max_files=10).collect(tmp_path)

    assert [item.path for item in context.files] == ["README.md"]
    assert context.inventory_hash


def test_workspace_inventory_truncates_deterministically(tmp_path: Path) -> None:
    for index in range(5):
        (tmp_path / f"file-{index}.txt").write_text(str(index))

    context = WorkspaceContextCollector(max_files=3).collect(tmp_path)

    assert [item.path for item in context.files] == [
        "file-0.txt",
        "file-1.txt",
        "file-2.txt",
    ]
    assert context.inventory_truncated is True


class FakeKnowledgeIndex:
    def search(self, query: str, filters=None, limit: int = 5):
        from tcad_agent.knowledge.models import Citation, SearchHit

        del filters
        return tuple(
            SearchHit(
                id=f"source:{index}",
                content=(f"{query} evidence {index} " * 50),
                backend="portable",
                score=1.0 - index / 10,
                reviewed=True,
                citation=Citation(
                    source_id=f"source-{index}",
                    title=f"Source {index}",
                    url=f"https://example.invalid/{index}",
                    version="1.0",
                    content_hash=f"{index:x}" * 64,
                ),
            )
            for index in range(limit)
        )


def test_local_evidence_enforces_passage_and_character_budgets() -> None:
    evidence = LocalEvidenceCollector(
        FakeKnowledgeIndex(), max_searches=2, max_passages=3, max_characters=700
    ).collect("equilibrium field", ("temperature 300 K",))

    assert len(evidence) == 3
    assert sum(len(item.content) for item in evidence) <= 700
    assert len({item.id for item in evidence}) == len(evidence)


def test_inventory_tolerates_a_file_removed_during_collection(tmp_path, monkeypatch):
    (tmp_path / "temporary.txt").write_text("ephemeral")
    collector = WorkspaceContextCollector()
    monkeypatch.setattr(
        collector, "_file_context", lambda *args: (_ for _ in ()).throw(FileNotFoundError())
    )
    assert collector.collect(tmp_path).files == ()
