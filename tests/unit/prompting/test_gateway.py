from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from openhands.sdk import Message, TextContent

from tcad_agent.prompting.gateway import (
    ModelResponseError,
    OpenHandsPreparationModel,
)
from tcad_agent.prompting.models import EvidenceExcerpt, WorkspaceContext


class ScriptedLLM:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.messages: list[list[Message]] = []
        self.model = "test/preparation-model"

    def completion(self, messages):
        self.messages.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            message=Message(
                role="assistant", content=[TextContent(text=response)]
            )
        )


def workspace() -> WorkspaceContext:
    return WorkspaceContext(
        display_name="repo",
        git_available=False,
        git_dirty=False,
        inventory_hash="a" * 64,
    )


def test_gateway_parses_a_generic_clarification_decision() -> None:
    response = json.dumps(
        {
            "status": "clarification",
            "summary": "One physical boundary condition is missing.",
            "questions": [
                {
                    "id": "contact_behavior",
                    "field_path": "contacts.behavior",
                    "prompt": "What contact behavior should be used?",
                    "reason": "This changes the electrical boundary condition.",
                    "required": True,
                }
            ],
            "intent": None,
            "unresolved_critical": ["contacts.behavior"],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    gateway = OpenHandsPreparationModel(ScriptedLLM([response]))

    decision = gateway.prepare(
        original_prompt="Simulate the structure at equilibrium.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.status == "clarification"
    assert decision.questions[0].field_path == "contacts.behavior"


def test_gateway_derives_missing_clarification_paths_from_typed_questions() -> None:
    response = json.dumps(
        {
            "status": "clarification",
            "summary": "Two researcher-owned conditions are missing.",
            "questions": [
                {
                    "id": "temperature",
                    "field_path": "physics.temperature",
                    "prompt": "What scalar reference temperature should be used?",
                    "reason": "The simulation contract requires this value.",
                    "required": True,
                },
                {
                    "id": "fixed_contact",
                    "field_path": "contacts.right.voltage",
                    "prompt": "What fixed voltage should be applied on the right?",
                    "reason": "It defines the applied bias.",
                    "required": True,
                },
            ],
            "intent": None,
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    llm = ScriptedLLM([response])

    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Simulate the stated spatial-temperature study.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.unresolved_critical == (
        "physics.temperature",
        "contacts.right.voltage",
    )
    assert len(llm.messages) == 1


def test_gateway_repairs_one_invalid_structured_response() -> None:
    valid = {
        "status": "ready",
        "summary": "The repository request is complete.",
        "questions": [],
        "intent": {
            "task_kind": "repository_change",
            "objective": "Inspect the repository and fix the failing test.",
            "fields": [],
            "exclusions": [],
            "deliverables": [],
            "validation_expectations": ["Run the relevant tests."],
            "unresolved_noncritical": [],
            "unresolved_critical": [],
        },
        "unresolved_critical": [],
        "warnings": [],
        "runtime_research_needed": False,
        "runtime_research_reason": None,
    }
    llm = ScriptedLLM(["not json", json.dumps(valid)])

    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Inspect the repository and fix the failing test.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.status == "ready"
    assert len(llm.messages) == 2


def test_gateway_sanitizes_provider_errors() -> None:
    gateway = OpenHandsPreparationModel(
        ScriptedLLM([RuntimeError("credential secret-value was rejected")])
    )

    with pytest.raises(ModelResponseError) as captured:
        gateway.prepare(
            original_prompt="Inspect the repository",
            answers=(),
            workspace=workspace(),
            evidence=(),
        )

    assert "secret-value" not in str(captured.value)


def test_gateway_allows_platform_to_choose_an_output_file_format() -> None:
    response = json.dumps(
        {
            "status": "ready",
            "summary": "The simulation request is executable.",
            "questions": [],
            "intent": {
                "task_kind": "simulation",
                "objective": "Run the requested equilibrium simulation.",
                "fields": [
                    {
                        "path": "outputs.file_format",
                        "value": "canonical-json",
                        "origin": "platform_default",
                        "source_reference": "platform output contract",
                        "evidence_refs": [],
                    }
                ],
                "exclusions": [],
                "deliverables": [],
                "validation_expectations": [],
                "unresolved_noncritical": [],
                "unresolved_critical": [],
            },
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )

    decision = OpenHandsPreparationModel(ScriptedLLM([response])).prepare(
        original_prompt="Run the specified simulation.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.intent is not None
    assert decision.intent.fields[0].path == "outputs.file_format"


def test_gateway_allows_reviewed_evidence_to_choose_interface_coupling() -> None:
    response = json.dumps(
        {
            "status": "ready",
            "summary": "The material adjacency is complete.",
            "questions": [],
            "intent": {
                "task_kind": "simulation",
                "objective": "Run the requested layered simulation.",
                "fields": [
                    {
                        "path": "interfaces.oxide_silicon.coupling",
                        "value": "continuity",
                        "origin": "evidence",
                        "rationale": "The reviewed backend guide supports this coupling.",
                        "evidence_refs": ["guide:interfaces"],
                    }
                ],
                "exclusions": [],
                "deliverables": [],
                "validation_expectations": [],
                "unresolved_noncritical": [],
                "unresolved_critical": [],
            },
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    evidence = EvidenceExcerpt(
        id="guide:interfaces",
        title="Reviewed guide",
        url="internal://guide",
        version="1",
        content_hash="a" * 64,
        reviewed=True,
        content="Continuity coupling is supported.",
    )

    decision = OpenHandsPreparationModel(ScriptedLLM([response])).prepare(
        original_prompt="Model the stated oxide and silicon layers.",
        answers=(),
        workspace=workspace(),
        evidence=(evidence,),
    )

    assert decision.status == "ready"


def test_gateway_reconciles_explicit_researcher_value_mislabeled_as_evidence() -> None:
    response = json.dumps(
        {
            "status": "ready",
            "summary": "The requested profile is complete.",
            "questions": [],
            "intent": {
                "task_kind": "simulation",
                "objective": "Run the requested silicon study.",
                "fields": [
                    {
                        "path": "regions.p.profile.type",
                        "value": "uniform",
                        "origin": "evidence",
                        "rationale": "The guide describes uniform profiles.",
                        "evidence_refs": ["guide:profiles"],
                    }
                ],
                "exclusions": [],
                "deliverables": [],
                "validation_expectations": [],
                "unresolved_noncritical": [],
                "unresolved_critical": [],
            },
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    evidence = EvidenceExcerpt(
        id="guide:profiles",
        title="Reviewed profile guide",
        url="internal://profiles",
        version="1",
        content_hash="b" * 64,
        reviewed=True,
        content="Uniform profiles are supported.",
    )

    decision = OpenHandsPreparationModel(ScriptedLLM([response])).prepare(
        original_prompt="Use uniform boron doping in the p region.",
        answers=(),
        workspace=workspace(),
        evidence=(evidence,),
    )

    assert decision.intent is not None
    field = decision.intent.fields[0]
    assert field.origin.value == "researcher"
    assert field.evidence_refs == ()


def test_gateway_does_not_reconcile_value_absent_from_researcher_input() -> None:
    invalid = {
        "status": "ready",
        "summary": "The profile is complete.",
        "questions": [],
        "intent": {
            "task_kind": "simulation",
            "objective": "Run a silicon study.",
            "fields": [
                {
                    "path": "regions.p.profile.type",
                    "value": "gaussian",
                    "origin": "evidence",
                    "rationale": "The guide describes Gaussian profiles.",
                    "evidence_refs": ["guide:profiles"],
                }
            ],
            "exclusions": [],
            "deliverables": [],
            "validation_expectations": [],
            "unresolved_noncritical": [],
            "unresolved_critical": [],
        },
        "unresolved_critical": [],
        "warnings": [],
        "runtime_research_needed": False,
        "runtime_research_reason": None,
    }
    evidence = EvidenceExcerpt(
        id="guide:profiles",
        title="Reviewed profile guide",
        url="internal://profiles",
        version="1",
        content_hash="b" * 64,
        reviewed=True,
        content="Gaussian profiles are supported.",
    )
    gateway = OpenHandsPreparationModel(
        ScriptedLLM([json.dumps(invalid), json.dumps(invalid)])
    )

    with pytest.raises(ModelResponseError, match="researcher-owned field"):
        gateway.prepare(
            original_prompt="Use boron doping in the p region.",
            answers=(),
            workspace=workspace(),
            evidence=(evidence,),
        )
