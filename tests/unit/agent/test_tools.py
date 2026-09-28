from pathlib import Path
from types import SimpleNamespace

import yaml

from tcad_agent.agent.tools import (
    DomainTools,
    TcadDomainAction,
    TcadDomainExecutor,
    TcadDomainTool,
    build_tools,
)
from tcad_agent.knowledge.models import Passage, WebEvidenceRecord, WebSearchResult
from tcad_agent.knowledge.retrieve import KnowledgeIndex

ROOT = Path(__file__).parents[3]


def valid_spec_payload() -> dict:
    return yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())


def test_run_tool_requires_validated_plan(tmp_path: Path) -> None:
    tools = build_tools(tmp_path)
    response = tools.run_experiment({"spec_path": "spec.yaml", "backend": "devsim"})
    assert response.status == "refused"
    assert response.code == "approval_required"


def test_sentaurus_compiles_without_configured_remote(tmp_path: Path) -> None:
    response = build_tools(tmp_path).compile_experiment(
        valid_spec_payload(), backend="sentaurus"
    )
    assert response.status == "ok"
    assert response.code == "compiled"
    assert response.data["job"]["backend"] == "sentaurus"


def test_tcad_executor_returns_llm_visible_refusal_for_missing_payload(
    tmp_path: Path,
) -> None:
    observation = TcadDomainExecutor(tmp_path)(
        TcadDomainAction(operation="validate_spec")
    )

    assert observation.status == "refused"
    assert observation.code == "invalid_spec"
    assert observation.content
    assert '"code": "invalid_spec"' in observation.text


def test_search_knowledge_uses_configured_product_index_not_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    index_path = tmp_path / "product" / "knowledge.sqlite3"
    KnowledgeIndex.build(
        index_path,
        [
            Passage.create(
                id="manual:contact",
                source_id="manual",
                title="DEVSIM manual",
                url="https://devsim.net/",
                license="CC-BY-ND-4.0",
                access="public",
                trust="primary",
                backend="devsim",
                version="2.9",
                reviewed=True,
                content="The contact_equation command assembles a boundary equation.",
            )
        ],
    )
    monkeypatch.setenv("TCAD_KNOWLEDGE_INDEX", str(index_path))

    response = build_tools(tmp_path / "empty-research-repository").search_knowledge(
        "contact equation", {"backend": "devsim"}
    )

    assert response.status == "ok"
    assert response.data["hits"]
    assert response.data["hits"][0]["citation"]["source_id"] == "manual"


class StubWebResearch:
    def search(
        self, query: str, preferred_domains: tuple[str, ...], limit: int
    ) -> tuple[WebSearchResult, ...]:
        assert query == "DEVSIM contact equation"
        assert preferred_domains == ("devsim.org",)
        assert limit == 3
        return (
            WebSearchResult(
                query=query,
                title="DEVSIM documentation",
                url="https://devsim.org/docs",
                snippet="Official command documentation",
                authority="primary",
            ),
        )

    def fetch_source(
        self,
        url: str,
        *,
        query: str = "",
        backend: str | None = None,
        version: str | None = None,
    ) -> WebEvidenceRecord:
        assert url == "https://devsim.org/docs"
        return WebEvidenceRecord.create(
            title="DEVSIM documentation",
            url=url,
            content_type="text/html",
            content="The solve command executes the configured equations.",
            query=query,
            authority="primary",
            backend=backend,
            version=version,
            from_cache=False,
        )


def test_tcad_tools_expose_structured_web_search_and_source_fetch(
    tmp_path: Path,
) -> None:
    tools = DomainTools(tmp_path, web_research=StubWebResearch())

    searched = tools.search_web(
        "DEVSIM contact equation", ("devsim.org",), limit=3
    )
    fetched = tools.fetch_source(
        "https://devsim.org/docs",
        query="DEVSIM solve command",
        backend="devsim",
        version="2.9.1",
    )

    assert searched.status == "ok"
    assert searched.data["results"][0]["authority"] == "primary"
    assert fetched.status == "ok"
    assert fetched.data["evidence"]["backend"] == "devsim"
    assert fetched.data["evidence"]["content_hash"]
    assert fetched.data["evidence"]["untrusted_content"] is True


def test_tcad_domain_tool_declares_external_research_capability(
    tmp_path: Path,
) -> None:
    tool = TcadDomainTool.create(
        SimpleNamespace(workspace=SimpleNamespace(working_dir=str(tmp_path)))
    )[0]

    assert tool.annotations.openWorldHint is True
