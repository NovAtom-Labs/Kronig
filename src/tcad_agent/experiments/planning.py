"""Pure experiment planning, digest, and study-accounting helpers."""

import hashlib
import json
from typing import cast

from pydantic import JsonValue

from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.domain.models import DCStudy, ExperimentSpec


def build_plan(
    spec: ExperimentSpec,
    backend: str,
    warnings: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "backend": backend,
        "spec": cast(dict[str, JsonValue], spec.normalized()),
        "warnings": list(warnings),
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
    if not isinstance(spec.study, DCStudy):
        return 1
    return round(
        (spec.study.stop.to("V") - spec.study.start.to("V"))
        / spec.study.step.to("V")
    ) + 1
