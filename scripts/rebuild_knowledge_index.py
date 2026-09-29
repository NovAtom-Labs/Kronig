#!/usr/bin/env python3
"""Rebuild the generated local knowledge index from every available approved source."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tcad_agent.knowledge.ingest import KnowledgeIngestor  # noqa: E402
from tcad_agent.knowledge.models import Passage, SourceManifest  # noqa: E402
from tcad_agent.knowledge.retrieve import KnowledgeIndex  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("knowledge-sources/index/knowledge.sqlite3"),
    )
    arguments = parser.parse_args()
    project_root = arguments.project_root.resolve(strict=True)
    manifest_path = project_root / "knowledge-sources/manifests/sources.yaml"
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    sources = tuple(
        SourceManifest.model_validate(item) for item in document.get("sources", ())
    )
    roots = (project_root, project_root.parent)
    ingestor = KnowledgeIngestor()
    passages: list[Passage] = []
    used_sources: set[str] = set()
    for source in sources:
        if source.local_path is None:
            continue
        source_root = next(
            (root for root in roots if (root / source.local_path).exists()),
            None,
        )
        if source_root is None:
            continue
        passages.extend(ingestor.ingest_local(source, source_root))
        used_sources.add(source.id)
    if not passages:
        raise RuntimeError("no approved local knowledge sources are available")

    destination = arguments.index
    if not destination.is_absolute():
        destination = project_root / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staged = Path(temporary) / "knowledge.sqlite3"
        KnowledgeIndex.build(staged, passages)
        staged.replace(destination)
    print(
        f"indexed {len(passages)} passages from {len(used_sources)} sources "
        f"at {destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
