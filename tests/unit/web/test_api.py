import inspect
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from tcad_agent.web.app import create_app


class ButtonTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: dict[str, str] = {}
        self.elements: dict[str, str] = {}
        self._current_button: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.elements[attributes["id"]] = tag
        if tag == "button" and attributes.get("id"):
            self._current_button = attributes["id"]

    def handle_data(self, data: str) -> None:
        if self._current_button is not None:
            self.buttons[self._current_button] = (
                self.buttons.get(self._current_button, "") + data
            ).strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "button":
            self._current_button = None


def client(tmp_path: Path) -> TestClient:
    del tmp_path
    return TestClient(create_app())


def test_root_and_health_are_local_researcher_entrypoints(tmp_path: Path) -> None:
    web = client(tmp_path)
    health = web.get("/health").json()
    assert health["status"] == "ok"
    assert len(health["runtime_fingerprint"]) == 16
    page = web.get("/")
    assert page.status_code == 200
    assert "Agent Kronig workspace" in page.text


def test_root_serves_workspace_ide_shell(tmp_path: Path) -> None:
    page = client(tmp_path).get("/")
    parser = ButtonTextParser()
    parser.feed(page.text)

    assert parser.elements["workspace-browser"] == "aside"
    assert parser.elements["repository-tree"] == "div"
    assert parser.elements["workspace-main"] == "main"
    assert "workspace-tabs" not in parser.elements
    assert parser.elements["workspace-context-name"] == "strong"
    assert parser.elements["workspace-context-state"] == "span"
    assert parser.elements["file-viewer"] == "section"
    assert parser.elements["file-viewer-body"] == "div"
    assert parser.elements["file-editor"] == "textarea"
    assert parser.elements["file-viewer-download"] == "a"
    assert parser.elements["agent-panel"] == "aside"
    assert "conversation-select" not in parser.elements
    assert "create-conversation" not in parser.elements
    assert "conversation-dialog" not in parser.elements
    assert "conversation-title-input" not in parser.elements
    assert parser.elements["session-state"] == "strong"
    assert parser.elements["session-messages"] == "div"
    assert "Describe the task for this repository." in page.text
    assert "agent-progress" not in parser.elements
    assert parser.elements["agent-activity"] == "div"
    assert parser.elements["open-workspace"] == "button"
    assert parser.elements["browse-workspace"] == "button"
    assert parser.elements["refresh-session"] == "button"
    assert parser.elements["toggle-agent-panel"] == "button"
    assert parser.elements["close-agent-panel"] == "button"
    assert parser.elements["file-viewer-edit"] == "button"
    assert parser.elements["file-viewer-save"] == "button"
    assert parser.elements["file-viewer-cancel"] == "button"
    assert 'href="/simulate"' not in page.text
    assert "No workspace open" not in page.text
    assert "Start a repository conversation" not in page.text
    assert "Select a conversation" not in page.text
    assert "New conversation" not in page.text


def test_conversation_page_route_is_removed(tmp_path: Path) -> None:
    response = client(tmp_path).get(f"/workspaces/{uuid4()}/conversations/{uuid4()}")

    assert response.status_code == 404


def test_workspace_header_separates_product_and_company_branding(tmp_path: Path) -> None:
    page = client(tmp_path).get("/").text

    product_wordmark = '<strong class="product-wordmark" aria-label="Agent Kronig">'
    agent_name = '<span class="product-agent" aria-hidden="true">Agent</span>'
    kronig_name = '<span class="product-kronig" aria-hidden="true">Kronig</span>'
    company = '<span class="company-lockup" aria-label="NovAtom Labs">'
    atom = (
        '<img class="company-atom" src="/static/novatom-atom-mark.svg" alt="" aria-hidden="true">'
    )
    assert product_wordmark in page
    assert agent_name in page
    assert kronig_name in page
    assert company in page
    assert atom in page
    assert '<span class="company-nov">Nov</span>' in page
    assert '<span class="company-atom-text">Atom</span>' in page
    assert '<span class="company-labs">Labs</span>' in page
    assert page.index(agent_name) < page.index(kronig_name)
    assert page.index(product_wordmark) < page.index('id="workspace-status"') < page.index(company)
    assert "Research workspace" not in page
    assert "Local runtime" not in page
    assert 'id="run-controls" class="run-controls" hidden' in page
    assert 'aria-valuenow="420"' in page
    assert 'src="/static/desktop-bridge.js?v=20260925-1"' in page
    assert page.index("desktop-bridge.js") < page.index("ide.js")


def test_typography_assets_are_self_hosted_and_served(tmp_path: Path) -> None:
    web = client(tmp_path)
    theme = web.get("/static/theme.css")

    assert theme.status_code == 200
    assert '--font-sans: "IBM Plex Sans"' in theme.text
    assert '--font-mono: "IBM Plex Mono"' in theme.text
    assert "https://" not in theme.text

    font_paths = (
        "/static/fonts/ibm-plex-sans-roman.woff2",
        "/static/fonts/ibm-plex-sans-italic.woff2",
        "/static/fonts/ibm-plex-mono-roman.woff2",
        "/static/fonts/ibm-plex-mono-italic.woff2",
    )
    for font_path in font_paths:
        response = web.get(font_path)
        assert response.status_code == 200
        assert response.content.startswith(b"wOF2")


def test_file_viewer_uses_one_compact_toolbar(tmp_path: Path) -> None:
    page = client(tmp_path).get("/").text

    assert 'class="file-viewer-utilities"' in page
    assert 'id="file-viewer-meta" class="file-viewer-meta" hidden' in page
    assert 'id="file-viewer-kind"' not in page
    assert page.index('id="file-viewer-edit"') < page.index('id="file-viewer-refresh"')
    assert page.index('id="file-viewer-download"') < page.index('id="file-viewer-close"')


def test_obsolete_guided_workflow_routes_are_absent(tmp_path: Path) -> None:
    web = client(tmp_path)
    simulation = web.get("/simulate", follow_redirects=False)
    request_stage = web.get(f"/requests/{uuid4()}/results", follow_redirects=False)
    request_api = web.post("/api/requests", json={"prompt": "simulate", "backend": "devsim"})

    assert simulation.status_code == 404
    assert request_stage.status_code == 404
    assert request_api.status_code == 404


def test_application_has_no_obsolete_control_dependency() -> None:
    assert "control" not in inspect.signature(create_app).parameters


def test_workspace_uses_scientific_theme(tmp_path: Path) -> None:
    web = client(tmp_path)
    workspace_page = web.get("/")
    theme = web.get("/static/theme.css?v=20260928-1")

    assert 'href="/static/theme.css?v=20260928-1"' in workspace_page.text
    assert theme.status_code == 200
    assert theme.headers["content-type"].startswith("text/css")
