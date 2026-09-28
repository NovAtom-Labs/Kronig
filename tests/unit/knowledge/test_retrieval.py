from pathlib import Path

import pytest

from tcad_agent.knowledge.ingest import KnowledgeIngestor
from tcad_agent.knowledge.models import Passage, SourceManifest
from tcad_agent.knowledge.retrieve import KnowledgeIndex


def passage(
    passage_id: str,
    content: str,
    *,
    version: str,
    reviewed: bool,
    backend: str = "devsim",
    compatible_versions: tuple[str, ...] = (),
) -> Passage:
    return Passage.create(
        id=passage_id,
        source_id=f"source-{passage_id}",
        title=f"Source {passage_id}",
        url=f"https://example.invalid/{passage_id}",
        license="Apache-2.0",
        access="public",
        trust="primary",
        backend=backend,
        version=version,
        compatible_versions=compatible_versions,
        reviewed=reviewed,
        content=content,
    )


def build_test_index(path: Path, passages: list[Passage]) -> KnowledgeIndex:
    return KnowledgeIndex.build(path / "knowledge.sqlite3", passages)


def test_reviewed_version_compatible_source_outranks_stale_source(tmp_path: Path) -> None:
    index = build_test_index(
        tmp_path,
        passages=[
            passage("old", "DEVSIM contact equation", version="1.0", reviewed=False),
            passage("current", "DEVSIM contact equation", version="2.9", reviewed=True),
        ],
    )
    hits = index.search(
        "contact equation",
        filters={"backend": "devsim", "version": "2.9"},
        limit=2,
    )
    assert [hit.id for hit in hits] == ["current"]
    assert hits[0].citation.source_id


def test_version_filter_accepts_explicitly_reviewed_compatible_documentation(
    tmp_path: Path,
) -> None:
    index = build_test_index(
        tmp_path,
        passages=[
            passage(
                "manual-2-9-0",
                "DEVSIM solve maximum_iterations convergence",
                version="2.9.0",
                compatible_versions=("2.9.1",),
                reviewed=True,
            )
        ],
    )

    hits = index.search(
        "solve maximum iterations",
        filters={"backend": "devsim", "version": "2.9.1"},
        limit=2,
    )

    assert [hit.id for hit in hits] == ["manual-2-9-0"]
    assert hits[0].citation.version == "2.9.0"


def test_retrieval_keeps_primary_source_diversity_in_small_context_window(
    tmp_path: Path,
) -> None:
    examples = [
        Passage.create(
            id=f"example:{index}",
            source_id="devsim-source",
            title="DEVSIM example",
            url="https://github.com/devsim/devsim",
            license="Apache-2.0",
            access="public",
            trust="primary",
            backend="devsim",
            version="2.9.1",
            reviewed=True,
            content=("solve maximum_iterations convergence " * (20 - index)).strip(),
        )
        for index in range(10)
    ]
    manual = Passage.create(
        id="manual:solve",
        source_id="devsim-manual",
        title="DEVSIM command reference",
        url="https://devsim.net/",
        license="CC-BY-ND-4.0",
        access="public",
        trust="primary",
        backend="devsim",
        version="2.9.0",
        compatible_versions=("2.9.1",),
        reviewed=True,
        content="solve maximum_iterations convergence command reference",
    )
    index = build_test_index(tmp_path, [*examples, manual])

    hits = index.search(
        "solve maximum iterations convergence",
        filters={"backend": "devsim", "version": "2.9.1"},
        limit=5,
    )

    assert {hit.citation.source_id for hit in hits} == {
        "devsim-source",
        "devsim-manual",
    }


def test_backend_filter_excludes_sentaurus_text(tmp_path: Path) -> None:
    index = build_test_index(
        tmp_path,
        [
            passage("devsim", "mobility model", version="2.9", reviewed=True),
            passage(
                "sentaurus",
                "mobility model",
                version="2025.09",
                reviewed=True,
                backend="sentaurus",
            ),
        ],
    )
    hits = index.search("mobility model", {"backend": "devsim"}, 5)
    assert hits
    assert all(hit.backend == "devsim" for hit in hits)


def test_ingest_local_directory_indexes_authorized_text_files(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "manual.md").write_text("# Contacts\n\nOhmic boundary equation.")
    (corpus / "example.py").write_text("def create_contact():\n    pass\n")
    (corpus / "ignored.bin").write_bytes(b"\x00\x01")
    source = SourceManifest(
        id="local-corpus",
        title="Local corpus",
        url="https://example.invalid/corpus",
        license="Apache-2.0",
        access="public",
        trust="primary",
        backend="devsim",
        version="1.0",
        reviewed=True,
        local_path="corpus",
    )

    passages = KnowledgeIngestor().ingest_local(source, tmp_path)

    assert len(passages) >= 2
    assert len({passage.id for passage in passages}) == len(passages)
    content = "\n".join(passage.content for passage in passages)
    assert "manual.md" in content
    assert "example.py" in content


def test_markdown_chunks_keep_section_heading_with_scientific_evidence() -> None:
    source = SourceManifest(
        id="portable-physics",
        title="Portable physics",
        url="internal://portable-physics",
        license="internal",
        access="restricted",
        trust="secondary",
        backend="portable",
        version="1.0",
        reviewed=False,
    )
    text = (
        "# Semiconductor equations\n\n"
        "Scope and assumptions.\n\n"
        "## Equilibrium expectations\n\n"
        "At equilibrium the Fermi level is spatially constant.\n\n"
        "Net terminal current should approach zero within tolerance.\n"
    )

    passages = KnowledgeIngestor().ingest_text(source, text)

    assert all(
        not item.content.startswith("## Equilibrium expectations\n\n##")
        for item in passages
    )
    assert any(
        "## Equilibrium expectations" in item.content
        and "Fermi level is spatially constant" in item.content
        for item in passages
    )
    assert any(
        "## Equilibrium expectations" in item.content
        and "Net terminal current" in item.content
        for item in passages
    )
    assert not any(item.content == "## Equilibrium expectations" for item in passages)


def test_python_separator_comments_are_not_mistaken_for_markdown_headings() -> None:
    source = SourceManifest(
        id="devsim-source",
        title="DEVSIM source",
        url="https://github.com/devsim/devsim",
        license="Apache-2.0",
        access="public",
        trust="primary",
        backend="devsim",
        version="2.9.1",
        reviewed=True,
    )

    passages = KnowledgeIngestor().ingest_text(
        source,
        '###\nsolve(type="dc", maximum_iterations=30)\n',
    )

    assert passages == (
        Passage.create(
            id="devsim-source:0",
            source_id="devsim-source",
            title="DEVSIM source",
            url="https://github.com/devsim/devsim",
            license="Apache-2.0",
            access="public",
            trust="primary",
            backend="devsim",
            version="2.9.1",
            compatible_versions=(),
            reviewed=True,
            content='###\nsolve(type="dc", maximum_iterations=30)',
        ),
    )


def test_ingest_local_directory_rejects_symlink_escape(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("restricted text")
    (corpus / "escape.md").symlink_to(outside)
    source = SourceManifest(
        id="local-corpus",
        title="Local corpus",
        url="https://example.invalid/corpus",
        license="internal",
        access="restricted",
        trust="internal-reviewed",
        backend="portable",
        version="1.0",
        reviewed=True,
        local_path="corpus",
    )

    with pytest.raises(ValueError, match="escapes the approved root"):
        KnowledgeIngestor().ingest_local(source, tmp_path)
