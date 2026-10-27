import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tcad_agent.capabilities import active
from tcad_agent.runners.ssh_check import CheckResult
from tcad_agent.web import simulator_routes


@pytest.fixture
def client(monkeypatch):
    for name in (
        "TCAD_BACKEND",
        "TCAD_SENTAURUS_RUNNER",
        "TCAD_HPSC_HOST",
        "TCAD_HPSC_USER",
        "TCAD_SENTAURUS_VERSION",
    ):
        monkeypatch.delenv(name, raising=False)
    active.set_preferred_backend(None)
    app = FastAPI()
    app.include_router(simulator_routes.build_simulator_router())
    yield TestClient(app)
    active.set_preferred_backend(None)


def test_lists_both_simulators_and_what_sentaurus_still_needs(client) -> None:
    state = client.get("/api/simulators").json()

    assert state["default"] == "devsim" and state["selected"] is None
    devsim, sentaurus = state["backends"]
    assert devsim["ready"] is True and devsim["missing_settings"] == []
    assert sentaurus["ready"] is False
    assert sentaurus["missing_settings"] == [
        "TCAD_SENTAURUS_RUNNER",
        "TCAD_HPSC_HOST",
        "TCAD_HPSC_USER",
        "TCAD_SENTAURUS_VERSION",
    ]


def test_sentaurus_is_ready_once_its_settings_are_present(client, monkeypatch) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_RUNNER", "ssh")
    monkeypatch.setenv("TCAD_HPSC_HOST", "10.0.0.5")
    monkeypatch.setenv("TCAD_HPSC_USER", "alice")
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", "O-2018.06-SP2")

    sentaurus = client.get("/api/simulators").json()["backends"][1]

    assert sentaurus["ready"] is True and sentaurus["missing_settings"] == []


def test_the_chosen_simulator_outranks_the_environment_default_but_not_the_request_text(
    client, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_BACKEND", "devsim")

    chosen = client.put("/api/simulators/default", json={"backend": "sentaurus"}).json()

    assert chosen["selected"] == "sentaurus" and chosen["default"] == "sentaurus"
    assert active.resolve_backend("simulate a diode") == "sentaurus"
    assert active.resolve_backend("simulate a diode with DEVSIM") == "devsim"
    cleared = client.put("/api/simulators/default", json={"backend": None}).json()
    assert cleared["selected"] is None and active.resolve_backend("a diode") == "devsim"


def test_an_unknown_simulator_is_refused(client) -> None:
    assert client.put("/api/simulators/default", json={"backend": "spice"}).status_code == 422
    assert client.put("/api/simulators/default", json={"extra": 1}).status_code == 422


def test_the_connection_check_reports_each_step_and_passes_the_trust_choice(
    client, monkeypatch
) -> None:
    seen = {}

    def fake(*, trust_host, deep, emit=None):
        seen.update(trust_host=trust_host, deep=deep)
        return [CheckResult("settings", True, "ok"), CheckResult("network", False, "down", "vpn")]

    monkeypatch.setattr(simulator_routes, "run_checks", fake)

    outcome = client.post("/api/simulators/sentaurus/check", json={"trust_host": True}).json()

    assert seen == {"trust_host": True, "deep": False}
    assert outcome["ok"] is False
    assert outcome["checks"][1] == {"name": "network", "ok": False, "detail": "down", "fix": "vpn"}
