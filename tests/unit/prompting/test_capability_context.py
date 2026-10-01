import json
from types import SimpleNamespace

import pytest
from openhands.sdk import Message, TextContent

from tcad_agent.capabilities.descriptors import CapabilityCatalog
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.prompting.gateway import OpenHandsPreparationModel
from tcad_agent.prompting.models import WorkspaceContext


class CapturingLLM:
    model = "test/model"

    def __init__(self) -> None:
        self.messages: list[list[Message]] = []

    def completion(self, messages):
        self.messages.append(list(messages))
        response = {
            "status": "clarification",
            "summary": "A required researcher-owned input is missing.",
            "questions": [
                {
                    "id": "temperature",
                    "field_path": "study.temperature",
                    "prompt": "What temperature should be used?",
                    "reason": "The selected physics requires a physical temperature.",
                    "required": True,
                }
            ],
            "intent": None,
            "unresolved_critical": ["study.temperature"],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
        return SimpleNamespace(
            message=Message(
                role="assistant", content=[TextContent(text=json.dumps(response))]
            )
        )


def test_gateway_receives_bounded_structured_capabilities() -> None:
    llm = CapturingLLM()
    gateway = OpenHandsPreparationModel(llm)
    catalog = CapabilityCatalog.from_manifest(CapabilityManifest.from_backend("devsim"))

    decision = gateway.prepare(
        original_prompt="Simulate this one dimensional stack.",
        answers=(),
        workspace=WorkspaceContext(
            display_name="repo",
            git_available=False,
            git_dirty=False,
            inventory_hash="a" * 64,
        ),
        evidence=(),
        capabilities=catalog.public_view(),
    )

    payload = json.loads(llm.messages[0][1].content[0].text)
    assert decision.questions[0].field_path == "study.temperature"
    assert payload["capability_catalog"]["backend"] == "devsim"
    assert len(payload["capability_catalog"]["capabilities"]) <= 128
    assert "device" not in payload["capability_catalog"]


def test_system_policy_distinguishes_researcher_inputs_from_expert_defaults() -> None:
    policy = OpenHandsPreparationModel._system_policy()

    assert "researcher-owned" in policy
    assert "capability catalog" in policy.lower()
    assert "Do not ask for expert" in policy
    assert "ambiguous units" in policy.lower()
    assert "absolute capacitance" in policy.lower()
    assert "reuse prior parameters" in policy.lower()
    assert "failed operating points" in policy.lower()
    assert "simulator or backend explicitly named" in policy.lower()
    assert "interface coupling" in policy.lower()


def test_system_policy_does_not_turn_conversation_into_scientific_clarification() -> None:
    policy = OpenHandsPreparationModel._system_policy().lower()

    assert "greetings, thanks, or casual conversation" in policy
    assert "do not ask for a simulation objective" in policy
    assert "ready explanation" in policy


def test_absolute_terminal_current_without_area_remains_unresolved() -> None:
    payload = {
        "schema_version": "1.0",
        "name": "absolute-current-needs-area",
        "dimension": 1,
        "regions": [
            {
                "id": "silicon",
                "material": "silicon",
                "x0": "0 um",
                "x1": "1 um",
            }
        ],
        "profiles": [],
        "contacts": [
            {"id": "left", "location": "x_min", "kind": "ohmic"},
            {"id": "right", "location": "x_max", "kind": "ohmic"},
        ],
        "physics": {"equations": ["poisson"]},
        "study": {"kind": "equilibrium"},
        "observables": ["absolute_terminal_current"],
    }
    try:
        spec = ExperimentSpec.model_validate(payload)
    except ValueError:
        pytest.fail("absolute terminal current must be a portable observable")

    decision = CapabilityService().check(spec, CapabilityManifest.from_backend("devsim"))

    assert decision.status is CapabilityStatus.NEEDS_INPUT
    assert any(issue.code == "missing_contact_area" for issue in decision.issues)
