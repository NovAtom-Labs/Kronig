from pathlib import Path

import httpx
import pytest
import yaml

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.evaluations.scientific_cases import (
    ScientificEvaluationSuite,
    score_scientific_case,
)
from tcad_agent.experiments.service import ExperimentEngine
from tcad_agent.ide.results import WorkspaceResultReader
from tcad_agent.knowledge.models import WebEvidenceRecord
from tcad_agent.knowledge.retrieve import KnowledgeIndex
from tcad_agent.knowledge.web import ScientificWebResearch
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]
SUITE = ScientificEvaluationSuite.from_file(ROOT / "evaluations" / "scientific" / "cases.yaml")
KNOWLEDGE_INDEX = ROOT / "knowledge-sources" / "index" / "knowledge.sqlite3"


def _web_evidence(case_id: str, tmp_path: Path) -> tuple[WebEvidenceRecord, ...]:
    case = SUITE.require_case(case_id)
    if not case.web_research_required:
        return ()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "html.duckduckgo.com":
            return httpx.Response(
                200,
                text=(
                    '<a class="result__a" href="https://devsim.org/docs/solve">'
                    "DEVSIM solve command</a>"
                    '<a class="result__snippet">Current nonlinear controls.</a>'
                ),
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=(
                "<html><head><title>DEVSIM solve command</title></head>"
                "<body><p>The solve command accepts relative_error, "
                "absolute_error, and maximum_iterations controls.</p></body></html>"
            ),
            request=request,
        )

    research = ScientificWebResearch(
        cache_root=tmp_path / "research-cache",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        resolver=lambda _host: ("93.184.216.34",),
    )
    results = research.search(
        case.web_query or "",
        preferred_domains=case.preferred_domains,
        limit=3,
    )
    assert results and results[0].authority == "primary"
    return (
        research.fetch_source(
            results[0].url,
            query=case.web_query or "",
            backend=case.backend,
            version="2.9.1",
        ),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "case_id",
    ["two-region-equilibrium", "three-region-dc", "four-region-equilibrium"],
)
def test_researcher_prompt_reaches_verified_interactive_result_contract(
    case_id: str,
    tmp_path: Path,
) -> None:
    case = SUITE.require_case(case_id)
    prompt = SUITE.read_prompt(case_id)
    spec_payload = yaml.safe_load(SUITE.spec_path(case_id).read_text())
    engine = ExperimentEngine()
    prepared = engine.prepare(ExperimentSpec.model_validate(spec_payload), case.backend)
    completed = engine.execute(
        prepared,
        approved_plan_digest=prepared.plan_digest,
        output_root=tmp_path / "runs",
        budget=RunBudget(seconds=120),
    )

    assert completed.state == "completed"
    bundle = completed.root
    view = WorkspaceResultReader().read(
        bundle.parent,
        f"{bundle.name}/results/canonical.json",
    )
    index = KnowledgeIndex(KNOWLEDGE_INDEX)
    local_hits = (
        *index.search(prompt, {"backend": case.backend}, limit=12),
        *index.search(prompt, {"backend": "portable"}, limit=12),
    )
    score = score_scientific_case(
        case,
        view,
        tuple(local_hits),
        _web_evidence(case_id, tmp_path),
    )

    assert score.passed, score.model_dump()
    assert score.score == 100
