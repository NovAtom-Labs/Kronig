from __future__ import annotations

import os
from pathlib import Path

import pytest

from tcad_agent.evaluations.scientific_cases import ScientificIntakeSuite
from tcad_agent.prompting.service import build_default_prompt_preparation

PROJECT_ROOT = Path(__file__).parents[2]
INTAKE_SUITE = PROJECT_ROOT / "evaluations/scientific/intake_cases.yaml"


def _require_live(pytestconfig: pytest.Config) -> None:
    if not pytestconfig.getoption("--run-live-bedrock"):
        pytest.skip("pass --run-live-bedrock to call the configured Bedrock model")
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        pytest.skip("AWS_BEARER_TOKEN_BEDROCK is not configured")


@pytest.mark.live_bedrock
@pytest.mark.parametrize(
    ("case_id", "expected_status"),
    (
        ("exact-bidirectional-junction", "ready"),
        ("ambiguous-oxide-thickness", "clarification"),
        ("unsupported-contact-and-physics", "blocked"),
        ("generic-layered-voltage-study", "ready"),
        ("supported-oxide-charge-sweep", "ready"),
        ("supported-fermi-junction", "ready"),
        ("supported-schottky-sweep", "ready"),
        ("supported-surface-physics", "ready"),
        ("supported-spatial-temperature", "clarification"),
        ("supported-current-components", "ready"),
    ),
)
def test_live_preparation_respects_expanded_devsim_scope(
    pytestconfig: pytest.Config,
    tmp_path: Path,
    case_id: str,
    expected_status: str,
) -> None:
    _require_live(pytestconfig)
    suite = ScientificIntakeSuite.from_file(INTAKE_SUITE)
    case = suite.require_case(case_id)
    service = build_default_prompt_preparation(PROJECT_ROOT)
    repository = tmp_path / case_id
    repository.mkdir()

    outcome = service.prepare(
        root=repository,
        original_prompt=suite.read_prompt(case_id),
        answers=(),
    )

    assert outcome.decision.status == expected_status, outcome.decision.model_dump_json(
        indent=2
    )
    assert len(outcome.decision.questions) <= case.maximum_questions
    if expected_status == "ready":
        assert outcome.compiled_request is not None
        assert not outcome.decision.unresolved_critical
    else:
        assert outcome.compiled_request is None
    if expected_status == "clarification":
        unresolved = " ".join(
            (
                *outcome.decision.unresolved_critical,
                *(question.field_path for question in outcome.decision.questions),
                *(question.prompt for question in outcome.decision.questions),
            )
        ).lower()
        assert any(
            concept.replace("_", " ") in unresolved
            for concept in case.required_concepts
        ), outcome.decision.model_dump_json(indent=2)
    if expected_status == "blocked":
        explanation = " ".join(
            (outcome.decision.summary, *outcome.decision.warnings)
        ).lower()
        assert "unsupported" in explanation or "cannot" in explanation
