import json
from pathlib import Path

import pytest

from tcad_agent.ide.results import WorkspaceResultError, WorkspaceResultReader


def test_reader_returns_typed_verified_canonical_bundle(
    tmp_path: Path, result_bundle_factory
) -> None:
    bundle = result_bundle_factory(tmp_path)

    view = WorkspaceResultReader().read(
        tmp_path, "run-0001/results/canonical.json"
    )

    assert view.bundle_path == "run-0001"
    assert view.canonical_path == "run-0001/results/canonical.json"
    assert view.manifest.run_id == "run-0001"
    assert view.result.backend == "devsim"
    assert view.result.fields["potential"].values == (0.0, 0.41, 0.82)
    assert view.experiment.name
    assert view.validation.checks
    assert bundle.is_dir()


def test_reader_rejects_noncanonical_file_path(
    tmp_path: Path, result_bundle_factory
) -> None:
    result_bundle_factory(tmp_path)

    with pytest.raises(WorkspaceResultError, match=r"results/canonical\.json"):
        WorkspaceResultReader().read(tmp_path, "run-0001/manifest.json")


def test_reader_rejects_tampered_canonical_artifact(
    tmp_path: Path, result_bundle_factory
) -> None:
    bundle = result_bundle_factory(tmp_path)
    target = bundle / "results" / "canonical.json"
    target.write_text(target.read_text().replace("0.41", "0.42", 1))

    with pytest.raises(WorkspaceResultError, match="hash"):
        WorkspaceResultReader().read(
            tmp_path, "run-0001/results/canonical.json"
        )


def test_reader_rejects_manifest_and_result_backend_mismatch(
    tmp_path: Path, result_bundle_factory
) -> None:
    result_bundle_factory(
        tmp_path,
        result_backend="sentaurus",
        manifest_backend="devsim",
    )

    with pytest.raises(WorkspaceResultError, match="backend"):
        WorkspaceResultReader().read(
            tmp_path, "run-0001/results/canonical.json"
        )


def test_reader_rejects_missing_manifested_artifact(
    tmp_path: Path, result_bundle_factory
) -> None:
    bundle = result_bundle_factory(tmp_path)
    (bundle / "validation" / "report.json").unlink()

    with pytest.raises(WorkspaceResultError, match="unavailable"):
        WorkspaceResultReader().read(
            tmp_path, "run-0001/results/canonical.json"
        )


def test_reader_rejects_path_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-result"
    (outside / "results").mkdir(parents=True, exist_ok=True)
    (outside / "results" / "canonical.json").write_text("{}\n")

    with pytest.raises(ValueError, match="outside"):
        WorkspaceResultReader().read(
            tmp_path, "../outside-result/results/canonical.json"
        )


def test_reader_opens_managed_bundle_without_workspace_projection(
    tmp_path: Path, result_bundle_factory
) -> None:
    bundle = result_bundle_factory(tmp_path / "managed")

    view = WorkspaceResultReader().read_bundle(bundle)

    assert view.bundle_path == "run-0001"
    assert view.canonical_path == "results/canonical.json"


def test_reader_allows_completed_execution_that_needs_validation_review(
    tmp_path: Path, result_bundle_factory
) -> None:
    bundle = result_bundle_factory(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.update(
        {
            "state": "failed",
            "execution_state": "completed",
            "validation_state": "needs_review",
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    view = WorkspaceResultReader().read_bundle(bundle)

    assert view.manifest.execution_state == "completed"
    assert view.manifest.validation_state == "needs_review"
