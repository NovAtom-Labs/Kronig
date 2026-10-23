"""Source setup builds one authorized index and never rewrites shared source work."""

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tcad_agent.knowledge.models import SourceManifest
from tcad_agent.knowledge.retrieve import KnowledgeIndex

ROOT = Path(__file__).resolve().parents[2]


def script():
    spec = importlib.util.spec_from_file_location(
        "kronig_setup_knowledge", ROOT / "scripts/rebuild_knowledge_index.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def curated_checkout(root):
    guides = root / "knowledge-sources/curated"
    guides.mkdir(parents=True)
    guide = guides / "guide.md"
    guide.write_text("# Equilibrium\n\nCheck charge balance and contact current.\n")
    manifest = root / "knowledge-sources/manifests/sources.yaml"
    manifest.parent.mkdir()
    source = dict(
        id="curated",
        title="Guide",
        url="internal://guide",
        license="internal",
        access="restricted",
        trust="secondary",
        backend="portable",
        version="1",
        local_path="knowledge-sources/curated",
    )
    manifest.write_text(json.dumps({"sources": [source]}))
    return guide


def git(root, *arguments):
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def source_checkout(root):
    root.mkdir()
    git(root, "init")
    (root / "pydoc").mkdir()
    (root / "pydoc/manual.txt").write_text("Native solver convergence reference\n")
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Setup test",
        "-c",
        "user.email=setup@example.invalid",
        "commit",
        "-m",
        "reference",
    )
    return git(root, "rev-parse", "HEAD")


def test_index_setup_reuses_unchanged_index_and_rebuilds_changed_guidance(tmp_path):
    module = script()
    root = tmp_path / "checkout"
    guide = curated_checkout(root)
    index = root / "knowledge-sources/index/knowledge.sqlite3"
    module.rebuild_index(root, index, if_stale=True)
    assert KnowledgeIndex(index).search("charge balance")
    first = index.stat().st_mtime_ns
    module.rebuild_index(root, index, if_stale=True)
    assert index.stat().st_mtime_ns == first
    guide.write_text("# Transport\n\nThermionic reservoir verification.\n")
    module.rebuild_index(root, index, if_stale=True)
    assert KnowledgeIndex(index).search("thermionic reservoir")
    assert not KnowledgeIndex(index).search("charge balance")
    assert list(index.parent.iterdir()) == [index]


def test_public_source_fetch_is_pinned_reusable_and_non_destructive(tmp_path, monkeypatch):
    module = script()
    upstream = tmp_path / "upstream"
    revision = source_checkout(upstream)
    root = tmp_path / "checkout"
    root.mkdir()
    source = SourceManifest(
        id="reference",
        title="Reference",
        license="Apache-2.0",
        access="public",
        trust="primary",
        backend="devsim",
        version="1",
        reviewed=True,
        url=f"https://github.com/example/reference/tree/{revision}",
        local_path="devsim/reference/pydoc",
        repository_path="devsim/reference",
    )
    original_git = module._git
    fetches = []

    def local_fetch(directory, *arguments):
        if "fetch" in arguments:
            fetches.append(arguments)
            arguments = tuple(
                str(upstream) if str(arg).startswith("https://") else arg for arg in arguments
            )
        return original_git(directory, *arguments)

    monkeypatch.setattr(module, "_git", local_fetch)
    module.prepare_sources(root, (source,))
    target = tmp_path / "devsim/reference"
    assert git(target, "rev-parse", "HEAD") == revision
    module.prepare_sources(root, (source,))
    assert len(fetches) == 1
    generated = target / "native-output.dat"
    generated.write_text("researcher's generated output")
    module.prepare_sources(root, (source,))
    assert generated.read_text() == "researcher's generated output"
    (target / "pydoc/manual.txt").write_text("researcher's edited manual")
    with pytest.raises(ValueError, match="modified"):
        module.prepare_sources(root, (source,))
    assert (target / "pydoc/manual.txt").read_text() == "researcher's edited manual"


@pytest.mark.parametrize(
    "repository_path,local_path",
    [
        ("../escape", "../escape"),
        ("devsim/reference", "devsim/reference/../escape"),
    ],
)
def test_public_source_setup_refuses_escaping_paths_before_fetch(
    tmp_path, monkeypatch, repository_path, local_path
):
    module = script()
    source = SourceManifest(
        id="escape",
        title="Escape",
        license="Apache-2.0",
        access="public",
        trust="primary",
        backend="devsim",
        version="1",
        reviewed=True,
        url="https://github.com/example/reference/tree/" + "a" * 40,
        local_path=local_path,
        repository_path=repository_path,
    )
    monkeypatch.setattr(module, "_git", lambda *args: pytest.fail("must reject before Git access"))
    with pytest.raises(ValueError, match="escape"):
        module.prepare_sources(tmp_path, (source,))


def test_source_setup_refuses_ignored_indexable_content(tmp_path):
    module = script()
    root = tmp_path / "checkout"
    root.mkdir()
    target = tmp_path / "devsim/reference"
    target.parent.mkdir()
    revision = source_checkout(target)
    (target / ".git/info/exclude").write_text("scratch.txt\n")
    (target / "scratch.txt").write_text("unreviewed local instructions")
    source = SourceManifest(
        id="reference",
        title="Reference",
        license="Apache-2.0",
        access="public",
        trust="primary",
        backend="devsim",
        version="1",
        reviewed=True,
        url=f"https://github.com/example/reference/tree/{revision}",
        local_path="devsim/reference/pydoc",
        repository_path="devsim/reference",
    )
    with pytest.raises(ValueError, match="modified"):
        module.prepare_sources(root, (source,))


def test_index_connections_are_closed_before_atomic_replacement(tmp_path, monkeypatch):
    module = script()
    root = tmp_path / "checkout"
    guide = curated_checkout(root)
    index = root / "knowledge-sources/index/knowledge.sqlite3"
    connections = []
    connect = sqlite3.connect
    replace = Path.replace

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    def windows_replace(path, destination):
        for connection in connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                connection.execute("SELECT 1")
        return replace(path, destination)

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    monkeypatch.setattr(Path, "replace", windows_replace)
    module.rebuild_index(root, index, if_stale=True)
    guide.write_text("Changed scientific evidence\n")
    module.rebuild_index(root, index, if_stale=True)
