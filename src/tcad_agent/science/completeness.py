"""Deterministic scientific completeness evaluation for a composed experiment."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal, cast

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.science.models import (
    InputAuthority,
    InputResolutionRecord,
    ProvenanceReference,
    ResolutionStatus,
    ScientificCompletenessReport,
)
from tcad_agent.science.requirements import absolute_current_area_requirements


def _leaf_values(value: Any, prefix: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(value, dict):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            yield from _leaf_values(value[key], child)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _leaf_values(item, f"{prefix}.{index}")
        return
    yield prefix, value


def _authority(path: str) -> InputAuthority:
    if path.startswith(("solver.", "sign_convention.")):
        return InputAuthority.PLATFORM
    if path.startswith(("physics.equations", "physics.models")):
        return InputAuthority.EXPERT
    if path.startswith("metadata."):
        return InputAuthority.DERIVED
    return InputAuthority.RESEARCHER


class ScientificCompletenessEngine:
    """Evaluate portable dependencies without inspecting names or prompt text."""

    def evaluate(
        self,
        spec: ExperimentSpec,
        backend: str,
    ) -> ScientificCompletenessReport:
        normalized = spec.normalized()
        dependency_records = absolute_current_area_requirements(spec)
        dependency_paths = {record.path for record in dependency_records}
        records: list[InputResolutionRecord] = list(dependency_records)
        for path, value in _leaf_values(normalized):
            semantic_path = path
            if path.startswith("contacts."):
                segments = path.split(".")
                try:
                    index = int(segments[1])
                except (IndexError, ValueError):
                    index = -1
                if 0 <= index < len(spec.contacts):
                    semantic_path = ".".join(
                        ("contacts", spec.contacts[index].id, *segments[2:])
                    )
            if semantic_path in dependency_paths:
                continue
            authority = _authority(semantic_path)
            source_kind = cast(
                Literal["researcher", "platform", "derived", "evidence", "adapter"],
                {
                    InputAuthority.RESEARCHER: "researcher",
                    InputAuthority.PLATFORM: "platform",
                    InputAuthority.EXPERT: "evidence",
                    InputAuthority.DERIVED: "derived",
                    InputAuthority.ADAPTER: "adapter",
                    InputAuthority.UNKNOWN: "derived",
                }[authority],
            )
            records.append(
                InputResolutionRecord(
                    path=semantic_path,
                    quantity=semantic_path.replace(".", " "),
                    value=value,
                    authority=authority,
                    source=ProvenanceReference(
                        id=(
                            "confirmed-experiment-spec"
                            if authority is InputAuthority.RESEARCHER
                            else f"agent-kronig-{authority.value}"
                        ),
                        kind=source_kind,
                    ),
                    required_by=("experiment_execution",),
                    status=ResolutionStatus.RESOLVED,
                    rationale="The typed experiment contract contains an explicit resolved value.",
                )
            )
        return ScientificCompletenessReport(
            backend=backend,
            records=tuple(sorted(records, key=lambda item: item.path)),
        )
