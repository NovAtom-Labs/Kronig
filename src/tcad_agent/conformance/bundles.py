"""Integrity-checked conformance of canonical backend evidence bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tcad_agent.bundles.reader import BundleReader, VerifiedBundle
from tcad_agent.conformance.compare import compare_results, load_case_rules
from tcad_agent.conformance.models import ComparisonStatus


def _identity(bundle: VerifiedBundle, path: Path) -> dict[str, object]:
    manifest = bundle.manifest
    return {
        "path": str(path.resolve()),
        "run_id": manifest.run_id,
        "simulator_version": manifest.simulator_version,
        "compiler_version": manifest.compiler_version,
        "input_digest": manifest.input_digest,
        "runtime_digest": manifest.runtime_digest,
    }


def compare_verified_bundles(
    devsim_bundle: Path,
    sentaurus_bundle: Path,
    *,
    rules_path: Path,
    case_id: str,
) -> tuple[dict[str, object], ComparisonStatus]:
    """Verify bundle integrity, contract identity, backend roles, and metrics."""
    reader = BundleReader()
    devsim = reader.read(devsim_bundle)
    sentaurus = reader.read(sentaurus_bundle)
    if devsim.result.backend != "devsim":
        raise ValueError("the first bundle must contain DEVSIM canonical results")
    if sentaurus.result.backend != "sentaurus":
        raise ValueError("the second bundle must contain Sentaurus canonical results")
    devsim_contract = devsim.experiment.normalized()
    sentaurus_contract = sentaurus.experiment.normalized()
    if devsim_contract != sentaurus_contract:
        raise ValueError("conformance requires the same ExperimentSpec in both bundles")
    rules = load_case_rules(rules_path, case_id)
    report = compare_results(devsim.result, sentaurus.result, rules)
    contract_bytes = json.dumps(
        devsim_contract, sort_keys=True, separators=(",", ":")
    ).encode()
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "case_id": case_id,
        "experiment_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "inputs": {
            "devsim": _identity(devsim, devsim_bundle),
            "sentaurus": _identity(sentaurus, sentaurus_bundle),
        },
        **report.model_dump(mode="json"),
    }
    return payload, report.overall
