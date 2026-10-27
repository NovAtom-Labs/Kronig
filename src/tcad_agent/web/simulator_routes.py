"""Simulator choice and the Sentaurus connection check for the researcher interface."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from tcad_agent.capabilities.active import (
    KNOWN_BACKENDS,
    default_backend,
    manifest_for,
    missing_settings,
    preferred_backend,
    set_preferred_backend,
)
from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.runners.ssh_check import run_checks


class SetBackendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["devsim", "sentaurus"] | None


class SentaurusCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trust_host: bool = False
    deep: bool = False


def _describe(backend: str) -> dict[str, object]:
    manifest = manifest_for(backend)
    missing = missing_settings(backend)
    return {
        "id": backend,
        "label": {"devsim": "DEVSIM (local)", "sentaurus": "Sentaurus (remote HPC)"}[backend],
        "ready": manifest.execution_state == "configured" or backend == "devsim",
        "missing_settings": list(missing),
        "aliases": list(CapabilityManifest.from_backend(backend).aliases),
    }


def build_simulator_router() -> APIRouter:
    router = APIRouter(prefix="/api/simulators")

    def state() -> dict[str, object]:
        return {
            "default": default_backend(),
            "selected": preferred_backend(),
            "backends": [_describe(name) for name in KNOWN_BACKENDS],
        }

    @router.get("")
    def simulators() -> dict[str, object]:
        return state()

    @router.put("/default")
    def choose_default(payload: SetBackendRequest) -> dict[str, object]:
        set_preferred_backend(payload.backend)
        return state()

    @router.post("/sentaurus/check")
    def check_sentaurus(payload: SentaurusCheckRequest) -> dict[str, object]:
        results = run_checks(trust_host=payload.trust_host, deep=payload.deep)
        return {
            "ok": bool(results) and all(result.ok for result in results),
            "checks": [
                {"name": r.name, "ok": r.ok, "detail": r.detail, "fix": r.fix} for r in results
            ],
        }

    return router
