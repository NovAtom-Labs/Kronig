import json

import pytest

from tcad_agent.ide.result_catalog import SavedResultCatalog
from tcad_agent.ide.results import WorkspaceResultError
from tcad_agent.runtime.paths import RuntimePaths


def test_saved_results_survive_without_chat_records(tmp_path, monkeypatch, result_bundle_factory):
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    result_bundle_factory(RuntimePaths.from_workspace(workspace).bundle_root)
    # In-progress staging is always present in real managed bundle storage.
    staging = RuntimePaths.from_workspace(workspace).bundle_root / ".work" / "unfinished-run"
    staging.mkdir(parents=True)
    project = workspace / "experiments" / "reviewed-study"
    project.mkdir(parents=True)
    (project / "project.json").write_text(json.dumps({"run_id": "run-0001"}))
    catalog = SavedResultCatalog()

    listing = catalog.list(workspace)

    assert len(listing.entries) == 1
    assert listing.entries[0].bundle_run_id == "run-0001"
    assert listing.entries[0].project_path == "experiments/reviewed-study"
    assert catalog.read(workspace, "run-0001").result.fields["potential"].values[1] == 0.41
    assert listing.rejected_count == 0
    assert listing.entries[0].reason
    assert listing.entries[0].output_state in {"passed", "failed", "not_applicable"}


def test_saved_catalog_excludes_tampered_evidence(tmp_path, monkeypatch, result_bundle_factory):
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    bundle = result_bundle_factory(RuntimePaths.from_workspace(workspace).bundle_root)
    (bundle / "results" / "canonical.json").write_text("{}")

    listing = SavedResultCatalog().list(workspace)

    assert listing.entries == ()
    assert listing.rejected_count == 1
    with pytest.raises(WorkspaceResultError):
        SavedResultCatalog().read(workspace, "run-0001")


@pytest.mark.parametrize("identifier", ["../run-0001", "/run-0001", "run-0001/results"])
def test_catalog_rejects_path_instead_of_bundle_identity(tmp_path, identifier):
    with pytest.raises(WorkspaceResultError, match="identity"):
        SavedResultCatalog().read(tmp_path, identifier)


def test_saved_catalog_cannot_cross_workspaces(tmp_path, monkeypatch, result_bundle_factory):
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    result_bundle_factory(RuntimePaths.from_workspace(first).bundle_root)

    assert SavedResultCatalog().list(second).entries == ()
    with pytest.raises(WorkspaceResultError):
        SavedResultCatalog().read(second, "run-0001")


def test_catalog_refuses_symlinked_managed_root(tmp_path, monkeypatch, result_bundle_factory):
    monkeypatch.setenv("AGENT_KRONIG_DATA_DIR", str(tmp_path / "data"))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside"
    result_bundle_factory(outside)
    managed = RuntimePaths.from_workspace(workspace).bundle_root
    managed.parent.mkdir(parents=True)
    managed.symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspaceResultError, match="directory"):
        SavedResultCatalog().list(workspace)
