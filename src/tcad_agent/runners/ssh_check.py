"""Plain pass/fail preflight for the SSH Sentaurus pathway on a new machine."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import shlex
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import paramiko

from tcad_agent.adapters.sentaurus.mesh import _site_lines
from tcad_agent.domain.errors import CapabilityError

_REQUIRED = {
    "TCAD_SENTAURUS_RUNNER": "set it to ssh",
    "TCAD_HPSC_HOST": "the HPC address, for example 10.0.0.5 or hpc.example.edu",
    "TCAD_HPSC_USER": "your login name on the HPC",
    "TCAD_SENTAURUS_VERSION": "the exact release, for example O-2018.06-SP2",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    fix: str = ""


def _fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def _server_key(host: str, port: int) -> paramiko.PKey:
    transport = paramiko.Transport((host, port))
    try:
        transport.start_client(timeout=15)
        return transport.get_remote_server_key()
    finally:
        transport.close()


def run_checks(
    *,
    trust_host: bool = False,
    deep: bool = False,
    emit: Callable[[CheckResult], None] | None = None,
) -> list[CheckResult]:
    """Run the checks in order, stopping at the first failure that blocks the rest."""
    results: list[CheckResult] = []

    def record(name: str, ok: bool, detail: str, fix: str = "") -> bool:
        result = CheckResult(name, ok, detail, fix)
        results.append(result)
        if emit:
            emit(result)
        return ok

    missing = [
        f"{name} ({hint})"
        for name, hint in _REQUIRED.items()
        if not os.getenv(name, "").strip()
        or (name == "TCAD_SENTAURUS_RUNNER" and os.getenv(name, "").lower() != "ssh")
    ]
    if missing:
        record("settings", False, "missing: " + "; ".join(missing), "add them to the .env file")
        return results
    record("settings", True, "required environment settings are present")

    host = os.environ["TCAD_HPSC_HOST"]
    user = os.environ["TCAD_HPSC_USER"]
    port = int(os.getenv("TCAD_HPSC_PORT", "22"))
    try:
        socket.create_connection((host, port), timeout=8).close()
    except OSError as error:
        record(
            "network",
            False,
            f"cannot reach {host}:{port} ({error})",
            "connect this computer to the HPC network or VPN (for example Tailscale) first",
        )
        return results
    record("network", True, f"{host}:{port} is reachable")

    known = Path.home() / ".ssh" / "known_hosts"
    keys = paramiko.HostKeys()
    if known.exists():
        keys.load(str(known))
    lookup = keys.lookup(host if port == 22 else f"[{host}]:{port}")
    if lookup is None:
        try:
            key = _server_key(host, port)
        except Exception as error:
            record("host key", False, f"could not read the server key ({error})")
            return results
        if not trust_host:
            record(
                "host key",
                False,
                f"{host} is not in {known} (server fingerprint {_fingerprint(key)})",
                "confirm that fingerprint with the HPC administrator, then rerun with --trust-host",
            )
            return results
        known.parent.mkdir(parents=True, exist_ok=True)
        keys.add(host if port == 22 else f"[{host}]:{port}", key.get_name(), key)
        keys.save(str(known))
        record("host key", True, f"trusted {_fingerprint(key)} and saved it to {known}")
    else:
        record("host key", True, "the server key is already trusted")

    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=os.getenv("TCAD_HPSC_PASSWORD") or None,
            allow_agent=True,
            look_for_keys=True,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
        )
    except Exception as error:
        record(
            "login",
            False,
            f"{type(error).__name__}: {error}",
            "check TCAD_HPSC_USER and TCAD_HPSC_PASSWORD, or load an SSH key for this account",
        )
        return results
    record("login", True, f"logged in as {user}")

    def remote(command: str, seconds: int = 60) -> tuple[int, str]:
        _, stdout, stderr = client.exec_command(command, timeout=seconds)
        text = stdout.read().decode(errors="replace") + stderr.read().decode(errors="replace")
        return stdout.channel.recv_exit_status(), text.strip()

    try:
        try:
            site = "".join(f"{line}; " for line in _site_lines())
        except CapabilityError as error:
            record("site setup", False, str(error), "shorten TCAD_SENTAURUS_SETUP to one line")
            return results
        probe_tools = "for t in sde sdevice timeout; do command -v $t || echo MISSING:$t; done"
        code, text = remote(f"{site}{probe_tools}")
        absent = re.findall(r"MISSING:(\w+)", text)
        if absent:
            record(
                "tools",
                False,
                "not found on the HPC: " + ", ".join(absent),
                "set TCAD_SENTAURUS_SETUP (for example 'module load sentaurus') or "
                "TCAD_SENTAURUS_BIN (the folder holding sde and sdevice)",
            )
            return results
        record("tools", True, text.replace("\n", "; "))

        code, text = remote(f"{site}timeout 120 sdevice -h 2>&1 | head -40")
        found = re.search(r"Version\s+([A-Za-z0-9._\-]+)", text)
        expected = os.environ["TCAD_SENTAURUS_VERSION"]
        if found is None:
            record("release", False, "sdevice printed no version banner", "check the install")
        elif found.group(1) != expected:
            record(
                "release",
                False,
                f"host runs {found.group(1)} but TCAD_SENTAURUS_VERSION is {expected}",
                f"set TCAD_SENTAURUS_VERSION={found.group(1)}",
            )
        else:
            record("release", True, f"Sentaurus Device {found.group(1)}")

        root = os.getenv("TCAD_HPSC_REMOTE_ROOT", "~/novatom-labs/runs")
        if root == "~":
            quoted = '"$HOME"'
        elif root.startswith("~/"):
            quoted = '"$HOME"/' + shlex.quote(root[2:])
        else:
            quoted = shlex.quote(root)
        probe = f"{quoted}/.kronig-check"
        code, text = remote(f"mkdir -p {quoted} && touch {probe} && rm -f {probe} && echo ok")
        if code == 0 and text.endswith("ok"):
            record("work folder", True, f"{root} is writable")
        else:
            detail = text or f"cannot write {root}"
            record("work folder", False, detail, "set TCAD_HPSC_REMOTE_ROOT to a writable folder")

        if deep:
            script = "(sde:clear)\n(sdegeo:create-rectangle (position 0 0 0) (position 1 1 0) "
            script += '"Silicon" "r")\n'
            code, text = remote(
                f"{site}d=$(mktemp -d) && cd $d && printf '%s' {shlex.quote(script)} > t.scm && "
                "timeout 180 sde -e -l t.scm > out.log 2>&1; rc=$?; "
                "grep -c 'Total Execution Time' out.log; rm -rf $d; exit $rc",
                seconds=200,
            )
            record(
                "license",
                code == 0 and text.strip().endswith("1"),
                "the structure editor started and finished" if code == 0 else text[-300:],
                "ask the HPC administrator whether your account may check out Sentaurus licenses",
            )
    finally:
        client.close()
    return results
