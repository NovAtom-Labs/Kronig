#!/usr/bin/env python3
"""Rebuild the generated local knowledge index from every available approved source."""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tcad_agent.knowledge.ingest import KnowledgeIngestor  # noqa: E402
from tcad_agent.knowledge.models import Passage, SourceManifest  # noqa: E402
from tcad_agent.knowledge.retrieve import KnowledgeIndex  # noqa: E402


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    ).stdout.strip()


def prepare_sources(project_root: Path, sources: tuple[SourceManifest, ...]) -> None:
    """Fetch declared public revisions once; never reset an existing source tree."""
    roots = (project_root.resolve(), project_root.resolve().parent)
    for source in sources:
        if source.repository_path is None:
            continue
        relative = Path(source.repository_path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError("knowledge repository path must not escape its approved root")
        match = re.fullmatch(
            r"https://github\.com/([\w.-]+/[\w.-]+)/tree/([a-f0-9]{40})", source.url
        )
        if source.access != "public" or not source.reviewed or match is None:
            raise ValueError(f"{source.id}: source fetch requires a reviewed public Git revision")
        if (
            not source.local_path
            or ".." in Path(source.local_path).parts
            or not Path(source.local_path).is_relative_to(relative)
        ):
            raise ValueError(f"{source.id}: knowledge local path must not escape its repository")
        target = next(
            (root / relative for root in roots if (root / relative).exists()), roots[1] / relative
        )
        if not any(target.resolve().is_relative_to(root) for root in roots):
            raise ValueError("knowledge repository path escapes its approved root")
        revision = match[2]
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=".kronig-source-", dir=target.parent
            ) as temporary:
                staged = Path(temporary) / "checkout"
                staged.mkdir()
                _git(staged, "init")
                _git(
                    staged, "fetch", "--depth", "1", f"https://github.com/{match[1]}.git", revision
                )
                _git(staged, "checkout", "--detach", "FETCH_HEAD")
                if _git(staged, "rev-parse", "HEAD") != revision:
                    raise ValueError(f"{source.id}: fetched source revision does not match")
                staged.rename(target)
        if _git(target, "rev-parse", "HEAD") != revision:
            raise ValueError(
                f"{source.id}: existing source revision differs; source was not changed"
            )
        untracked = _git(target, "ls-files", "--others").splitlines()
        if _git(target, "diff", "--name-only", "HEAD", "--") or any(
            Path(path).suffix.lower() in KnowledgeIngestor.TEXT_SUFFIXES for path in untracked
        ):
            raise ValueError(
                f"{source.id}: modified source must be reviewed; source was not changed"
            )


def rebuild_index(
    project_root: Path, destination: Path, *, fetch_sources: bool = False, if_stale: bool = False
) -> None:
    project_root = project_root.resolve(strict=True)
    manifest_path = project_root / "knowledge-sources/manifests/sources.yaml"
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    sources = tuple(SourceManifest.model_validate(item) for item in document.get("sources", ()))
    if fetch_sources:
        prepare_sources(project_root, sources)
    roots = (project_root, project_root.parent)
    ingestor = KnowledgeIngestor()
    available = []
    digest = hashlib.sha256(b"kronig-knowledge-setup-v1\0" + manifest_path.read_bytes())
    digest.update(Path(__file__).read_bytes())
    for source in sources:
        if source.local_path is None:
            continue
        source_root = next((root for root in roots if (root / source.local_path).exists()), None)
        if source_root is None:
            continue
        available.append((source, source_root))
        path = source_root / source.local_path
        documents = (
            [path]
            if path.is_file()
            else sorted(
                item
                for item in path.rglob("*")
                if item.is_file() and item.suffix.lower() in ingestor.TEXT_SUFFIXES
            )
        )
        for item in documents:
            digest.update(
                source.id.encode() + b"\0" + item.relative_to(source_root).as_posix().encode()
            )
            digest.update(b"\0" + item.read_bytes() + b"\0")
    fingerprint = digest.hexdigest()
    if not destination.is_absolute():
        destination = project_root / destination
    if if_stale and destination.is_file():
        try:
            with closing(sqlite3.connect(destination)) as connection:
                receipt = connection.execute("SELECT input_digest FROM build_metadata").fetchone()
                healthy = connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
                populated = connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0] > 0
            if receipt == (fingerprint,) and healthy and populated:
                print(f"[ready] knowledge index unchanged: {destination}")
                return
        except sqlite3.Error:
            pass
    passages: list[Passage] = []
    used_sources: set[str] = set()
    for source, source_root in available:
        passages.extend(ingestor.ingest_local(source, source_root))
        used_sources.add(source.id)
    if not passages:
        raise RuntimeError("no approved local knowledge sources are available")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staged = Path(temporary) / "knowledge.sqlite3"
        KnowledgeIndex.build(staged, passages)
        with closing(sqlite3.connect(staged)) as connection, connection:
            connection.execute("CREATE TABLE build_metadata (input_digest TEXT NOT NULL)")
            connection.execute("INSERT INTO build_metadata VALUES (?)", (fingerprint,))
        staged.replace(destination)
    print(f"indexed {len(passages)} passages from {len(used_sources)} sources at {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--index", type=Path, default=Path("knowledge-sources/index/knowledge.sqlite3")
    )
    parser.add_argument(
        "--fetch-sources",
        action="store_true",
        help="fetch missing public Git revisions without resetting existing sources",
    )
    parser.add_argument("--if-stale", action="store_true", help="reuse an unchanged healthy index")
    arguments = parser.parse_args()
    rebuild_index(
        arguments.project_root,
        arguments.index,
        fetch_sources=arguments.fetch_sources,
        if_stale=arguments.if_stale,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
