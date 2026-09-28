"""Stable interfaces for model-generated structured proposals."""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import Field, JsonValue, model_validator

from tcad_agent.control.models import ClarificationQuestion, ResearchRequest
from tcad_agent.domain.models import StrictModel
from tcad_agent.knowledge.models import Citation


class KnowledgeExcerpt(StrictModel):
    content: str = Field(min_length=1, max_length=1600)
    citation: Citation
    reviewed: bool


class AgentContextPacket(StrictModel):
    citations: tuple[str, ...] = ()
    capabilities: dict[str, JsonValue] = Field(default_factory=dict)
    clarification_answers: dict[str, str] = Field(default_factory=dict)
    knowledge: tuple[KnowledgeExcerpt, ...] = ()
    procedures: tuple[str, ...] = ()


class AgentProposal(StrictModel):
    kind: Literal["clarification", "spec", "refusal"]
    questions: tuple[ClarificationQuestion, ...] = ()
    spec: dict[str, JsonValue] | None = None
    message: str | None = None

    @model_validator(mode="after")
    def require_kind_payload(self) -> "AgentProposal":
        if self.kind == "clarification" and not self.questions:
            raise ValueError("clarification proposal requires at least one question")
        if self.kind == "spec" and self.spec is None:
            raise ValueError("spec proposal requires a specification")
        if self.kind == "refusal" and not self.message:
            raise ValueError("refusal proposal requires a message")
        return self


class ModelGateway(Protocol):
    def propose(
        self, request: ResearchRequest, context: AgentContextPacket
    ) -> AgentProposal: ...


class ScriptedModelGateway:
    def __init__(self, proposals: Sequence[AgentProposal]) -> None:
        self._proposals = tuple(proposals)
        self._index = 0

    def propose(self, request: ResearchRequest, context: AgentContextPacket) -> AgentProposal:
        del request, context
        if self._index >= len(self._proposals):
            raise RuntimeError("scripted model gateway has no remaining proposal")
        proposal = self._proposals[self._index]
        self._index += 1
        return proposal
