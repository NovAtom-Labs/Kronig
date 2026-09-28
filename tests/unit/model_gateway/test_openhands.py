import json
from types import SimpleNamespace

import pytest
from openhands.sdk import TextContent
from pydantic import ValidationError

from tcad_agent.control.models import ClarificationQuestion, ResearchRequest
from tcad_agent.model_gateway.base import AgentContextPacket, AgentProposal, ScriptedModelGateway
from tcad_agent.model_gateway.openhands import (
    ModelConfigurationError,
    OpenHandsBedrockGateway,
)


class FakeLLM:
    def __init__(self, response: str | Exception | list[str]) -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.messages = []
        self.calls = 0

    def completion(self, messages, tools=None):
        del tools
        self.messages.append(messages)
        response = self.responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            message=SimpleNamespace(content=[TextContent(text=response)])
        )


def test_scripted_gateway_returns_typed_proposals_in_order() -> None:
    first = AgentProposal(
        kind="clarification",
        questions=(
            ClarificationQuestion(
                field="profiles.region.value",
                prompt="What concentration should this region use?",
            ),
        ),
    )
    second = AgentProposal(kind="refusal", message="unsupported")
    gateway = ScriptedModelGateway((first, second))
    request = ResearchRequest(prompt="simulate")
    context = AgentContextPacket()
    assert gateway.propose(request, context) == first
    assert gateway.propose(request, context) == second


def test_clarification_proposal_requires_an_actionable_question() -> None:
    with pytest.raises(ValidationError, match="clarification proposal requires"):
        AgentProposal(kind="clarification", questions=())


def test_openhands_gateway_parses_structured_proposal() -> None:
    payload = {"kind": "refusal", "questions": [], "message": "unsupported"}
    gateway = OpenHandsBedrockGateway(FakeLLM(json.dumps(payload)))
    proposal = gateway.propose(ResearchRequest(prompt="simulate"), AgentContextPacket())
    assert proposal == AgentProposal.model_validate(payload)


def test_openhands_gateway_parses_json_code_fence() -> None:
    payload = {"kind": "refusal", "questions": [], "message": "unsupported"}
    response = f"```json\n{json.dumps(payload)}\n```"
    gateway = OpenHandsBedrockGateway(FakeLLM(response))

    proposal = gateway.propose(ResearchRequest(prompt="simulate"), AgentContextPacket())

    assert proposal == AgentProposal.model_validate(payload)


def test_openhands_gateway_sends_exact_experiment_schema() -> None:
    payload = {"kind": "refusal", "questions": [], "message": "unsupported"}
    llm = FakeLLM(json.dumps(payload))
    gateway = OpenHandsBedrockGateway(llm)

    gateway.propose(ResearchRequest(prompt="simulate"), AgentContextPacket())

    user_payload = json.loads(llm.messages[0][1].content[0].text)
    schema = user_payload["experiment_spec_schema"]
    assert set(schema["required"]) >= {
        "schema_version",
        "name",
        "dimension",
        "regions",
        "profiles",
        "contacts",
        "physics",
        "study",
        "observables",
    }
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["QuantityValue"]["type"] == "string"
    system_prompt = llm.messages[0][0].content[0].text
    assert "Never invent scientifically meaningful inputs" in system_prompt
    assert "return kind clarification" in system_prompt


def test_openhands_gateway_repairs_schema_invalid_spec_once() -> None:
    invalid = {"kind": "spec", "questions": [], "spec": {"schema_version": "1.0"}}
    valid_spec = {
        "schema_version": "1.0",
        "name": "generic-equilibrium",
        "dimension": 1,
        "regions": [
            {"id": "region", "material": "silicon", "x0": "0 um", "x1": "1 um"}
        ],
        "profiles": [],
        "contacts": [
            {"id": "left", "location": "x_min", "kind": "ohmic"},
            {"id": "right", "location": "x_max", "kind": "ohmic"},
        ],
        "physics": {"equations": ["poisson"], "temperature": "300 K"},
        "study": {"kind": "equilibrium"},
        "observables": ["potential"],
    }
    repaired = {"kind": "spec", "questions": [], "spec": valid_spec}
    llm = FakeLLM([json.dumps(invalid), json.dumps(repaired)])
    gateway = OpenHandsBedrockGateway(llm)

    proposal = gateway.propose(
        ResearchRequest(prompt="simulate"), AgentContextPacket()
    )

    assert proposal.spec == valid_spec
    assert llm.calls == 2
    repair_text = llm.messages[1][-1].content[0].text
    assert "Field required" in repair_text
    assert "Return only the corrected proposal JSON" in repair_text


def test_openhands_gateway_redacts_provider_error_secrets() -> None:
    secret = "ABSK-secret-value"
    gateway = OpenHandsBedrockGateway(
        FakeLLM(RuntimeError(f"authentication rejected token {secret}"))
    )
    with pytest.raises(ModelConfigurationError) as caught:
        gateway.propose(ResearchRequest(prompt="simulate"), AgentContextPacket())
    assert secret not in str(caught.value)


def test_environment_factory_requires_bedrock_credential(monkeypatch) -> None:
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    with pytest.raises(ModelConfigurationError, match="AWS_BEARER_TOKEN_BEDROCK"):
        OpenHandsBedrockGateway.from_environment()
