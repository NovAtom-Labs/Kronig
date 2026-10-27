import pytest


@pytest.fixture(autouse=True)
def instant_model_retries(monkeypatch):
    """Retrying a failed model call must not slow the unit tests down."""
    monkeypatch.setattr("tcad_agent.prompting.gateway.MODEL_RETRY_SECONDS", 0.0)