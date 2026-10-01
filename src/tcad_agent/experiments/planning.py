"""Pure experiment planning, digest, and study-accounting helpers."""

import hashlib
import json
from typing import cast

from pydantic import JsonValue

from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.studies import expand_study_points
from tcad_agent.science.models import ScientificCompletenessReport


def build_plan(
    spec: ExperimentSpec,
    backend: str,
    warnings: tuple[str, ...],
    completeness: ScientificCompletenessReport,
) -> dict[str, JsonValue]:
    return {
        "backend": backend,
        "spec": cast(dict[str, JsonValue], spec.normalized()),
        "warnings": list(warnings),
        "scientific_input_ledger": [
            record.model_dump(mode="json", exclude_none=True)
            for record in completeness.records
        ],
        "portable": True,
    }


def digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def digest_plan(plan: dict[str, JsonValue]) -> str:
    return digest_json(plan)


def digest_capability(manifest: CapabilityManifest) -> str:
    return digest_json(manifest.model_dump(mode="json"))


def expected_bias_points(spec: ExperimentSpec) -> int:
    expanded = expand_study_points(spec.study)
    return len(expanded) if expanded else 1
