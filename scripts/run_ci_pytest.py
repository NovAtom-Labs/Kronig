#!/usr/bin/env python3
"""Run pytest and expose bounded failures as GitHub check annotations."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def _command_value(value: str, *, property_value: bool = False) -> str:
    escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        escaped = escaped.replace(":", "%3A").replace(",", "%2C")
    return escaped


def failed_test_annotations(report: Path) -> tuple[str, ...]:
    """Return GitHub workflow error commands for failures in one JUnit report."""

    if not report.is_file():
        return ("::error title=Pytest failed before reporting::No JUnit report was produced",)
    try:
        root = ET.parse(report).getroot()
    except ET.ParseError as exc:
        return ("::error title=Pytest report is invalid::" + _command_value(str(exc)[:2000]),)

    annotations: list[str] = []
    for case in root.iter("testcase"):
        outcome = case.find("failure")
        if outcome is None:
            outcome = case.find("error")
        if outcome is None:
            continue
        classname = case.get("classname", "unknown")
        name = case.get("name", "unknown")
        title = _command_value(f"Pytest failure: {classname}.{name}", property_value=True)
        properties = [f"title={title}"]
        file_name = case.get("file")
        if file_name:
            properties.insert(0, f"file={_command_value(file_name, property_value=True)}")
        line = case.get("line")
        if line and line.isdigit():
            properties.insert(1 if file_name else 0, f"line={int(line) + 1}")
        message_parts = [outcome.get("message", "Test failed")]
        if outcome.text and outcome.text.strip():
            message_parts.append(outcome.text.strip())
        message = "\n".join(message_parts)
        if len(message) > 4000:
            message = message[:1000] + "\n[... bounded traceback ...]\n" + message[-2900:]
        message = _command_value(message)
        annotations.append(f"::error {','.join(properties)}::{message}")
    if not annotations:
        annotations.append(
            "::error title=Pytest failed without a test case::"
            "Inspect the test process exit and collection output"
        )
    return tuple(annotations)


def main(arguments: list[str] | None = None) -> int:
    extra_arguments = list(arguments if arguments is not None else sys.argv[1:])
    with tempfile.TemporaryDirectory(prefix="agent-kronig-pytest-") as directory:
        report = Path(directory) / "pytest.xml"
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", f"--junitxml={report}", *extra_arguments],
            check=False,
        )
        if completed.returncode:
            for annotation in failed_test_annotations(report):
                print(annotation, flush=True)
        return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
