"""SSH runner for executing Sentaurus on the HPSC machine."""

from __future__ import annotations

import getpass
import os
import time
from pathlib import Path
from uuid import uuid4

import paramiko

from tcad_agent.runners.models import CompiledJob, NativeRunResult, RunBudget


class SSHRunnerError(RuntimeError):
    """Raised when the SSH-based Sentaurus runner fails."""


class SSHSentaurusRunner:
    """Run Sentaurus remotely on HPSC using SSH and SFTP."""

    def __init__(
        self,
        host: str | None = None,
        user: str | None = None,
        port: int | None = None,
        remote_root: str | None = None,
    ) -> None:
        self.host = host or os.getenv("TCAD_HPSC_HOST")
        self.user = user or os.getenv("TCAD_HPSC_USER")
        self.port = port or int(os.getenv("TCAD_HPSC_PORT", "22"))
        self.remote_root = remote_root or os.getenv(
            "TCAD_HPSC_REMOTE_ROOT",
            "~/novatom-labs/runs",
        )

        self._password: str | None = os.getenv("TCAD_HPSC_PASSWORD")

    def _get_password(self) -> str:
        if not self._password:
            if not self.user or not self.host:
                raise SSHRunnerError(
                    "TCAD_HPSC_HOST and TCAD_HPSC_USER must be configured"
                )

        self._password = getpass.getpass(
            f"HPSC password for {self.user}@{self.host}: "
        )
        os.environ["TCAD_HPSC_PASSWORD"] = self._password

        return self._password

    def _connect(self) -> paramiko.SSHClient:
        if not self.host or not self.user:
            raise SSHRunnerError(
                "TCAD_HPSC_HOST and TCAD_HPSC_USER must be configured"
            )

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.user,
            password=self._get_password(),
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
        )

        return client

    def run(
        self,
        job: CompiledJob,
        budget: RunBudget,
    ) -> NativeRunResult:
        if job.backend != "sentaurus":
            raise ValueError(
                "SSH Sentaurus runner accepts only sentaurus jobs"
            )

        workspace = job.entrypoint.parent.resolve()
        remote_job_id = str(uuid4())

        output_dir = workspace / "ssh-result"
        output_dir.mkdir(mode=0o700, exist_ok=True)

        stdout_path = output_dir / "runner.stdout.log"
        stderr_path = output_dir / "runner.stderr.log"
        return_code_path = output_dir / "runner.return_code"

        start = time.monotonic()
        client: paramiko.SSHClient | None = None

        try:
            client = self._connect()

            # Expand ~/novatom-labs/runs on the remote machine.
            stdin, stdout, stderr = client.exec_command(
                "printf '%s' \"$HOME\""
            )
            home = stdout.read().decode().strip()

            if not home:
                raise SSHRunnerError(
                    "Could not determine remote home directory"
                )

            remote_root = self.remote_root

            if remote_root.startswith("~/"):
                remote_root = f"{home}/{remote_root[2:]}"

            remote_dir = f"{remote_root}/{remote_job_id}"

            # 1. Create remote workspace.
            stdin, stdout, stderr = client.exec_command(
                f"mkdir -p '{remote_dir}'"
            )

            exit_code = stdout.channel.recv_exit_status()

            if exit_code != 0:
                error = stderr.read().decode(errors="replace").strip()
                raise SSHRunnerError(
                    f"Could not create remote directory: {error}"
                )

            # 2. Upload input files.
            sftp = client.open_sftp()

            try:
                for path in job.input_files:
                    local_path = path.resolve()
                    remote_path = f"{remote_dir}/{path.name}"

                    sftp.put(
                        str(local_path),
                        remote_path,
                    )
            finally:
                sftp.close()

            # 3. Run Sentaurus remotely.
            command = (
                f"cd '{remote_dir}' && "
                f"timeout {int(budget.seconds)}s "
                f"sdevice '{job.entrypoint.name}' "
                f"> runner.stdout.log "
                f"2> runner.stderr.log; "
                f"echo $? > runner.return_code"
            )

            stdin, stdout, stderr = client.exec_command(command)

            execution_exit_code = stdout.channel.recv_exit_status()

            # 4. Download logs and result files.
            sftp = client.open_sftp()

            try:
                for remote_name, local_path in (
                (
                    "runner.stdout.log",
                    stdout_path,
                ),
                (
                    "runner.stderr.log",
                    stderr_path,
                ),
                (
                    "runner.return_code",
                    return_code_path,
                ),
                (
                    "sdevice.log",
                    output_dir / "sdevice.log",
                ),
            ):
                    try:
                        sftp.get(
                            f"{remote_dir}/{remote_name}",
                            str(local_path),
                        )
                    except FileNotFoundError:
                        pass

                for name in (
                    "sdevice.tdr",
                    "sdevice.plt",
                    "sentaurus-result.json",
                ):
                    try:
                        sftp.get(
                            f"{remote_dir}/{name}",
                            str(output_dir / name),
                        )
                    except FileNotFoundError:
                        pass
            finally:
                sftp.close()

            # 5. Determine actual Sentaurus return code.
            if return_code_path.exists():
                try:
                    return_code = int(
                        return_code_path.read_text().strip()
                    )
                except ValueError:
                    return_code = execution_exit_code
            else:
                return_code = execution_exit_code

            if return_code == 0:
                status = "completed"
                error = None
            elif return_code == 124:
                status = "timed_out"
                error = "Sentaurus execution timed out"
            else:
                status = "execution_failed"
                error = (
                    stderr_path.read_text(errors="replace")
                    if stderr_path.exists()
                    else "Sentaurus execution failed"
                )

            result_path = None

            for candidate in (
                output_dir / "sentaurus-result.json",
                output_dir / "sdevice.tdr",
            ):
                if candidate.exists():
                    result_path = candidate
                    break

            return NativeRunResult(
                backend="sentaurus",
                status=status,
                return_code=return_code,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                result_path=result_path,
                elapsed_seconds=time.monotonic() - start,
                error=error,
            )

        except Exception as exc:
            stdout_path.touch(exist_ok=True)
            stderr_path.touch(exist_ok=True)

            return NativeRunResult(
                backend="sentaurus",
                status="execution_failed",
                return_code=None,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                result_path=None,
                elapsed_seconds=time.monotonic() - start,
                error=str(exc),
            )

        finally:
            if client is not None:
                client.close()