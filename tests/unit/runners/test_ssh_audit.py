import getpass
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from tcad_agent.runners.models import CompiledJob, RunBudget
from tcad_agent.runners.ssh import SSHAuditError, SSHSentaurusRunner


def make_runner(tmp_path: Path) -> SSHSentaurusRunner:
    """Create a runner with audit output directed to a temporary folder."""
    runner = object.__new__(SSHSentaurusRunner)
    runner._audit_events = []
    runner._audit_json_path = tmp_path / "ssh-audit.json"
    runner._audit_log_path = tmp_path / "ssh-audit.log"
    runner._run_id = "test-run-001"
    runner._started_at = "2026-10-13T00:00:00+00:00"
    runner._password = "test-secret-password"
    return runner


def read_audit(runner: SSHSentaurusRunner) -> dict:
    assert runner._audit_json_path is not None
    return json.loads(runner._audit_json_path.read_text(encoding="utf-8"))


def test_connection_rejects_unknown_server_keys(tmp_path, monkeypatch):
    import paramiko

    runner = make_runner(tmp_path)
    runner.host, runner.user, runner.port = "untrusted.invalid", "researcher", 22
    client = paramiko.SSHClient()
    monkeypatch.setattr(client, "_log", lambda *args: None)
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)

    def attempt_connection(**kwargs):
        key = paramiko.RSAKey.generate(2048)
        client._policy.missing_host_key(client, kwargs["hostname"], key)

    monkeypatch.setattr(client, "connect", attempt_connection)
    with pytest.raises(paramiko.SSHException, match="not found in known_hosts"):
        runner._connect()


def test_key_agent_auth_does_not_prompt_or_export_password(tmp_path, monkeypatch):
    import os

    import paramiko

    runner = make_runner(tmp_path)
    runner.host, runner.user, runner.port = "known.invalid", "researcher", 22
    runner._password = None
    monkeypatch.delenv("TCAD_HPSC_PASSWORD", raising=False)

    def hidden_prompt(*args, **kwargs):
        pytest.fail("Desktop SSH must not open a hidden password prompt")

    monkeypatch.setattr(getpass, "getpass", hidden_prompt)
    client = paramiko.SSHClient()
    monkeypatch.setattr(paramiko, "SSHClient", lambda: client)

    def key_agent_connection(**kwargs):
        assert kwargs.get("password") is None
        assert kwargs.get("allow_agent", True)
        assert kwargs.get("look_for_keys", True)

    monkeypatch.setattr(client, "connect", key_agent_connection)
    try:
        assert runner._connect() is client
        assert "TCAD_HPSC_PASSWORD" not in os.environ
    finally:
        client.close()


def test_record_writes_valid_json_and_readable_log(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)

    runner._record(
        "ssh.connect",
        "succeeded",
        host="test-host",
        port=22,
    )

    document = read_audit(runner)
    assert document["schema_version"] == 1
    assert document["run_id"] == "test-run-001"
    assert len(document["events"]) == 1

    event = document["events"][0]
    assert event["action"] == "ssh.connect"
    assert event["status"] == "succeeded"
    assert event["details"]["host"] == "test-host"
    assert event["details"]["port"] == 22
    assert event["timestamp"]

    log_text = runner._audit_log_path.read_text(encoding="utf-8")
    assert "[SUCCEEDED] ssh.connect" in log_text
    assert '"host": "test-host"' in log_text


def test_exec_records_actual_nonzero_exit_code(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)

    client = Mock()
    stdout = Mock()
    stderr = Mock()

    stdout.read.return_value = b""
    stdout.channel.recv_exit_status.return_value = 23
    stderr.read.return_value = b"Sentaurus failed"
    client.exec_command.return_value = (Mock(), stdout, stderr)

    exit_code, stdout_text, stderr_text = runner._exec(
        client,
        "sdevice device.cmd",
        "sentaurus.execute",
    )

    assert exit_code == 23
    assert stdout_text == ""
    assert stderr_text == "Sentaurus failed"

    events = read_audit(runner)["events"]
    result_event = next(
        event
        for event in events
        if event["action"] == "sentaurus.execute" and event["status"] == "failed"
    )

    assert result_event["details"]["exit_code"] == 23
    assert "Sentaurus failed" in result_event["details"]["stderr"]


