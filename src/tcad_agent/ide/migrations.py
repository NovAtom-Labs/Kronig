"""Idempotent SQLite schema migrations for the local Agent Kronig store."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

LATEST_SCHEMA_VERSION = 3


def _record_migration(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, datetime.now(UTC).isoformat()),
    )
    connection.execute(f"PRAGMA user_version = {version}")


def _migration_1(connection: sqlite3.Connection) -> None:
    """Introduce an auditable migration ledger without rewriting user data."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _migration_2(connection: sqlite3.Connection) -> None:
    """Upgrade approvals created before permission categories were persisted."""

    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(approval_requests)").fetchall()
    }
    if columns and "permission_category" not in columns:
        connection.execute(
            """
            ALTER TABLE approval_requests
            ADD COLUMN permission_category TEXT NOT NULL
            DEFAULT 'unrecognized_action'
            """
        )


def _migration_3(connection: sqlite3.Connection) -> None:
    """Persist component-level scientific run outcomes."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS run_outcomes (
            run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
            execution_state TEXT NOT NULL,
            validation_state TEXT NOT NULL,
            deliverable_state TEXT NOT NULL,
            report_state TEXT NOT NULL,
            overall_state TEXT NOT NULL,
            failed_check_count INTEGER NOT NULL,
            unmet_deliverables_json TEXT NOT NULL,
            project_root TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


_MIGRATIONS: tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...] = (
    (1, _migration_1),
    (2, _migration_2),
    (3, _migration_3),
)


def migrate_schema(connection: sqlite3.Connection) -> None:
    """Apply every missing migration once inside the caller's transaction."""

    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current > LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            "The local Agent Kronig database was created by a newer application version."
        )
    for version, migration in _MIGRATIONS:
        if version <= current:
            continue
        migration(connection)
        _record_migration(connection, version)
        current = version
