from pathlib import Path

from tcad_agent.runtime.paths import RuntimePaths


def test_runtime_bundles_live_under_application_data(tmp_path: Path) -> None:
    repository = tmp_path / "research" / "selected-project"
    repository.mkdir(parents=True)
    paths = RuntimePaths.from_roots(data_root=tmp_path / "app-data", workspace=repository)

    assert paths.bundle_root.is_relative_to((tmp_path / "app-data").resolve())
    assert not paths.bundle_root.is_relative_to(repository.resolve())
    assert paths.bundle_root.name == "bundles"


def test_workspace_identity_is_stable_and_path_specific(tmp_path: Path) -> None:
    first = RuntimePaths.from_roots(
        data_root=tmp_path / "app-data", workspace=tmp_path / "project-a"
    )
    again = RuntimePaths.from_roots(
        data_root=tmp_path / "app-data", workspace=tmp_path / "project-a"
    )
    other = RuntimePaths.from_roots(
        data_root=tmp_path / "app-data", workspace=tmp_path / "project-b"
    )

    assert first.workspace_key == again.workspace_key
    assert first.workspace_key != other.workspace_key
