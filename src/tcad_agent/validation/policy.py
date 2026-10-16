"""Fingerprint the complete local scientific acceptance implementation."""

import hashlib
import json
import marshal
from importlib import import_module
from pathlib import Path
from types import CodeType

_POLICY_MODULES = (
    "tcad_agent.validation",
    "tcad_agent.validation.assessment",
    "tcad_agent.validation.analytical",
    "tcad_agent.validation.convergence",
    "tcad_agent.validation.datasets",
    "tcad_agent.validation.engine",
    "tcad_agent.validation.mesh",
    "tcad_agent.validation.models",
    "tcad_agent.validation.physics",
    "tcad_agent.validation.statistics",
    "tcad_agent.validation.charge",
    "tcad_agent.validation.refinement",
    "tcad_agent.validation.policy",
    "tcad_agent.domain.models",
    "tcad_agent.domain.presentation",
    "tcad_agent.domain.profiles",
    "tcad_agent.domain.studies",
    "tcad_agent.domain.units",
    "tcad_agent.results.datasets",
    "tcad_agent.results.models",
    "tcad_agent.results.presentation",
)


def _portable_code(code: CodeType) -> CodeType:
    """Remove installation paths from all nested code objects before hashing."""
    return code.replace(
        co_filename="<validation-policy>",
        co_consts=tuple(
            _portable_code(value) if isinstance(value, CodeType) else value
            for value in code.co_consts
        ),
    )


def _module_fingerprint(module_name: str, source_path: Path) -> tuple[str, str]:
    try:
        content = source_path.read_bytes()
        kind = "source"
    except OSError:
        # PyInstaller normally bundles our source data, but its frozen loader
        # also exposes the actual code object when source files are unavailable.
        try:
            module = import_module(module_name)
            loader = module.__spec__.loader if module.__spec__ is not None else None
            get_code = getattr(loader, "get_code", None)
            code = get_code(module_name) if callable(get_code) else None
        except (ImportError, OSError) as exc:
            raise ValueError(f"validation policy code is unavailable: {module_name}") from exc
        if not isinstance(code, CodeType):
            raise ValueError(f"validation policy code is unavailable: {module_name}") from None
        content = marshal.dumps(_portable_code(code))
        kind = "module_code"
    return kind, hashlib.sha256(content).hexdigest()


def validation_policy_digest() -> str:
    """Hash local criteria and referenced numeric semantics without caching.

    Source changes, including fixed Poisson/rate/continuity/capacitance limits,
    invalidate recovery even when configurable engine tolerances are unchanged.
    Frozen-loader code is used when source assets are unavailable. Missing
    source and code fail closed. No historical policy is inferred. A switch
    between source and code representations changes the policy identity.
    """
    package_root = Path(__file__).resolve().parent.parent
    manifest = {}
    for module_name in _POLICY_MODULES:
        relative = module_name.removeprefix("tcad_agent.").replace(".", "/")
        path = package_root / (
            "validation/__init__.py" if relative == "validation" else f"{relative}.py"
        )
        manifest[module_name] = _module_fingerprint(module_name, path)
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
