from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.run_ci_pytest import failed_test_annotations


def test_failed_test_annotations_are_bounded_and_github_safe(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite failures="1" errors="0" tests="1">
    <testcase classname="tests.test_example" name="test_failure"
              file="tests/test_example.py" line="11">
      <failure message="assert left == right">first line\nsecond%line\rthird</failure>
    </testcase>
  </testsuite>
</testsuites>
"""
    )

    annotations = failed_test_annotations(report)

    assert annotations == (
        "::error file=tests/test_example.py,line=12,title=Pytest failure%3A "
        "tests.test_example.test_failure::assert left == right%0Afirst line%0A"
        "second%25line%0Athird",
    )


def test_failed_test_annotations_report_a_missing_junit_file(tmp_path: Path) -> None:
    assert failed_test_annotations(tmp_path / "missing.xml") == (
        "::error title=Pytest failed before reporting::No JUnit report was produced",
    )


def test_long_failure_retains_final_traceback_not_only_test_source(tmp_path: Path) -> None:
    report = tmp_path / "pytest.xml"
    report.write_text(
        '<testsuite><testcase name="native_boundary"><failure message="native error">'
        + "test source line\n" * 1000
        + "actual_driver.py:42: NativeError: exact diagnostic</failure></testcase></testsuite>"
    )
    annotation = failed_test_annotations(report)[0]
    assert "exact diagnostic" in annotation
    assert "native error" in annotation
    assert len(annotation) < 5000
