import sqlite3

from tcad_agent.web.errors import ErrorCategory, map_exception


def test_lifecycle_database_failure_is_not_misreported_as_provider_failure() -> None:
    mapped = map_exception(
        sqlite3.IntegrityError("FOREIGN KEY constraint failed"),
        operation="desktop_shutdown",
    )

    assert mapped.envelope.category is ErrorCategory.LIFECYCLE
    assert mapped.envelope.code == "lifecycle_persistence_conflict"
    assert "credential" not in mapped.envelope.message.lower()
    assert mapped.envelope.recovery_actions
    assert mapped.status_code == 409


def test_error_contract_redacts_secret_shaped_values() -> None:
    mapped = map_exception(
        RuntimeError("api_key=super-secret-value"),
        operation="run_request",
    )

    serialized = mapped.envelope.model_dump_json()
    assert "super-secret-value" not in serialized
    assert mapped.envelope.diagnostic_id
