import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tcad_agent.conformance.platform_evidence import (
    PlatformEvidenceError,
    ScientificPlatformEvidence,
    compare_platform_evidence,
    write_platform_evidence,
)


def evidence(platform: str, architecture: str) -> ScientificPlatformEvidence:
    return ScientificPlatformEvidence.model_validate(
        {
            "platform": platform,
            "architecture": architecture,
            "application_commit": "a" * 40,
            "python_version": "3.13.7",
            "devsim_version": "2.9.1",
            "devsim_source_commit": "43b41ca845184c47e22b72d144db7e7db8509377",
            "invariant_fixture_sha256": "b" * 64,
            "scientific_suite": "tests/integration/test_devsim_reference_benchmarks.py",
            "status": "passed",
        }
    )


def test_platform_evidence_round_trips_as_deterministic_json(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"

    write_platform_evidence(evidence("linux", "x64"), output)

    assert json.loads(output.read_text())["platform"] == "linux"
    assert output.read_text().endswith("\n")


def test_platform_evidence_script_bootstraps_the_source_tree() -> None:
    project_root = Path(__file__).parents[3]
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "scripts/scientific_platform_evidence.py", "--help"],
        cwd=project_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "write" in completed.stdout
    assert "compare" in completed.stdout


def test_platform_comparison_requires_every_target_and_identical_science_inputs() -> None:
    records = (
        evidence("linux", "x64"),
        evidence("win", "x64"),
        evidence("mac", "x64"),
        evidence("mac", "arm64"),
    )

    compare_platform_evidence(
        records,
        required_targets=(("linux", "x64"), ("win", "x64"), ("mac", "x64"), ("mac", "arm64")),
    )


def test_platform_comparison_refuses_missing_or_mismatched_evidence() -> None:
    records = (
        evidence("linux", "x64"),
        evidence("win", "x64").model_copy(update={"invariant_fixture_sha256": "c" * 64}),
    )

    with pytest.raises(PlatformEvidenceError, match="missing targets"):
        compare_platform_evidence(
            records,
            required_targets=(("linux", "x64"), ("win", "x64"), ("mac", "x64")),
        )

    with pytest.raises(PlatformEvidenceError, match="fixture hash"):
        compare_platform_evidence(
            records,
            required_targets=(("linux", "x64"), ("win", "x64")),
        )
