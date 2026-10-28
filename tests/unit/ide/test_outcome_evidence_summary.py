from __future__ import annotations

from pathlib import Path

from tcad_agent.ide.outcomes import outcome_evidence_summary
from tcad_agent.validation.models import ValidationCheck, ValidationReport


def _write(root: Path, checks: list[ValidationCheck]) -> None:
    report = ValidationReport(overall="passed", checks=tuple(checks))
    (root / "validation.json").write_text(report.model_dump_json())


def _check(check_id: str, status: str, message: str = "ok") -> ValidationCheck:
    return ValidationCheck(id=check_id, level="numerical", status=status, message=message)


def test_summary_counts_passed_and_names_failures(tmp_path: Path) -> None:
    _write(
        tmp_path,
        [
            _check("a", "passed"),
            _check("b", "passed"),
            _check("mesh", "failed", "conduction band changed 47% between meshes"),
        ],
    )
    text = outcome_evidence_summary(tmp_path)
    assert "2 checks passed, 1 failed" in text
    assert "mesh - conduction band changed 47% between meshes." in text


def test_summary_limits_listed_failures(tmp_path: Path) -> None:
    _write(tmp_path, [_check(f"c{i}", "failed", "bad") for i in range(5)])
    text = outcome_evidence_summary(tmp_path, max_failures=2)
    assert "c0" in text and "c1" in text and "c2" not in text
    assert "+3 more" in text


def test_summary_is_empty_without_a_report(tmp_path: Path) -> None:
    assert outcome_evidence_summary(tmp_path) == ""
