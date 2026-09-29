"""Typed capability manifests and refusal decisions."""

from enum import StrEnum
from importlib.resources import files
from typing import Literal, Self

import yaml
from pydantic import Field, model_validator

from tcad_agent.domain.models import StrictModel


class CapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    NEEDS_INPUT = "needs_input"
    BACKEND_UNSUPPORTED = "backend_unsupported"
    PLATFORM_UNSUPPORTED = "platform_unsupported"


class CapabilityIssue(StrictModel):
    path: str
    code: str
    message: str
    requested: str | int | None = None
    supported: tuple[str | int | float, ...] = ()


class CapabilityDecision(StrictModel):
    status: CapabilityStatus
    backend: str
    issues: tuple[CapabilityIssue, ...] = ()


class CapabilityManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: str
    adapter_version: str = "0.1.0"
    execution_state: Literal["configured", "unconfigured"] = "configured"
    dimensions: tuple[int, ...]
    equations: tuple[str, ...]
    models: tuple[str, ...] = ()
    materials: tuple[str, ...] = ("silicon",)
    profiles: tuple[str, ...] = ("constant",)
    interfaces: tuple[str, ...] = ("continuity",)
    contacts: tuple[str, ...] = ("ohmic",)
    studies: tuple[str, ...] = ("equilibrium", "dc")
    observables: tuple[str, ...] = ()
    limits: dict[str, int | float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_unique_values(self) -> Self:
        for field_name in (
            "dimensions",
            "equations",
            "models",
            "materials",
            "profiles",
            "interfaces",
            "contacts",
            "studies",
            "observables",
        ):
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} capability values must be unique")
        return self

    @classmethod
    def from_backend(cls, backend: str) -> "CapabilityManifest":
        if backend not in {"devsim", "sentaurus"}:
            raise ValueError(f"unknown backend: {backend}")
        resource = files("tcad_agent.adapters").joinpath(backend, "manifest.yaml")
        return cls.model_validate(yaml.safe_load(resource.read_text()))
