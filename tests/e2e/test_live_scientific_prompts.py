"""Opt-in evaluations against the configured Bedrock model.

These tests intentionally use natural researcher language. They verify that the live
model drafts a portable contract when intent is complete and asks a useful question
when scientifically essential input is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.control.models import ResearchRequest
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.evaluations.scientific_cases import ScientificEvaluationSuite
from tcad_agent.model_gateway.base import AgentContextPacket
from tcad_agent.model_gateway.openhands import OpenHandsBedrockGateway

ROOT = Path(__file__).parents[2]
SUITE = ScientificEvaluationSuite.from_file(
    ROOT / "evaluations" / "scientific" / "cases.yaml"
)


def _require_live_bedrock(pytestconfig: pytest.Config) -> None:
    if not pytestconfig.getoption("--run-live-bedrock"):
        pytest.skip("pass --run-live-bedrock to call the configured Bedrock model")
    if not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        pytest.skip("AWS_BEARER_TOKEN_BEDROCK is not configured")


def _context() -> AgentContextPacket:
    manifest = CapabilityManifest.from_backend("devsim")
    return AgentContextPacket(
        capabilities=manifest.model_dump(mode="json"),
        procedures=(
            "Preserve researcher intent in ExperimentSpec.",
            "Choose a defensible mesh from the stated geometry.",
            "Ask only for scientifically essential missing inputs.",
        ),
    )


@pytest.mark.live_bedrock
def test_live_model_translates_complete_researcher_prompt_to_supported_contract(
    pytestconfig: pytest.Config,
) -> None:
    _require_live_bedrock(pytestconfig)
    case = SUITE.require_case("two-region-equilibrium")

    proposal = OpenHandsBedrockGateway.from_environment().propose(
        ResearchRequest(prompt=SUITE.read_prompt(case.id)),
        _context(),
    )

    assert proposal.kind == "spec", proposal.model_dump(mode="json")
    spec = ExperimentSpec.model_validate(proposal.spec)
    assert len(spec.regions) == case.region_count
    assert spec.study.kind == case.study_kind
    assert spec.physics.temperature.to("K") == pytest.approx(300.0)
    assert {str(value) for value in spec.observables}.issuperset(
        set(case.expected_fields)
    )
    decision = CapabilityService().check(
        spec,
        CapabilityManifest.from_backend("devsim"),
    )
    assert decision.status is CapabilityStatus.SUPPORTED, decision.model_dump(
        mode="json"
    )


@pytest.mark.live_bedrock
def test_live_model_requests_missing_concentrations_instead_of_inventing_them(
    pytestconfig: pytest.Config,
) -> None:
    _require_live_bedrock(pytestconfig)
    case = SUITE.require_case("three-region-dc")

    proposal = OpenHandsBedrockGateway.from_environment().propose(
        ResearchRequest(prompt=SUITE.read_prompt(case.id)),
        _context(),
    )

    assert proposal.kind == "clarification", proposal.model_dump(mode="json")
    assert proposal.questions
    question_text = " ".join(
        f"{question.field} {question.prompt}" for question in proposal.questions
    ).lower()
    assert any(term in question_text for term in ("doping", "concentration", "profile"))
