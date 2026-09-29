"""Integrity-checked reader for immutable experiment bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tcad_agent.bundles.models import BundleManifest
from tcad_agent.domain.models import ExperimentSpec, StrictModel
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationReport


class BundleIntegrityError(ValueError):
    """A bundle cannot be trusted or decoded."""


class VerifiedBundle(StrictModel):
    root: Path
    manifest: BundleManifest
    experiment: ExperimentSpec
    result: CanonicalResult
    validation: ValidationReport


class BundleReader:
    json_limit = 16 * 1024 * 1024
    required = (
        "experiment.json",
        "results/canonical.json",
        "validation/report.json",
    )

    def read(self, root: Path) -> VerifiedBundle:
        try:
            canonical_root = root.resolve(strict=True)
            manifest = BundleManifest.model_validate(
                self._read_json(canonical_root / "manifest.json")
            )
        except (OSError, ValidationError) as exc:
            raise BundleIntegrityError("bundle manifest is unavailable or malformed") from exc
        for required in self.required:
            if required not in manifest.artifacts:
                raise BundleIntegrityError(f"bundle manifest omits {required}")
        for relative, record in manifest.artifacts.items():
            target = (canonical_root / relative).resolve(strict=True)
            if not target.is_relative_to(canonical_root):
                raise BundleIntegrityError("bundle artifact resolves outside the bundle")
            raw = target.read_bytes()
            if len(raw) != record.bytes:
                raise BundleIntegrityError(f"bundle artifact size mismatch: {relative}")
            if hashlib.sha256(raw).hexdigest() != record.sha256:
                raise BundleIntegrityError(f"bundle artifact hash mismatch: {relative}")
        try:
            experiment = ExperimentSpec.model_validate(
                self._read_json(canonical_root / "experiment.json")
            )
            result = CanonicalResult.model_validate(
                self._read_json(canonical_root / "results" / "canonical.json")
            )
            validation = ValidationReport.model_validate(
                self._read_json(canonical_root / "validation" / "report.json")
            )
        except ValidationError as exc:
            raise BundleIntegrityError("bundle content is malformed") from exc
        if result.backend != manifest.backend:
            raise BundleIntegrityError("result backend does not match bundle manifest")
        return VerifiedBundle(
            root=canonical_root,
            manifest=manifest,
            experiment=experiment,
            result=result,
            validation=validation,
        )

    def _read_json(self, path: Path) -> dict[str, Any]:
        if path.stat().st_size > self.json_limit:
            raise BundleIntegrityError("bundle JSON exceeds the supported size")
        try:
            payload = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BundleIntegrityError("bundle JSON is unreadable") from exc
        if not isinstance(payload, dict):
            raise BundleIntegrityError("bundle JSON must contain an object")
        return payload
