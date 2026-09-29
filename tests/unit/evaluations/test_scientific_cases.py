from pathlib import Path

import pytest
from pydantic import ValidationError

from tcad_agent.evaluations.scientific_cases import (
    ScientificEvaluationCase,
    ScientificEvaluationSuite,
    ScientificIntakeSuite,
    score_scientific_case,
)
from tcad_agent.ide.results import WorkspaceResultReader
from tcad_agent.knowledge.models import (
    Citation,
    SearchHit,
    WebEvidenceRecord,
)

ROOT = Path(__file__).parents[3]
SUITE = ROOT / "evaluations" / "scientific" / "cases.yaml"
INTAKE_SUITE = ROOT / "evaluations" / "scientific" / "intake_cases.yaml"


def test_scientific_suite_contains_varied_researcher_prompts_and_viewer_contracts() -> None:
    suite = ScientificEvaluationSuite.from_file(SUITE)

    assert len(suite.cases) >= 3
    assert {case.study_kind for case in suite.cases} >= {"equilibrium", "dc"}
    assert {case.region_count for case in suite.cases} >= {2, 3, 4}
    assert any(case.web_research_required for case in suite.cases)
    assert any(not case.web_research_required for case in suite.cases)
    for case in suite.cases:
        prompt = suite.read_prompt(case.id)
        assert len(prompt.split()) >= 25
        assert "ExperimentSpec" not in prompt
        assert "canonical.json" not in prompt
        assert "adapter" not in prompt.lower()
        assert case.expected_fields
        assert case.minimum_graphable_fields >= 2
        assert suite.spec_path(case.id).is_file()


def test_scientific_suite_rejects_web_case_without_research_contract(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(
        """
schema_version: "1.0"
purpose: invalid fixture
cases:
  - id: missing-web-contract
    title: Invalid case
    prompt_file: prompt.md
    spec_file: spec.yaml
    backend: devsim
    study_kind: equilibrium
    region_count: 2
    web_research_required: true
    expected_fields: [potential, electric_field]
    minimum_graphable_fields: 2
""".strip()
    )

    with pytest.raises(ValidationError, match="web_query"):
        ScientificEvaluationSuite.from_file(path)


def test_scientific_suite_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    path = tmp_path / "cases.yaml"
    path.write_text(
        """
schema_version: "1.0"
purpose: duplicate fixture
cases:
  - &case
    id: duplicate
    title: First
    prompt_file: prompt.md
    spec_file: spec.yaml
    backend: devsim
    study_kind: equilibrium
    region_count: 2
    web_research_required: false
    expected_fields: [potential, electric_field]
    minimum_graphable_fields: 2
  - <<: *case
    title: Second
""".strip()
    )

    with pytest.raises(ValidationError, match="unique"):
        ScientificEvaluationSuite.from_file(path)


def test_intake_suite_covers_complete_ambiguous_unsupported_and_varied_requests() -> None:
    suite = ScientificIntakeSuite.from_file(INTAKE_SUITE)

    assert len(suite.cases) >= 5
    assert {case.expected_status for case in suite.cases} >= {
        "ready",
        "clarification",
        "blocked",
    }
    assert any(case.expected_study == "dc_points" for case in suite.cases)
    assert any(case.expected_study == "dc" for case in suite.cases)
    assert any("unit" in case.required_concepts for case in suite.cases)
    assert any("unsupported_physics" in case.required_concepts for case in suite.cases)
    for case in suite.cases:
        prompt = suite.read_prompt(case.id)
        assert len(prompt.split()) >= 20
        assert "ExperimentSpec" not in prompt
        assert "canonical" not in prompt.lower()
        assert "adapter" not in prompt.lower()
        assert case.maximum_questions <= 7


def test_scientific_score_requires_evidence_validation_and_viewer_ready_fields(
    tmp_path: Path,
    result_bundle_factory,
) -> None:
    result_bundle_factory(tmp_path)
    view = WorkspaceResultReader().read(
        tmp_path, "run-0001/results/canonical.json"
    )
    case = ScientificEvaluationCase(
        id="scored-case",
        title="Scored case",
        prompt_file="prompt.md",
        spec_file="spec.yaml",
        backend="devsim",
        study_kind="dc",
        region_count=2,
        web_research_required=True,
        web_query="DEVSIM convergence controls",
        preferred_domains=("devsim.org",),
        required_local_source_ids=("devsim-manual",),
        expected_fields=(
            "potential",
            "electric_field",
            "electron_density",
            "hole_density",
        ),
        required_validation_checks=(
            "all-points-converged",
            "terminal-current-conservation",
            "requested-observables-present",
        ),
        minimum_graphable_fields=4,
    )
    local_hit = SearchHit(
        id="manual:solve",
        content="The solve command controls nonlinear convergence.",
        backend="devsim",
        score=1.0,
        reviewed=True,
        citation=Citation(
            source_id="devsim-manual",
            title="DEVSIM manual",
            url="https://devsim.org/docs",
            version="2.9.1",
            content_hash="a" * 64,
        ),
    )
    web_evidence = WebEvidenceRecord.create(
        title="DEVSIM documentation",
        url="https://devsim.org/docs/solve",
        content_type="text/html",
        content="Current public solve command documentation.",
        query="DEVSIM convergence controls",
        authority="primary",
        backend="devsim",
        version="2.9.1",
        from_cache=False,
    )

    score = score_scientific_case(case, view, (local_hit,), (web_evidence,))

    assert score.passed is True
    assert score.score == 100
    assert all(score.checks.values())


def test_scientific_score_fails_when_required_web_research_is_missing(
    tmp_path: Path,
    result_bundle_factory,
) -> None:
    result_bundle_factory(tmp_path)
    view = WorkspaceResultReader().read(
        tmp_path, "run-0001/results/canonical.json"
    )
    case = ScientificEvaluationCase(
        id="missing-research",
        title="Missing research",
        prompt_file="prompt.md",
        spec_file="spec.yaml",
        backend="devsim",
        study_kind="dc",
        region_count=2,
        web_research_required=True,
        web_query="DEVSIM convergence controls",
        preferred_domains=("devsim.org",),
        expected_fields=("potential",),
        minimum_graphable_fields=1,
    )

    score = score_scientific_case(case, view, (), ())

    assert score.passed is False
    assert score.checks["web-evidence"] is False
