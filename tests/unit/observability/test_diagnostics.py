from pathlib import Path

import pytest

from tcad_agent.observability.diagnostics import DiagnosticStore


def test_diagnostic_store_redacts_and_bounds_records(tmp_path: Path) -> None:
    store = DiagnosticStore(tmp_path, maximum_files=2, maximum_bytes=512)

    for index in range(4):
        store.write(
            diagnostic_id=f"diag-{index}",
            category="lifecycle",
            operation="shutdown",
            detail="token=secret-value " + ("x" * 1000),
        )

    files = tuple((tmp_path / "diagnostics").glob("*.json"))
    assert len(files) == 2
    assert all(path.stat().st_size <= 512 for path in files)
    assert "secret-value" not in "".join(path.read_text() for path in files)


def test_diagnostic_store_reads_only_a_safe_record_identifier(tmp_path: Path) -> None:
    store = DiagnosticStore(tmp_path)
    store.write(
        diagnostic_id="diag-0123456789abcdef",
        category="lifecycle",
        operation="desktop_shutdown",
        detail="password=should-not-escape cleanup failed",
    )

    record = store.read("diag-0123456789abcdef")

    assert record["diagnostic_id"] == "diag-0123456789abcdef"
    assert record["category"] == "lifecycle"
    assert "should-not-escape" not in record["detail"]
    with pytest.raises(ValueError, match="identifier"):
        store.read("../outside")
    with pytest.raises(FileNotFoundError):
        store.read("diag-ffffffffffffffff")
