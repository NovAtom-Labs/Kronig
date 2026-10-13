from pathlib import Path

import pytest
import yaml

from tcad_agent.agent.tools import TcadDomainAction, TcadDomainExecutor, build_tools

ROOT = Path(__file__).parents[3]


def valid_spec_payload() -> dict:
    return yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())


def test_run_tool_requires_validated_plan(tmp_path: Path) -> None:
    tools = build_tools(tmp_path)
    response = tools.run_experiment({"spec_path": "spec.yaml", "backend": "devsim"})
    assert response.status == "refused"
    assert response.code == "approval_required"


def test_sentaurus_compiles_without_configured_remote(tmp_path: Path) -> None:
    response = build_tools(tmp_path).compile_experiment(
        valid_spec_payload(), backend="sentaurus"
    )
    assert response.status == "ok"
    assert response.code == "compiled"
    assert response.data["job"]["backend"] == "sentaurus"


def test_tcad_executor_returns_llm_visible_refusal_for_missing_payload(
    tmp_path: Path,
) -> None:
    observation = TcadDomainExecutor(tmp_path)(
        TcadDomainAction(operation="validate_spec")
    )

    assert observation.status == "refused"
    assert observation.code == "invalid_spec"
    assert observation.content
    assert '"code": "invalid_spec"' in observation.text


def test_llm_can_read_ssh_audit_from_experiment_bundle(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))
    bundle = tmp_path / "bundles" / "run-123" / "logs"
    bundle.mkdir(parents=True)
    (bundle / "ssh-audit.json").write_text(
        '{"schema_version": 1, "run_id": "ssh-run", "events": '
        '[{"action": "ssh.connect", "status": "succeeded"}]}',
        encoding="utf-8",
    )
    (bundle / "ssh-audit.log").write_text(
        "[SUCCEEDED] ssh.connect\n", encoding="utf-8"
    )

    response = build_tools(tmp_path).read_ssh_audit("run-123")

    assert response.status == "ok"
    assert response.code == "ssh_audit_read"
    audit = response.data["audit"]
    assert isinstance(audit, dict)
    assert audit["events"][0]["action"] == "ssh.connect"
    assert "ssh.connect" in response.data["text_log"]


def test_read_ssh_audit_rejects_path_traversal(tmp_path: Path) -> None:
    response = build_tools(tmp_path).read_ssh_audit("../outside")

    assert response.status == "refused"
    assert response.code == "invalid_run_id"


def test_read_ssh_audit_reports_missing_bundle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))

    response = build_tools(tmp_path).read_ssh_audit("missing-run")

    assert response.status == "refused"
    assert response.code == "ssh_audit_not_found"


def test_llm_domain_tool_dispatches_ssh_audit_read(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))
    audit_dir = tmp_path / "bundles" / "run-456" / "logs"
    audit_dir.mkdir(parents=True)
    (audit_dir / "ssh-audit.json").write_text(
        '{"schema_version": 1, "run_id": "ssh-run", "events": []}',
        encoding="utf-8",
    )
    (audit_dir / "ssh-audit.log").write_text("audit available\n", encoding="utf-8")

    observation = TcadDomainExecutor(tmp_path)(
        TcadDomainAction(
            operation="read_ssh_audit",
            payload={"run_id": "run-456"},
        )
    )

    assert observation.status == "ok"
    assert observation.code == "ssh_audit_read"
    assert '"events": []' in observation.text


def test_llm_can_discover_recent_ssh_audit_bundles(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path))
    audit_dir = tmp_path / "bundles" / "run-discover" / "logs"
    audit_dir.mkdir(parents=True)
    (audit_dir / "ssh-audit.json").write_text(
        '{"schema_version": 1, "run_id": "ssh-run", "updated_at": '
        '"2026-10-13T00:00:00+00:00", "events": [{"action": "ssh.connect"}]}',
        encoding="utf-8",
    )

    response = build_tools(tmp_path).read_ssh_audit()

    assert response.status == "ok"
    assert response.code == "ssh_audit_index"
    assert response.data["runs"][0]["bundle_run_id"] == "run-discover"
