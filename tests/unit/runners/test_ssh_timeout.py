"""The remote command must stay valid on old coreutils."""

import re

from tcad_agent.runners.ssh import SSHSentaurusRunner


def test_remote_timeout_is_always_whole_seconds() -> None:
    # A later run in one experiment gets the fractional rest of the budget.
    command = SSHSentaurusRunner.remote_command("/work/run", "sh run.sh", 2523.8)
    assert "timeout 2524s " in command
    assert not re.search(r"timeout \d+\.\d", command)


def test_remote_command_records_the_exit_status_of_the_program() -> None:
    command = SSHSentaurusRunner.remote_command("/work/my run", "sh run.sh", 60)
    assert command.startswith(
        "cd '/work/my run' && KRONIG_BUDGET_SECONDS=60 timeout 60s sh run.sh "
    )
    assert "runner.return_code" in command and command.endswith('exit "$rc"')

def test_only_transient_connection_errors_are_retried() -> None:
    import paramiko

    from tcad_agent.runners.ssh import _is_transient_connect_error

    assert _is_transient_connect_error(TimeoutError("timed out"))
    assert _is_transient_connect_error(ConnectionResetError())
    assert _is_transient_connect_error(paramiko.SSHException("Error reading SSH protocol banner"))
    assert not _is_transient_connect_error(paramiko.AuthenticationException("bad password"))
    assert _is_transient_connect_error(paramiko.SSHException("No existing session"))
    assert not _is_transient_connect_error(
        paramiko.SSHException("Server '10.0.0.5' not found in known_hosts")
    )


def test_a_dropped_connection_does_not_lose_a_running_job(tmp_path, monkeypatch) -> None:
    from unittest.mock import Mock

    import tcad_agent.runners.ssh as ssh

    monkeypatch.setattr(ssh, "POLL_SECONDS", 0)
    runner = SSHSentaurusRunner(host="h", user="u", remote_root="/r")
    first, second = Mock(name="first"), Mock(name="second")
    launches = []
    def record_launch(client, command, action):
        launches.append(command)
        return 0, "launched", ""

    runner._exec = record_launch
    answers = iter([OSError("connection reset"), None, 0])

    def read(client, directory):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    runner._read_return_code = read  # type: ignore[method-assign]
    runner._reconnect = lambda client, deadline: second  # type: ignore[method-assign]
    client, code, _out, _err = runner._execute_resilient(first, "/r/run", "sh run.sh", 60)
    assert code == 0 and client is second
    assert len(launches) == 1 and "nohup" in launches[0] and "sh run.sh" in launches[0]


def test_a_job_that_never_reports_is_treated_as_timed_out(monkeypatch) -> None:
    from unittest.mock import Mock

    import tcad_agent.runners.ssh as ssh

    monkeypatch.setattr(ssh, "POLL_SECONDS", 0)
    monkeypatch.setattr(ssh, "RESULT_GRACE_SECONDS", -1)
    runner = SSHSentaurusRunner(host="h", user="u", remote_root="/r")
    runner._exec = lambda client, command, action: (0, "launched", "")
    runner._read_return_code = lambda client, directory: None  # type: ignore[method-assign]
    _client, code, _out, _err = runner._execute_resilient(Mock(), "/r/run", "sh run.sh", 0)
    assert code == 124

def test_failure_summary_quotes_the_native_error_not_the_license_banner(tmp_path):
    from tcad_agent.runners.ssh import SSHSentaurusRunner

    (tmp_path / "sdevice.stdout.log").write_text(
        "*** license agreement between you, or your company, and Synopsys, Inc. ***\n"
        'Electrode/Thermode "source" cannot overlap or touch Electrode/Thermode "gate" !\n'
        "RelErrControl (Reference error):\n",
        encoding="utf-8",
    )
    text = SSHSentaurusRunner._failure_summary(tmp_path, 5, "")
    assert "cannot overlap or touch" in text
    assert "license unavailable" not in text and "agreement" not in text


def test_a_stalled_solve_is_described_from_the_simulator_log(tmp_path) -> None:
    assert 'before the device simulator started' in SSHSentaurusRunner._stall_detail(tmp_path)
    (tmp_path / 'sdevice.stdout.log').write_text(
        'KRONIG numerics level 0 stalled:\nKRONIG numerics level 1 stalled: 0\n'
    )
    detail = SSHSentaurusRunner._stall_detail(tmp_path)
    assert 'after 2 stalled numerical strategies' in detail and 'did not converge' in detail

