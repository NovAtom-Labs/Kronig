"""SSH runner for executing Sentaurus remotely with a persisted audit trail."""

from __future__ import annotations

import json
import math
import os
import shlex
import stat
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import paramiko

from tcad_agent.runners.models import CompiledJob, NativeRunResult, RunBudget


class SSHRunnerError(RuntimeError):
    """Raised when the SSH-based Sentaurus runner fails."""


class SSHAuditError(OSError):
    """Raised when the SSH audit trail cannot be initialized or persisted."""


class SSHSentaurusRunner:
    """Run Sentaurus remotely on HPSC using SSH/SFTP and record every action."""

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

        self._audit_events: list[dict[str, object]] = []
        self._audit_json_path: Path | None = None
        self._audit_log_path: Path | None = None
        self._run_id: str | None = None
        self._started_at: str | None = None

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()

    def _safe_text(self, value: object) -> str:
        """Convert a value to text while redacting the configured SSH password."""
        if isinstance(value, bytes):
            text = value.decode("utf-8", errors="replace")
        elif isinstance(value, BaseException):
            text = str(value)
        else:
            text = str(value)
        if self._password:
            text = text.replace(self._password, "[REDACTED]")
        return text

    def _sanitize(self, value: object) -> object:
        """Recursively make event details JSON-safe and redact secrets."""
        if isinstance(value, Mapping):
            return {self._safe_text(key): self._sanitize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self._sanitize(item) for item in value]
        if isinstance(value, (str, bytes, BaseException, Path)):
            return self._safe_text(value)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self._safe_text(value)

    def _record(
        self,
        action: str,
        status: str,
        **details: object,
    ) -> None:
        """Persist a structured event and a human-readable log entry.

        Audit persistence errors are raised instead of ignored: continuing remote
        execution after losing the audit trail would violate the runner's contract.
        """
        sanitized_details = self._sanitize(details)
        if not isinstance(sanitized_details, dict):
            raise SSHAuditError("Could not serialize SSH audit event details")
        event: dict[str, object] = {
            "timestamp": self._timestamp(),
            "run_id": self._run_id,
            "action": action,
            "status": status,
            "details": sanitized_details,
        }
        self._audit_events.append(event)

        try:
            if self._audit_json_path is not None:
                document = {
                    "schema_version": 1,
                    "run_id": self._run_id,
                    "started_at": self._started_at,
                    "updated_at": self._timestamp(),
                    "events": self._audit_events,
                }
                temporary_path = self._audit_json_path.with_suffix(".json.tmp")
                temporary_path.write_text(
                    json.dumps(document, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                temporary_path.replace(self._audit_json_path)

            if self._audit_log_path is not None:
                details_text = json.dumps(
                    sanitized_details,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                line = (
                    f"{event['timestamp']} [{status.upper()}] {action}"
                    f"{' | ' + details_text if details_text != '{}' else ''}\n"
                )
                with self._audit_log_path.open("a", encoding="utf-8") as log_file:
                    log_file.write(line)
        except OSError as exc:
            raise SSHAuditError(
                f"Could not persist SSH audit trail ({type(exc).__name__})"
            ) from exc

    def _initialize_audit(self, output_dir: Path) -> None:
        """Start clean per-run audit files and prevent stale events being reused."""
        self._audit_json_path = output_dir / "ssh-audit.json"
        self._audit_log_path = output_dir / "ssh-audit.log"
        try:
            self._audit_json_path.unlink(missing_ok=True)
            self._audit_json_path.with_suffix(".json.tmp").unlink(missing_ok=True)
            self._audit_log_path.write_text("", encoding="utf-8")
        except OSError as exc:
            raise SSHAuditError(
                f"Could not initialize SSH audit files ({type(exc).__name__})"
            ) from exc

    def _connect(self) -> paramiko.SSHClient:
        if not self.host or not self.user:
            raise SSHRunnerError("TCAD_HPSC_HOST and TCAD_HPSC_USER must be configured")

        self._record(
            "ssh.connect",
            "started",
            host=self.host,
            port=self.port,
            user=self.user,
        )

        client = paramiko.SSHClient()

        try:
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
            client.connect(
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self._password,
                allow_agent=True,
                look_for_keys=True,
                timeout=15,
                banner_timeout=15,
                auth_timeout=15,
            )
        except Exception as exc:
            try:
                self._record(
                    "ssh.connect",
                    "failed",
                    error=self._safe_text(exc),
                )
            finally:
                try:
                    client.close()
                except Exception as close_exc:
                    try:
                        self._record(
                            "ssh.client_close",
                            "failed",
                            error=self._safe_text(close_exc),
                        )
                    except SSHAuditError:
                        # Preserve the original connection/audit failure after cleanup.
                        pass
            raise

        try:
            self._record("ssh.connect", "succeeded")
        except SSHAuditError:
            # The connection is live, but we must not use it without a durable audit.
            try:
                client.close()
            except Exception:
                pass
            raise
        return client

    def _exec(
        self,
        client: paramiko.SSHClient,
        command: str,
        action: str,
    ) -> tuple[int, str, str]:
        """Execute and audit one remote command, including its exit status."""
        self._record(
            action,
            "started",
            command=command,
        )

        try:
            _stdin, stdout, stderr = client.exec_command(command)
            stdout_text = stdout.read().decode(errors="replace")
            stderr_text = stderr.read().decode(errors="replace")
            exit_code = stdout.channel.recv_exit_status()

            self._record(
                action,
                "succeeded" if exit_code == 0 else "failed",
                exit_code=exit_code,
                stdout_bytes=len(stdout_text.encode()),
                stderr_bytes=len(stderr_text.encode()),
                stderr=self._safe_text(stderr_text[-2000:]) if stderr_text.strip() else "",
            )
            return exit_code, stdout_text, stderr_text
        except Exception as exc:
            self._record(
                action,
                "failed",
                error=self._safe_text(exc),
            )
            raise

    def _upload_files(
        self,
        client: paramiko.SSHClient,
        job: CompiledJob,
        remote_dir: str,
    ) -> None:
        sftp = None
        try:
            self._record("sftp.open_upload", "started")
            try:
                sftp = client.open_sftp()
            except Exception as exc:
                self._record(
                    "sftp.open_upload",
                    "failed",
                    error=self._safe_text(exc),
                )
                raise
            self._record("sftp.open_upload", "succeeded")

            for path in job.input_files:
                local_path = path.resolve()
                remote_path = f"{remote_dir}/{path.name}"

                self._record(
                    "sftp.upload",
                    "started",
                    filename=path.name,
                    size_bytes=local_path.stat().st_size,
                    remote_path=remote_path,
                )
                try:
                    sftp.put(str(local_path), remote_path)
                    self._record(
                        "sftp.upload",
                        "succeeded",
                        filename=path.name,
                        size_bytes=local_path.stat().st_size,
                    )
                except Exception as exc:
                    self._record(
                        "sftp.upload",
                        "failed",
                        filename=path.name,
                        error=self._safe_text(exc),
                    )
                    raise
        finally:
            if sftp is not None:
                try:
                    sftp.close()
                except Exception as exc:
                    self._record(
                        "sftp.close_upload",
                        "failed",
                        error=self._safe_text(exc),
                    )
                    raise
                else:
                    self._record("sftp.close_upload", "succeeded")

    def _download_files(
        self,
        client: paramiko.SSHClient,
        remote_dir: str,
        output_dir: Path,
        names: tuple[str, ...],
        maximum_bytes: int | None = None,
    ) -> None:
        sftp = None
        try:
            self._record("sftp.open_download", "started")
            try:
                sftp = client.open_sftp()
            except Exception as exc:
                self._record(
                    "sftp.open_download",
                    "failed",
                    error=self._safe_text(exc),
                )
                raise
            self._record("sftp.open_download", "succeeded")

            downloaded = 0
            for name in names:
                remote_path = f"{remote_dir}/{name}"
                local_path = output_dir / name

                self._record(
                    "sftp.download",
                    "started",
                    filename=name,
                    remote_path=remote_path,
                )
                try:
                    if maximum_bytes is None:
                        sftp.get(remote_path, str(local_path))
                    else:
                        attributes = sftp.lstat(remote_path)
                        if (
                            not stat.S_ISREG(attributes.st_mode)
                            or attributes.st_size + downloaded > maximum_bytes
                        ):
                            raise SSHRunnerError(
                                "export tables exceed size limit or are not regular files"
                            )

                        def check_size(
                            transferred: int, total: int, prior: int = downloaded
                        ) -> None:
                            if transferred + prior > maximum_bytes:
                                raise SSHRunnerError("export tables exceed transfer size limit")

                        sftp.get(remote_path, str(local_path), callback=check_size)
                        downloaded += local_path.stat().st_size
                    self._record(
                        "sftp.download",
                        "succeeded",
                        filename=name,
                        size_bytes=local_path.stat().st_size,
                    )
                except FileNotFoundError as exc:
                    # Missing result files can be normal when Sentaurus fails.
                    self._record(
                        "sftp.download",
                        "unavailable",
                        filename=name,
                        error=self._safe_text(exc),
                    )
                except Exception as exc:
                    self._record(
                        "sftp.download",
                        "failed",
                        filename=name,
                        error=self._safe_text(exc),
                    )
                    raise
        finally:
            if sftp is not None:
                try:
                    sftp.close()
                except Exception as exc:
                    self._record(
                        "sftp.close_download",
                        "failed",
                        error=self._safe_text(exc),
                    )
                    raise
                else:
                    self._record("sftp.close_download", "succeeded")

    def _download_export_tables(self, client, remote_dir: str, output_dir: Path) -> None:
        from tcad_agent.adapters.sentaurus.tables import TableExport

        path = output_dir / "sentaurus-result.json"
        if path.stat().st_size > 64 * 1024 * 1024:
            raise SSHRunnerError("native export exceeds size limit")
        payload = json.loads(path.read_bytes())
        if isinstance(payload, dict) and payload.get("schema_version") == "2.0":
            export = TableExport.model_validate(payload)
            names = tuple(
                sorted({item.table.file for item in export.datasets.values() if item.table})
            )
            if names:
                self._download_files(
                    client, remote_dir, output_dir, names, maximum_bytes=64 * 1024 * 1024
                )

    def run(
        self,
        job: CompiledJob,
        budget: RunBudget,
    ) -> NativeRunResult:
        if job.backend != "sentaurus":
            raise ValueError("SSH Sentaurus runner accepts only sentaurus jobs")

        workspace = job.entrypoint.parent.resolve()
        self._run_id = str(uuid4())
        self._started_at = self._timestamp()
        self._audit_events = []

        output_dir = workspace / "ssh-result" / self._run_id
        output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._initialize_audit(output_dir)
        audit_json_path = self._audit_json_path
        audit_log_path = self._audit_log_path
        assert audit_json_path is not None and audit_log_path is not None

        stdout_path = output_dir / "runner.stdout.log"
        stderr_path = output_dir / "runner.stderr.log"
        return_code_path = output_dir / "runner.return_code"

        start = time.monotonic()
        client: paramiko.SSHClient | None = None
        status = "execution_failed"
        return_code: int | None = None
        error: str | None = None
        result_path: Path | None = None
        audit_failure: SSHAuditError | None = None

        self._record(
            "run.start",
            "started",
            backend=job.backend,
            entrypoint=job.entrypoint.name,
            input_files=[path.name for path in job.input_files],
            budget_seconds=budget.seconds,
            host=self.host,
            port=self.port,
            user=self.user,
        )

        try:
            manifest = None
            if any(path.name == "job-manifest.json" for path in job.input_files):
                from tcad_agent.adapters.sentaurus.runtime import validate_bundle

                manifest = validate_bundle(
                    job, simulator_version=os.getenv("TCAD_SENTAURUS_VERSION")
                )
                self._record("bundle.preflight", "succeeded", input_digest=job.input_digest)
            client = self._connect()

            exit_code, home_output, _ = self._exec(
                client,
                'printf "%s" "$HOME"',
                "remote.get_home",
            )
            home = home_output.strip()
            if exit_code != 0 or not home:
                raise SSHRunnerError("Could not determine remote home directory")

            remote_root = self.remote_root
            if remote_root == "~":
                remote_root = home
            elif remote_root.startswith("~/"):
                remote_root = f"{home}/{remote_root[2:]}"

            remote_dir = f"{remote_root.rstrip('/')}/{self._run_id}"
            self._record(
                "remote.workspace",
                "started",
                remote_dir=remote_dir,
            )

            mkdir_command = f"mkdir -p -- {shlex.quote(remote_dir)}"
            exit_code, _, stderr_text = self._exec(
                client,
                mkdir_command,
                "remote.mkdir",
            )
            if exit_code != 0:
                raise SSHRunnerError(
                    f"Could not create remote directory: {self._safe_text(stderr_text.strip())}"
                )
            self._record(
                "remote.workspace",
                "succeeded",
                remote_dir=remote_dir,
            )

            self._upload_files(client, job, remote_dir)

            command = (
                f"cd {shlex.quote(remote_dir)} && "
                f"timeout {budget.seconds:g}s "
                f"sdevice {shlex.quote(job.entrypoint.name)} "
                f"> runner.stdout.log 2> runner.stderr.log; "
                f"rc=$?; "
                f"printf '%s\\n' \"$rc\" > runner.return_code; "
                f'exit "$rc"'
            )

            _exit_code, _stdout_text, _stderr_text = self._exec(
                client,
                command,
                "sentaurus.execute",
            )

            # Retain shell diagnostics even if the remote logs cannot be fetched.
            stdout_path.write_text(self._safe_text(_stdout_text), encoding="utf-8")
            stderr_path.write_text(self._safe_text(_stderr_text), encoding="utf-8")

            self._download_files(
                client,
                remote_dir,
                output_dir,
                (
                    "runner.stdout.log",
                    "runner.stderr.log",
                    "runner.return_code",
                    "sdevice.log",
                    "sdevice.tdr",
                    "sdevice.plt",
                ),
            )
            self._download_files(
                client,
                remote_dir,
                output_dir,
                ("sentaurus-result.json",),
                maximum_bytes=64 * 1024 * 1024,
            )

            if return_code_path.exists():
                try:
                    return_code = int(return_code_path.read_text().strip())
                except ValueError:
                    self._record(
                        "sentaurus.return_code",
                        "invalid",
                        file="runner.return_code",
                    )

            if return_code is None:
                # The remote command's exit code also covers command failures.
                return_code = _exit_code

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

            for candidate in (
                output_dir / "sentaurus-result.json",
                output_dir / "sdevice.tdr",
            ):
                if candidate.exists():
                    result_path = candidate
                    break

            if status == "completed":
                from tcad_agent.adapters.sentaurus.normalizer import SentaurusNormalizer

                try:
                    if result_path is None or result_path.name != "sentaurus-result.json":
                        raise SSHRunnerError(
                            "simulation exited successfully but no native table export "
                            "was produced; "
                            "binary TDR is not a canonical result"
                        )
                    self._download_export_tables(client, remote_dir, output_dir)
                    normalized = SentaurusNormalizer().normalize(
                        NativeRunResult(
                            backend="sentaurus",
                            status="completed",
                            return_code=return_code,
                            stdout_path=stdout_path,
                            stderr_path=stderr_path,
                            result_path=result_path,
                            elapsed_seconds=time.monotonic() - start,
                        )
                    )
                    if manifest and manifest.native_review:
                        if normalized.simulator_version != manifest.native_review.simulator_version:
                            raise SSHRunnerError(
                                "native export release differs from the reviewed release"
                            )
                        provenance = normalized.metadata.get("declared_provenance")
                        if provenance != {
                            "compiler_version": manifest.compiler_version,
                            "experiment_sha256": manifest.inputs["experiment.json"],
                            "mesh_sha256": manifest.inputs["device.tdr"],
                        }:
                            raise SSHRunnerError(
                                "native export provenance differs from the submitted bundle"
                            )
                        from tcad_agent.domain.models import ExperimentSpec

                        spec = ExperimentSpec.model_validate_json(
                            (workspace / "experiment.json").read_bytes()
                        )
                        if set(normalized.terminals) != {contact.id for contact in spec.contacts}:
                            raise SSHRunnerError(
                                "native export terminals differ from the submitted experiment"
                            )
                        points = normalized.operating_points
                        expected = manifest.operating_points
                        if expected:
                            if len(points) != len(expected) or len(normalized.bias_points) != len(
                                expected
                            ):
                                raise SSHRunnerError(
                                    "native export point count differs from the submitted schedule"
                                )
                            for actual, requested in zip(
                                normalized.bias_points, expected, strict=True
                            ):
                                if not math.isclose(
                                    actual.bias_v, requested.bias_v, rel_tol=1e-12, abs_tol=1e-15
                                ):
                                    raise SSHRunnerError(
                                        "native export bias differs from the submitted schedule"
                                    )
                        elif len(points) != 1:
                            raise SSHRunnerError(
                                "equilibrium export must contain exactly one operating point"
                            )
                except (OSError, ValueError, SSHRunnerError) as exc:
                    status = "malformed_result"
                    error = self._safe_text(exc)

            self._record(
                "run.result",
                status,
                return_code=return_code,
                result_file=result_path.name if result_path else None,
                error=self._safe_text(error) if error else None,
            )

        except Exception as exc:
            status = "execution_failed"
            error = self._safe_text(exc)
            try:
                self._record(
                    "run.error",
                    "failed",
                    error=error,
                    exception_type=type(exc).__name__,
                )
            except SSHAuditError as audit_exc:
                audit_failure = audit_exc
            stdout_path.touch(exist_ok=True)
            stderr_path.touch(exist_ok=True)

            if not stderr_path.stat().st_size and error:
                stderr_path.write_text(error, encoding="utf-8")

        finally:
            if client is not None:
                if audit_failure is None:
                    try:
                        self._record("ssh.disconnect", "started")
                    except SSHAuditError as audit_exc:
                        audit_failure = audit_exc
                try:
                    client.close()
                except Exception as exc:
                    if audit_failure is None:
                        try:
                            self._record(
                                "ssh.disconnect",
                                "failed",
                                error=self._safe_text(exc),
                            )
                        except SSHAuditError as audit_exc:
                            audit_failure = audit_exc
                else:
                    if audit_failure is None:
                        try:
                            self._record("ssh.disconnect", "succeeded")
                        except SSHAuditError as audit_exc:
                            audit_failure = audit_exc

            elapsed = time.monotonic() - start
            if audit_failure is None:
                try:
                    self._record(
                        "run.finish",
                        status,
                        elapsed_seconds=round(elapsed, 3),
                        return_code=return_code,
                        audit_json=audit_json_path.name,
                        audit_log=audit_log_path.name,
                    )
                except SSHAuditError as audit_exc:
                    audit_failure = audit_exc

        if audit_failure is not None:
            raise audit_failure

        return NativeRunResult(
            backend="sentaurus",
            status=status,
            return_code=return_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            result_path=result_path,
            elapsed_seconds=time.monotonic() - start,
            error=error,
            audit_json_path=audit_json_path,
            audit_log_path=audit_log_path,
        )