def test_exec_records_and_reraises_ssh_exception(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)

    client = Mock()
    client.exec_command.side_effect = OSError("connection reset")

    with pytest.raises(OSError, match="connection reset"):
        runner._exec(client, "printf test", "remote.test")

    events = read_audit(runner)["events"]
    failure = next(
        event
        for event in events
        if event["action"] == "remote.test" and event["status"] == "failed"
    )

    assert "connection reset" in failure["details"]["error"]


def test_download_connection_error_is_recorded_as_failure(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)
    client = Mock()
    sftp = Mock()
    client.open_sftp.return_value = sftp
    sftp.get.side_effect = OSError("connection reset")

    with pytest.raises(OSError, match="connection reset"):
        runner._download_files(
            client,
            "/remote/run",
            tmp_path,
            ("device.tdr",),
        )

    events = read_audit(runner)["events"]
    failure = next(
        event
        for event in events
        if event["action"] == "sftp.download" and event["status"] == "failed"
    )

    assert failure["details"]["filename"] == "device.tdr"
    assert "connection reset" in failure["details"]["error"]
    sftp.close.assert_called_once()


def test_missing_download_is_marked_unavailable(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)
    client = Mock()
    sftp = Mock()
    client.open_sftp.return_value = sftp
    sftp.get.side_effect = FileNotFoundError("file not found")

    runner._download_files(
        client,
        "/remote/run",
        tmp_path,
        ("optional.plt",),
    )

    events = read_audit(runner)["events"]
    unavailable = next(
        event
        for event in events
        if event["action"] == "sftp.download" and event["status"] == "unavailable"
    )

    assert unavailable["details"]["filename"] == "optional.plt"


def test_password_is_redacted_from_json_and_text_log(
    tmp_path: Path,
) -> None:
    runner = make_runner(tmp_path)

    runner._record(
        "remote.test",
        "failed",
        error="Authentication failed for test-secret-password",
    )

    json_text = runner._audit_json_path.read_text(encoding="utf-8")
    log_text = runner._audit_log_path.read_text(encoding="utf-8")

    assert "test-secret-password" not in json_text
    assert "test-secret-password" not in log_text
    assert "[REDACTED]" in json_text
    assert "[REDACTED]" in log_text


def test_nested_password_values_are_redacted(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)

    runner._record(
        "remote.test",
        "failed",
        context={"message": "bad test-secret-password"},
        values=["safe", "test-secret-password"],
    )

    json_text = runner._audit_json_path.read_text(encoding="utf-8")
    log_text = runner._audit_log_path.read_text(encoding="utf-8")
    assert "test-secret-password" not in json_text
    assert "test-secret-password" not in log_text
    assert json_text.count("[REDACTED]") == 2


def test_audit_persistence_failure_is_not_silently_ignored(tmp_path: Path) -> None:
    runner = make_runner(tmp_path / "missing-parent")

    with pytest.raises(SSHAuditError, match="Could not persist SSH audit trail"):
        runner._record("ssh.connect", "started", host="test-host")


def test_audit_initialization_removes_previous_run_data(tmp_path: Path) -> None:
    runner = make_runner(tmp_path)
    runner._audit_json_path.write_text('{"events": ["stale"]}', encoding="utf-8")
    runner._audit_log_path.write_text("stale log line\n", encoding="utf-8")

    runner._initialize_audit(tmp_path)

    assert not runner._audit_json_path.exists()
    assert runner._audit_log_path.read_text(encoding="utf-8") == ""


