import json
from types import SimpleNamespace

from openhands.sdk import Message, TextContent

from tcad_agent.capabilities.descriptors import CapabilityCatalog
from tcad_agent.capabilities.models import CapabilityManifest
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
