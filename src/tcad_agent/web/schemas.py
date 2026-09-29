"""HTTP request contracts for the local researcher interface."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcad_agent.prompting.models import ClarificationAnswer


class WebRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenWorkspaceRequest(WebRequest):
    path: str = Field(min_length=1, max_length=4096)


class CreateMessageRequest(WebRequest):
    content: str = Field(min_length=1, max_length=100_000)


class StartAgentRunRequest(WebRequest):
    message_id: UUID


class AnswerClarificationRequest(WebRequest):
    expected_revision: int = Field(ge=0)
    answers: tuple[ClarificationAnswer, ...] = Field(min_length=1, max_length=7)


class SaveWorkspaceFileRequest(WebRequest):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=1_048_576)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ResolveAgentApprovalRequest(WebRequest):
    expected_revision: int = Field(ge=0)


class DenyAgentApprovalRequest(ResolveAgentApprovalRequest):
    reason: str = Field(min_length=1, max_length=2_000)
