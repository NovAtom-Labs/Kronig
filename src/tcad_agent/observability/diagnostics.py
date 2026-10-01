"""Size-bounded local diagnostic persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET = re.compile(
    r"(?i)\b(token|password|secret|api[-_]?key|authorization)\s*[:=]\s*[^\s,;]+"
)
_DIAGNOSTIC_ID = re.compile(r"^diag-[0-9a-f]{16}$")


def redact_diagnostic(value: object) -> str:
    return _SECRET.sub(r"\1=[REDACTED]", str(value))


class DiagnosticStore:
    def __init__(
        self,
        data_root: Path,
        *,
        maximum_files: int = 100,
        maximum_bytes: int = 32 * 1024,
    ) -> None:
        self.root = data_root.resolve() / "diagnostics"
        self.maximum_files = max(1, maximum_files)
        self.maximum_bytes = max(256, maximum_bytes)

    def write(
        self,
        *,
        diagnostic_id: str,
        category: str,
        operation: str,
        detail: object,
    ) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        safe_detail = redact_diagnostic(detail)
        payload = {
            "diagnostic_id": diagnostic_id,
            "category": category,
            "operation": operation,
            "created_at": datetime.now(UTC).isoformat(),
            "detail": safe_detail,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        if len(encoded) > self.maximum_bytes:
            suffix = "...[clipped]"
            low, high = 0, len(safe_detail)
            while low < high:
                midpoint = (low + high + 1) // 2
                payload["detail"] = safe_detail[:midpoint] + suffix
                encoded_candidate = json.dumps(
                    payload, sort_keys=True, ensure_ascii=False
                ).encode("utf-8")
                if len(encoded_candidate) <= self.maximum_bytes:
                    low = midpoint
                else:
                    high = midpoint - 1
            payload["detail"] = safe_detail[:low] + suffix
            encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode(
                "utf-8"
            )
        destination = self.root / f"{diagnostic_id}.json"
        descriptor, temporary = tempfile.mkstemp(dir=self.root, prefix=".diag-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            candidate = Path(temporary)
            if candidate.exists():
                candidate.unlink()
        self._prune()
        return destination

    def read(self, diagnostic_id: str) -> dict[str, Any]:
        """Return one already-redacted record without permitting path traversal."""

        if not _DIAGNOSTIC_ID.fullmatch(diagnostic_id):
            raise ValueError("diagnostic identifier is invalid")
        target = self.root / f"{diagnostic_id}.json"
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("diagnostic record is unreadable") from exc
        if not isinstance(payload, dict) or payload.get("diagnostic_id") != diagnostic_id:
            raise ValueError("diagnostic record is invalid")
        return payload

    def _prune(self) -> None:
        files = sorted(
            (path for path in self.root.glob("*.json") if path.is_file()),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for stale in files[self.maximum_files :]:
            stale.unlink(missing_ok=True)
