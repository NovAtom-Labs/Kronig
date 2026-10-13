from pathlib import Path

import pytest

from tcad_agent.ide.paths import WorkspacePathError, canonical_directory
from tcad_agent.ide.repository import RepositoryInspector


def test_inspector_accepts_a_non_git_directory(tmp_path: Path) -> None:
    root = tmp_path / "research"
    root.mkdir()
    (root / "experiment.yaml").write_text("name: reference\n")

    snapshot = RepositoryInspector().inspect(root)

    assert snapshot.root == root.resolve()
    assert snapshot.display_name == "research"
    assert snapshot.git.available is False
    assert [entry.name for entry in RepositoryInspector().entries(root)] == ["experiment.yaml"]


def test_entries_report_external_symlink_without_following_it(tmp_path: Path) -> None:
    root = tmp_path / "research"
    outside = tmp_path / "private"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("do not read")
    (root / "external").symlink_to(outside, target_is_directory=True)

    entries = RepositoryInspector().entries(root)

    assert [(item.name, item.kind) for item in entries] == [("external", "symlink")]
    with pytest.raises(WorkspacePathError, match="outside the workspace"):
        RepositoryInspector().entries(root, "external")


def test_canonical_directory_rejects_missing_files_and_plain_files(
    tmp_path: Path,
) -> None:
    regular_file = tmp_path / "file.txt"
    regular_file.write_text("content")

    with pytest.raises(WorkspacePathError, match="does not exist"):
        canonical_directory(tmp_path / "missing")
    with pytest.raises(WorkspacePathError, match="not a directory"):
        canonical_directory(regular_file)
