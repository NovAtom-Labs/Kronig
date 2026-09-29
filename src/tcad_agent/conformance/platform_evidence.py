"""Portable CI evidence for the pinned scientific reference suite."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field

from tcad_agent.domain.models import StrictModel


class PlatformEvidenceError(ValueError):
    """Cross-platform scientific evidence is incomplete or inconsistent."""


class ScientificPlatformEvidence(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    platform: Literal["linux", "win", "mac"]
    architecture: Literal["x64", "arm64"]
    application_commit: str = Field(min_length=40, max_length=64)
    python_version: str = Field(min_length=1)
    devsim_version: str = Field(min_length=1)
    devsim_source_commit: str = Field(min_length=40, max_length=64)
    invariant_fixture_sha256: str = Field(min_length=64, max_length=64)
    scientific_suite: str = Field(min_length=1)
    status: Literal["passed"]


def write_platform_evidence(
    evidence: ScientificPlatformEvidence, output: Path
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    )


def load_platform_evidence(path: Path) -> ScientificPlatformEvidence:
    return ScientificPlatformEvidence.model_validate_json(path.read_text())


def compare_platform_evidence(
    records: Sequence[ScientificPlatformEvidence],
    *,
    required_targets: Sequence[tuple[str, str]],
) -> None:
    actual = {(record.platform, record.architecture) for record in records}
    required = set(required_targets)
    missing = sorted(required - actual)
    unexpected = sorted(actual - required)
    if missing:
        raise PlatformEvidenceError(f"missing targets: {missing}")
    if unexpected:
        raise PlatformEvidenceError(f"unexpected targets: {unexpected}")
    if len(actual) != len(records):
        raise PlatformEvidenceError("duplicate platform evidence target")

    def require_one(label: str, values: set[str]) -> None:
        if len(values) != 1:
            raise PlatformEvidenceError(f"{label} differs across platform evidence")

    require_one("application commit", {record.application_commit for record in records})
    require_one("DEVSIM version", {record.devsim_version for record in records})
    require_one(
        "DEVSIM source commit", {record.devsim_source_commit for record in records}
    )
    require_one(
        "invariant fixture hash",
        {record.invariant_fixture_sha256 for record in records},
    )
    require_one("scientific suite", {record.scientific_suite for record in records})
