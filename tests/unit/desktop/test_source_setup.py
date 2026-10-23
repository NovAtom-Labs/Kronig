from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def verifier():
    path = ROOT / "scripts/verify_source_setup.py"
    assert path.is_file(), "native setup must have an executable verifier"
    spec = importlib.util.spec_from_file_location("verify_source_setup", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_repeat_verification_detects_index_rebuild_or_dependency_reinstallation(tmp_path):
    module = verifier()
    cache = tmp_path / ".tcad-agent-dev/bootstrap.json"
    index = tmp_path / "knowledge-sources/index/knowledge.sqlite3"
    cache.parent.mkdir()
    index.parent.mkdir(parents=True)
    cache.write_text('{"stages":{"application":"a","devsim":"d","desktop":"e"}}')
    index.write_bytes(b"index evidence")
    original = module.setup_snapshot(tmp_path)
    module.require_reuse(original, module.setup_snapshot(tmp_path))
    index.write_bytes(b"changed evidence")
    with pytest.raises(ValueError, match="reuse"):
        module.require_reuse(original, module.setup_snapshot(tmp_path))


def test_repeat_setup_rejects_same_content_receipt_replacement(tmp_path):
    module = verifier()
    cache = tmp_path / ".tcad-agent-dev/bootstrap.json"
    index = tmp_path / "knowledge-sources/index/knowledge.sqlite3"
    cache.parent.mkdir()
    index.parent.mkdir(parents=True)
    cache.write_text('{"stages":{"application":"a","devsim":"d","desktop":"e"}}')
    index.write_bytes(b"unchanged index")
    before = module.setup_snapshot(tmp_path)
    replacement = cache.with_suffix(".tmp")
    replacement.write_bytes(cache.read_bytes())
    changed = cache.stat().st_mtime_ns + 1_000_000_000
    os.utime(replacement, ns=(changed, changed))
    replacement.replace(cache)
    with pytest.raises(ValueError, match="reuse"):
        module.require_reuse(before, module.setup_snapshot(tmp_path))


def test_failed_native_child_preserves_bounded_redacted_diagnostics(monkeypatch):
    module = verifier()

    def failure(command, **kwargs):
        return subprocess.CompletedProcess(
            command, 1, stdout="native math runtime is missing", stderr="api_key=private-value"
        )

    monkeypatch.setattr(module.subprocess, "run", failure)
    with pytest.raises(RuntimeError, match="native math runtime is missing") as caught:
        module.run_checked(["native-runtime"], cwd=ROOT, environment={})
    assert "private-value" not in str(caught.value)


def test_native_evidence_rejects_failed_science_despite_completed_execution(
    result_bundle_factory, tmp_path
):
    from tcad_agent.bundles.reader import BundleReader

    module = verifier()
    bundle = BundleReader().read(result_bundle_factory(tmp_path))
    failed = bundle.model_copy(
        update={"validation": bundle.validation.model_copy(update={"overall": "failed"})}
    )
    with pytest.raises(ValueError, match="validation"):
        module.scientific_summary(failed)


def test_native_smoke_strips_provider_and_user_runtime_configuration():
    module = verifier()
    actual = module.clean_environment(
        {
            "PATH": "tools",
            "SystemRoot": "Windows",
            "OPENAI_API_KEY": "private",
            "AWS_BEARER_TOKEN_BEDROCK": "private",
            "TCAD_WORKSPACE": "research",
            "AGENT_KRONIG_DATA_DIR": "settings",
            "PYTHONPATH": "other checkout",
        }
    )
    assert actual == {"PATH": "tools", "SystemRoot": "Windows"}


def test_source_setup_workflow_is_native_and_cannot_publish_releases():
    path = ROOT / ".github/workflows/source-setup.yml"
    assert path.is_file(), "source setup needs native Windows and Linux jobs"
    workflow = yaml.safe_load(path.read_text())
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request" in workflow["on"]
    assert workflow["on"]["push"]["branches"] == ["main"]
    jobs = workflow["jobs"]
    assert set(jobs) == {"setup"}
    rows = jobs["setup"]["strategy"]["matrix"]["include"]
    assert {row["runner"] for row in rows} == {"ubuntu-24.04", "windows-2025", "macos-15"}
    steps = jobs["setup"]["steps"]
    assert (
        next(step for step in steps if step.get("uses", "").startswith("actions/checkout"))["with"][
            "path"
        ]
        == "source checkout"
    )
    assert not any("secrets." in str(step) for step in steps)
