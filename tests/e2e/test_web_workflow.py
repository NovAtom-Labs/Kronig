import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
import yaml

from tcad_agent.control.service import ControlService
from tcad_agent.control.store import SqliteRequestStore
from tcad_agent.model_gateway.base import AgentProposal, ScriptedModelGateway
from tcad_agent.web.app import create_app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_http_workflow_runs_devsim_once_and_serves_artifacts(tmp_path: Path) -> None:
    spec = yaml.safe_load(Path("examples/pn-junction.yaml").read_text())
    control = ControlService(
        store=SqliteRequestStore(tmp_path / "requests.sqlite3"),
        gateway=ScriptedModelGateway((AgentProposal(kind="spec", spec=spec),)),
        workspace=tmp_path / "workspace",
    )
    app = create_app(control)
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{base_url}/health", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.02)
        created = httpx.post(
            f"{base_url}/api/requests",
            json={"prompt": "simulate complete reference", "backend": "devsim"},
            timeout=5,
        )
        assert created.status_code == 201, created.text
        request = created.json()
        approved = httpx.post(
            f"{base_url}/api/requests/{request['id']}/approve",
            json={"plan_digest": request["plan_digest"]},
            timeout=5,
        )
        assert approved.status_code == 200, approved.text
        first = httpx.post(
            f"{base_url}/api/requests/{request['id']}/run", timeout=20
        )
        second = httpx.post(
            f"{base_url}/api/requests/{request['id']}/run", timeout=20
        )
        assert first.json()["state"] == "completed"
        assert second.json()["state"] == "completed"
        results = httpx.get(
            f"{base_url}/api/requests/{request['id']}/results",
            timeout=5,
        )
        assert results.status_code == 200
        results_payload = results.json()
        assert results_payload["result"]["status"] == "completed"
        assert results_payload["result"]["fields"]["potential"]["unit"] == "V"
        assert results_payload["validation"]["overall"] == "passed"
        assert results_payload["experiment"]["name"] == "pn-junction-reference"
        report = httpx.get(
            f"{base_url}/api/requests/{request['id']}/artifacts/report.md",
            timeout=5,
        )
        assert report.status_code == 200
        assert "TCAD Evidence Summary" in report.text
        fields = httpx.get(
            f"{base_url}/api/requests/{request['id']}/artifacts/results/fields.csv",
            timeout=5,
        )
        plots = httpx.get(
            f"{base_url}/api/requests/{request['id']}/artifacts/results/field-plots.svg",
            timeout=5,
        )
        assert fields.status_code == 200
        assert "field,position_m,value,unit" in fields.text
        assert plots.status_code == 200
        assert "<svg" in plots.text
        events = httpx.get(
            f"{base_url}/api/requests/{request['id']}/events", timeout=5
        )
        assert events.status_code == 200
        assert "event: stage" in events.text
        traversal = httpx.get(
            f"{base_url}/api/requests/{request['id']}/artifacts/%2E%2E%2Fexperiment.json",
            timeout=5,
        )
        assert traversal.status_code in {400, 404}
        assert len(tuple((tmp_path / "workspace" / "bundles").glob("*"))) == 1
    finally:
        server.should_exit = True
        thread.join(timeout=5)
