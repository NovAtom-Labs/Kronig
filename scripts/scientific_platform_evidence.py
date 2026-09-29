#!/usr/bin/env python3
"""Write or compare scientific reference-suite evidence from native CI targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tcad_agent.conformance.platform_evidence import (  # noqa: E402
    ScientificPlatformEvidence,
    compare_platform_evidence,
    load_platform_evidence,
    write_platform_evidence,
)

FIXTURE = ROOT / "tests" / "fixtures" / "devsim" / "official-reference-invariants.json"
SUITE = "tests/integration/test_devsim_reference_benchmarks.py"
TARGETS = (("linux", "x64"), ("win", "x64"), ("mac", "x64"), ("mac", "arm64"))


def _git_revision(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_command(platform_id: str, architecture: str, output: Path) -> None:
    import devsim

    fixture = json.loads(FIXTURE.read_text())
    expected_source = str(fixture["source"]["commit"])
    source_root = next(
        candidate
        for candidate in (ROOT / "devsim" / "source", ROOT.parent / "devsim" / "source")
        if candidate.is_dir()
    )
    actual_source = _git_revision(source_root)
    if actual_source != expected_source:
        raise ValueError(
            f"pinned DEVSIM source mismatch: expected {expected_source}, got {actual_source}"
        )
    application_commit = os.getenv("GITHUB_SHA") or _git_revision(ROOT)
    record = ScientificPlatformEvidence(
        platform=platform_id,
        architecture=architecture,
        application_commit=application_commit,
        python_version=platform.python_version(),
        devsim_version=str(devsim.__version__),
        devsim_source_commit=actual_source,
        invariant_fixture_sha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        scientific_suite=SUITE,
        status="passed",
    )
    write_platform_evidence(record, output)


def compare_command(inputs: Sequence[Path], output: Path | None) -> None:
    records = tuple(load_platform_evidence(path) for path in inputs)
    compare_platform_evidence(records, required_targets=TARGETS)
    payload = {
        "schema_version": "1.0",
        "status": "passed",
        "targets": [
            {"platform": record.platform, "architecture": record.architecture}
            for record in sorted(
                records, key=lambda item: (item.platform, item.architecture)
            )
        ],
        "application_commit": records[0].application_commit,
        "devsim_version": records[0].devsim_version,
        "devsim_source_commit": records[0].devsim_source_commit,
        "invariant_fixture_sha256": records[0].invariant_fixture_sha256,
    }
    rendered = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if output is None:
        print(rendered, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    write_parser = subparsers.add_parser("write")
    write_parser.add_argument("--platform", required=True, choices=("linux", "win", "mac"))
    write_parser.add_argument("--arch", required=True, choices=("x64", "arm64"))
    write_parser.add_argument("--output", required=True, type=Path)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("inputs", nargs="+", type=Path)
    compare_parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "write":
        write_command(arguments.platform, arguments.arch, arguments.output)
    else:
        compare_command(arguments.inputs, arguments.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