def test_run_returns_per_run_audit_paths_and_records_remote_work(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "compiled"
    workspace.mkdir()
    entrypoint = workspace / "device.cmd"
    entrypoint.write_text("solve\n", encoding="utf-8")
    input_file = workspace / "device.cmd"
    stale_dir = workspace / "ssh-result"
    stale_dir.mkdir()
    (stale_dir / "ssh-audit.json").write_text('{"stale": true}', encoding="utf-8")
    (stale_dir / "ssh-audit.log").write_text("stale run\n", encoding="utf-8")

    class FakeSFTP:
        def lstat(self, path):
            raise FileNotFoundError(path)

        def put(self, local: str, remote: str) -> None:
            assert Path(local).is_file()
            assert remote.endswith(Path(local).name)

        def get(self, remote: str, local: str) -> None:
            name = Path(remote).name
            if name == "runner.stdout.log":
                Path(local).write_text("Sentaurus finished\n", encoding="utf-8")
            elif name == "runner.stderr.log":
                Path(local).write_text("", encoding="utf-8")
            elif name == "runner.return_code":
                Path(local).write_text("0\n", encoding="utf-8")
            else:
                raise FileNotFoundError(name)

        def close(self) -> None:
            return None

    class FakeClient:
        def open_sftp(self) -> FakeSFTP:
            return FakeSFTP()

        def close(self) -> None:
            return None

    runner = SSHSentaurusRunner(host="test-host", user="test-user", remote_root="/remote/runs")
    runner._connect = lambda: FakeClient()  # type: ignore[method-assign]
    runner._read_return_code = lambda client, directory: 0  # type: ignore[method-assign]

    def fake_exec(client, command: str, action: str) -> tuple[int, str, str]:
        runner._record(action, "started", command=command)
        if action == "remote.get_home":
            result = (0, "/home/test-user", "")
        else:
            result = (0, "", "")
        runner._record(action, "succeeded", exit_code=result[0])
        return result

    runner._exec = fake_exec  # type: ignore[method-assign]
    job = CompiledJob(
        backend="sentaurus",
        entrypoint=entrypoint,
        input_files=(input_file,),
        input_digest="a" * 64,
        runtime_digest="b" * 64,
        compiler_version="test",
    )

    result = runner.run(job, RunBudget(seconds=10))

    assert result.status == "malformed_result"
    assert "no native table export" in result.error
    assert result.audit_json_path is not None and result.audit_json_path.is_file()
    assert result.audit_log_path is not None and result.audit_log_path.is_file()
    document = json.loads(result.audit_json_path.read_text(encoding="utf-8"))
    actions = [event["action"] for event in document["events"]]
    assert "sftp.upload" in actions
    assert "sentaurus.execute" in actions
    assert actions[-1] == "run.finish"
    assert "stale run" not in result.audit_log_path.read_text(encoding="utf-8")


def test_failed_rerun_cannot_reuse_previous_return_code_or_results(tmp_path):
    entrypoint = tmp_path / "device.cmd"
    entrypoint.write_text("solve\n", encoding="utf-8")
    stale = tmp_path / "ssh-result"
    stale.mkdir()
    (stale / "runner.return_code").write_text("0\n", encoding="utf-8")
    (stale / "sentaurus-result.json").write_text('{"old": true}', encoding="utf-8")
    runner = SSHSentaurusRunner(host="host", user="user", remote_root="/remote/runs")
    runner._connect = lambda: Mock()
    runner._exec = lambda client, command, action: (
        (0, "/home/user", "")
        if action == "remote.get_home"
        else (23, "", "failed")
        if action == "sentaurus.execute"
        else (0, "", "")
    )
    runner._upload_files = lambda *args: None
    runner._download_files = lambda *args, **kwargs: None
    job = CompiledJob(
        backend="sentaurus",
        entrypoint=entrypoint,
        input_files=(entrypoint,),
        input_digest="a" * 64,
        runtime_digest="b" * 64,
        compiler_version="test",
    )

    result = runner.run(job, RunBudget(seconds=10))

    assert result.return_code == 23
    assert result.status == "execution_failed"
    assert result.result_path is None
    assert (stale / "sentaurus-result.json").read_text(encoding="utf-8") == '{"old": true}'


def test_missing_downloaded_logs_preserve_failed_run_diagnostics(tmp_path):
    entrypoint = tmp_path / "device.cmd"
    entrypoint.write_text("solve\n", encoding="utf-8")
    runner = SSHSentaurusRunner(host="host", user="user", remote_root="/remote/runs")
    runner._connect = lambda: Mock()
    runner._exec = lambda client, command, action: (
        (0, "/home/user", "")
        if action == "remote.get_home"
        else (23, "starting\n", "site command failed\n")
        if action == "sentaurus.execute"
        else (0, "", "")
    )
    runner._upload_files = lambda *args: None
    runner._download_files = lambda *args, **kwargs: None
    job = CompiledJob(
        backend="sentaurus",
        entrypoint=entrypoint,
        input_files=(entrypoint,),
        input_digest="a" * 64,
        runtime_digest="b" * 64,
        compiler_version="test",
    )

    result = runner.run(job, RunBudget(seconds=10))

    assert result.stdout_path.read_text(encoding="utf-8") == "starting\n"
    assert result.stderr_path.read_text(encoding="utf-8") == "site command failed\n"
    assert result.error == "site command failed\n"


def test_fractional_budget_is_not_rendered_as_disabled_timeout(tmp_path):
    import shlex

    entrypoint = tmp_path / "device.cmd"
    entrypoint.write_text("solve\n", encoding="utf-8")
    runner = SSHSentaurusRunner(host="host", user="user", remote_root="/remote/runs")
    runner._connect = lambda: Mock()

    def remote_exec(client, command, action):
        if action == "remote.get_home":
            return 0, "/home/user", ""
        if action == "sentaurus.execute":
            # The job is launched detached; its own command line is the quoted argument of sh -c.
            inner = shlex.split(shlex.split(command)[shlex.split(command).index("-c") + 1])
            # Whole seconds, rounded up: old coreutils reject fractions; 0 would disable it.
            assert inner[inner.index("timeout") + 1] == "1s"
        return 0, "", ""

    runner._exec = remote_exec
    runner._read_return_code = lambda client, directory: 0
    runner._upload_files = lambda *args: None
    runner._download_files = lambda *args, **kwargs: None
    job = CompiledJob(
        backend="sentaurus",
        entrypoint=entrypoint,
        input_files=(entrypoint,),
        input_digest="a" * 64,
        runtime_digest="b" * 64,
        compiler_version="test",
    )

    result = runner.run(job, RunBudget(seconds=0.25))
    # run() catches remote failures; a malformed timeout must not be swallowed.
    assert result.return_code == 0
    assert result.status == "malformed_result"
    assert "no native table export" in result.error


def test_connect_closes_client_if_success_event_cannot_be_persisted(
    tmp_path: Path, monkeypatch
) -> None:
    runner = SSHSentaurusRunner(host="test-host", user="test-user", remote_root="/remote/runs")
    runner._password = "test-secret-password"
    runner._run_id = "test-run-001"
    runner._started_at = runner._timestamp()
    runner._audit_json_path = tmp_path / "ssh-audit.json"
    runner._audit_log_path = tmp_path / "ssh-audit.log"
    client = Mock()
    monkeypatch.setattr("tcad_agent.runners.ssh.paramiko.SSHClient", lambda: client)
    runner._record = Mock(side_effect=[None, SSHAuditError("disk unavailable")])

    with pytest.raises(SSHAuditError, match="disk unavailable"):
        runner._connect()

    client.close.assert_called_once()
