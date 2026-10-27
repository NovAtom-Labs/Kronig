"""Per-request backend selection so DEVSIM and Sentaurus are both always available.

The backend comes from the simulator a researcher names in the request. A request
that names none (or both) uses ``TCAD_BACKEND`` and then DEVSIM. Names are data in
each backend's capability manifest, not branches in code.
"""

from __future__ import annotations

import os
import re

from tcad_agent.capabilities.descriptors import CapabilityCatalog
from tcad_agent.capabilities.models import CapabilityManifest

KNOWN_BACKENDS = ("devsim", "sentaurus")
_SSH_SETTINGS = ("TCAD_HPSC_HOST", "TCAD_HPSC_USER", "TCAD_SENTAURUS_VERSION")


_preferred: str | None = None


def set_preferred_backend(name: str | None) -> None:
    """Simulator picked in the interface; it outranks ``TCAD_BACKEND`` until changed."""
    global _preferred
    if name is not None and name not in KNOWN_BACKENDS:
        raise ValueError(f"backend must be one of {', '.join(KNOWN_BACKENDS)}; got {name!r}")
    _preferred = name


def preferred_backend() -> str | None:
    return _preferred


def missing_settings(backend: str) -> tuple[str, ...]:
    """Environment settings a backend still needs before it can run on this machine."""
    if backend != "sentaurus":
        return ()
    missing = [name for name in _SSH_SETTINGS if not os.getenv(name, "").strip()]
    if os.getenv("TCAD_SENTAURUS_RUNNER", "").strip().lower() != "ssh":
        missing.insert(0, "TCAD_SENTAURUS_RUNNER")
    return tuple(missing)


def default_backend() -> str:
    """Backend used when a request does not name a simulator."""
    if _preferred is not None:
        return _preferred
    name = os.getenv("TCAD_BACKEND", "devsim").strip().lower() or "devsim"
    if name not in KNOWN_BACKENDS:
        raise ValueError(f"TCAD_BACKEND must be one of {', '.join(KNOWN_BACKENDS)}; got {name!r}")
    return name


def _names(backend: str) -> tuple[str, ...]:
    return (backend, *CapabilityManifest.from_backend(backend).aliases)


def resolve_backend(request: str | None) -> str:
    """Pick the backend a request explicitly names, else the configured default."""
    text = request or ""
    named = [
        backend
        for backend in KNOWN_BACKENDS
        if any(re.search(rf"(?i)\b{re.escape(name)}\b", text) for name in _names(backend))
    ]
    return named[0] if len(named) == 1 else default_backend()


def manifest_for(backend: str) -> CapabilityManifest:
    """Capability manifest with the backend's real execution state on this machine.

    Sentaurus is configured only when the SSH runner is selected and every setting it
    needs is present; otherwise the packaged state (unconfigured) is kept.
    """
    manifest = CapabilityManifest.from_backend(backend)
    if backend == "sentaurus":
        ready = os.getenv("TCAD_SENTAURUS_RUNNER", "").lower() == "ssh" and all(
            os.getenv(name, "").strip() for name in _SSH_SETTINGS
        )
        if ready:
            return manifest.model_copy(update={"execution_state": "configured"})
    return manifest


def catalog_for_request(request: str | None) -> CapabilityCatalog:
    return CapabilityCatalog.from_manifest(manifest_for(resolve_backend(request)))
