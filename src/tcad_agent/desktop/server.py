"""Managed loopback backend entrypoint for the Electron desktop shell."""

from __future__ import annotations

import json
import os
import socket
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

import uvicorn
from fastapi import FastAPI

from tcad_agent.desktop.auth import DesktopAuth
from tcad_agent.desktop.config import DesktopLaunchConfig
from tcad_agent.desktop.lock import DataDirectoryLock, DesktopDataLockError
from tcad_agent.desktop.owner_monitor import anchor_main, monitor_main, start_owner_monitor
from tcad_agent.desktop.session_storage import (
    DesktopSessionStorage,
    DesktopSessionStorageError,
)
from tcad_agent.web.app import create_app
from tcad_agent.web.ide_routes import build_default_ide_services
from tcad_agent.web.runtime import runtime_fingerprint


def readiness_record(
    config: DesktopLaunchConfig,
    *,
    url: str,
    pid: int,
    fingerprint: str,
    owner_monitor_pid: int | None = None,
) -> dict[str, str | int]:
    """Return the versioned machine-readable shell handshake."""

    record: dict[str, str | int] = {
        "protocol": config.protocol_version,
        "url": url,
        "pid": pid,
        "runtime_fingerprint": fingerprint,
    }
    if owner_monitor_pid is not None:
        record["owner_monitor_pid"] = owner_monitor_pid
    return record


def bind_desktop_socket(config: DesktopLaunchConfig) -> socket.socket:
    """Bind and listen before advertising desktop readiness."""

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((config.host, config.port))
        listener.listen(128)
        return listener
    except Exception:
        listener.close()
        raise


def create_desktop_app(
    config: DesktopLaunchConfig, runtime_root: Path
) -> FastAPI:
    """Create one authenticated application rooted in temporary session storage."""

    os.environ["TCAD_WORKSPACE"] = str(runtime_root)
    if config.devsim_runner is not None:
        os.environ["AGENT_KRONIG_DEVSIM_RUNNER"] = str(config.devsim_runner)
    services = build_default_ide_services()
    return create_app(
        runtime_id=runtime_fingerprint(),
        ide=services,
        desktop_auth=DesktopAuth(config.launch_token),
    )


def serve_desktop(
    config: DesktopLaunchConfig,
    *,
    output: TextIO = sys.stdout,
) -> None:
    """Run the authenticated desktop backend until the owning shell exits."""

    owner_monitor = start_owner_monitor() if config.owner_pipe else None
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with DataDirectoryLock(config.data_dir):
        storage = DesktopSessionStorage.prepare(config.data_dir)
        listener: socket.socket | None = None
        try:
            listener = bind_desktop_socket(config)
            host, port = listener.getsockname()
            fingerprint = runtime_fingerprint()
            record = readiness_record(
                config,
                url=f"http://{host}:{port}",
                pid=os.getpid(),
                fingerprint=fingerprint,
                owner_monitor_pid=owner_monitor.pid if owner_monitor is not None else None,
            )
            output.write(json.dumps(record, separators=(",", ":")) + "\n")
            output.flush()
            server = uvicorn.Server(
                uvicorn.Config(
                    create_desktop_app(config, storage.runtime_root),
                    log_level="info",
                    access_log=False,
                )
            )
            server.run(sockets=[listener])
        finally:
            if listener is not None:
                listener.close()
            storage.cleanup()


def main(environment: Mapping[str, str] | None = None) -> None:
    """Console entrypoint used by Electron and packaged sidecars."""

    try:
        if sys.argv[1:] == ["--owner-anchor"]:
            anchor_main()
            return
        if len(sys.argv) == 3 and sys.argv[1] == "--owner-monitor":
            monitor_main(int(sys.argv[2]))
            return
        serve_desktop(DesktopLaunchConfig.from_environment(environment))
    except (
        ValueError,
        DesktopDataLockError,
        DesktopSessionStorageError,
        OSError,
        RuntimeError,
    ) as exc:
        print(f"Agent Kronig desktop backend could not start: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
