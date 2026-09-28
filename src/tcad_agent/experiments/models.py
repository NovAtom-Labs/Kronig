"""Typed experiment preparation records."""

from typing import Literal

from pydantic import Field, JsonValue

from tcad_agent.domain.models import ExperimentSpec, StrictModel


class PreparedExperiment(StrictModel):
    """Immutable simulator-neutral plan awaiting exact-digest approval."""

    schema_version: Literal["1.0"] = "1.0"
    backend: str
    spec: ExperimentSpec
    plan: dict[str, JsonValue]
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    warnings: tuple[str, ...] = ()
