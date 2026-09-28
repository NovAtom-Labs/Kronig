from pathlib import Path

from fastapi.testclient import TestClient

from tcad_agent.desktop.auth import DesktopAuth
from tcad_agent.web.app import create_app


def desktop_client(tmp_path: Path, auth: DesktopAuth) -> TestClient:
    return TestClient(
        create_app(desktop_auth=auth),
        follow_redirects=False,
        raise_server_exceptions=True,
    )


def test_desktop_session_requires_one_use_bootstrap_token(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path / "runtime"))
    token = "desktop-token-" + "a" * 32
    auth = DesktopAuth(token)
    client = desktop_client(tmp_path, auth)

    assert client.get("/health").status_code == 200
    assert client.get("/api/desktop/status").json() == {"active": False}
    assert client.get("/").status_code == 401
    assert client.get("/static/ide.css").status_code == 401

    invalid = client.get("/desktop/bootstrap?token=short")
    assert invalid.status_code == 403

    bootstrap = client.get(f"/desktop/bootstrap?token={token}")
    assert bootstrap.status_code == 303
    assert bootstrap.headers["location"] == "/"
    cookie = bootstrap.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert client.get("/").status_code == 200

    second_client = desktop_client(tmp_path, auth)
    reused = second_client.get(f"/desktop/bootstrap?token={token}")
    assert reused.status_code == 403


def test_desktop_auth_rejects_empty_and_malformed_tokens(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path / "runtime"))
    auth = DesktopAuth("b" * 43)
    client = desktop_client(tmp_path, auth)

    assert client.get("/desktop/bootstrap").status_code == 403
    assert client.get("/desktop/bootstrap?token=%00").status_code == 403


def test_desktop_shutdown_handshake_closes_mutating_api(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path / "runtime"))
    token = "desktop-token-" + "c" * 32
    auth = DesktopAuth(token)
    client = desktop_client(tmp_path, auth)
    assert client.get(f"/desktop/bootstrap?token={token}").status_code == 303

    prepared = client.post(
        "/api/desktop/prepare-shutdown",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert prepared.status_code == 200
    assert prepared.json() == {"ready": True}
    blocked = client.post(
        "/api/workspaces",
        json={"path": str(tmp_path)},
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "desktop_shutdown_committed"


def test_desktop_shutdown_handshake_requires_control_token(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_WORKSPACE", str(tmp_path / "runtime"))
    token = "desktop-token-" + "d" * 32
    client = desktop_client(tmp_path, DesktopAuth(token))

    response = client.post("/api/desktop/prepare-shutdown")

    assert response.status_code == 403
