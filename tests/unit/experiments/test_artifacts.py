import json
from pathlib import Path

import pytest

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.experiments.artifacts import ExperimentPlanArtifactWriter, project_slug
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.validation.policy import validation_policy_digest


def test_recovery_plan_has_distinct_project_and_visible_numeric_diff(tmp_path, valid_spec):
    from tcad_agent.recovery.models import FailureKind, FailureRecord, RecoveryAction
    from tcad_agent.recovery.proposals import RecoveryProposalService

    engine = ExperimentEngine()
    original = ExperimentPlanArtifactWriter(tmp_path).write(engine.prepare(valid_spec, "devsim"))
    content = original.markdown_path.read_text()
    proposal = RecoveryProposalService().propose(
        valid_spec,
        action=RecoveryAction.REFINE_MESH,
        failure=FailureRecord(kind=FailureKind.CONSERVATION, evidence="Current residual"),
        original_bundle_id="original-run",
        validation_limits={"current_atol": 1e-6},
        validation_policy_digest=validation_policy_digest(),
    )
    recovered = ExperimentPlanArtifactWriter(tmp_path).write(
        engine.prepare(proposal.candidate_spec, "devsim", recovery_proposal=proposal)
    )

    assert recovered.project_root != original.project_root
    assert original.markdown_path.read_text() == content
    assert "original-run" in recovered.markdown_path.read_text()
    assert "mesh_spacing" in recovered.markdown_path.read_text()
    assert "1e-06" in recovered.markdown_path.read_text()


def test_plan_artifacts_are_byte_stable_and_include_input_ledger(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
) -> None:
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")
    writer = ExperimentPlanArtifactWriter(tmp_path)

    first = writer.write(prepared)
    first_markdown = first.markdown_path.read_bytes()
    first_json = first.json_path.read_bytes()
    second = writer.write(prepared)

    assert second == first
    assert first.markdown_path.read_bytes() == first_markdown
    assert first.json_path.read_bytes() == first_json
    payload = json.loads(first.json_path.read_text())
    assert payload["plan_digest"] == prepared.plan_digest
    assert payload["prepared"] == prepared.model_dump(mode="json")
    assert payload["scientific_input_ledger"]
    assert "Scientific input ledger" in first.markdown_path.read_text()
    assert "maximum retries" not in first.markdown_path.read_text().lower()
    assert "magnitude_si" not in first.markdown_path.read_text()
    assert "## Doping and charge profiles" in first.markdown_path.read_text()


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Compensated Silicon Study", "compensated-silicon-study"),
        ("../outside", "outside"),
        ("", "experiment"),
    ],
)
def test_project_slug_is_readable_and_cannot_traverse(name: str, expected: str) -> None:
    assert project_slug(name) == expected


def test_plan_writer_rejects_symlink_escape(
    tmp_path: Path,
    valid_spec: ExperimentSpec,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "workspace" / "experiments").parent.mkdir()
    (tmp_path / "workspace" / "experiments").symlink_to(outside, target_is_directory=True)
    prepared = ExperimentEngine().prepare(valid_spec, "devsim")

    with pytest.raises(ValueError, match="symlink"):
        ExperimentPlanArtifactWriter(tmp_path / "workspace").write(prepared)
