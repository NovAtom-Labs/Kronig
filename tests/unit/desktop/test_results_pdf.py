"""Opt-in hidden Electron PDF integration, including the real allowlisted bridge."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(not os.getenv("KRONIG_TEST_PDF"), reason="requires installed Electron runtime")
def test_scientific_pdf_preserves_results_and_excludes_private_chat(tmp_path: Path) -> None:
    from pypdf import PdfReader

    root = Path(__file__).resolve().parents[3]
    distribution = root / "desktop/node_modules/electron/dist"
    electron = distribution / (
        "Electron.app/Contents/MacOS/Electron" if sys.platform == "darwin"
        else "electron.exe" if os.name == "nt" else "electron"
    )
    destination = tmp_path / "scientific-results.pdf"
    completed = subprocess.run(
        [str(electron), str(root / "desktop/fixtures/print-scientific-results.cjs"),
         str(destination)],
        capture_output=True, text=True, timeout=45, check=False,
        env={key: value for key, value in os.environ.items() if key != "ELECTRON_RUN_AS_NODE"},
    )
    assert completed.returncode == 0, completed.stderr[-4000:]
    reader = PdfReader(destination)
    text = "\n".join(page.extract_text() for page in reader.pages)
    for phrase in (
        "Scientific PDF regression", "silicon-bulk", "Potential", "V/m",
        "Terminal conservation requires review", "2.960e-6", "A/m^2",
        "absolute tolerance", "test-simulator-1", "test-compiler-1",
        "input-sha256-fixture", "runtime-sha256-fixture", "run-pdf-regression",
        "Potential across device position", "Input authority records are unavailable",
    ):
        assert phrase in text, f"scientific PDF lost {phrase!r}"
    assert "PRIVATE CHAT MUST NOT APPEAR" not in text
    assert "Export PDF" not in text
    assert any("/Contents" in page for page in reader.pages)
