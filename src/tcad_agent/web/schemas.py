"""HTTP request contracts for the local researcher interface."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from tcad_agent.ide.models import PlanApprovalMode
from tcad_agent.prompting.models import ClarificationAnswer
from tcad_agent.recovery.models import RecoveryAction


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


class ApprovePlanRequest(WebRequest):
    expected_revision: int = Field(ge=0)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: PlanApprovalMode = PlanApprovalMode.REVIEW_EACH_RISK


class RevisePlanRequest(WebRequest):
    expected_revision: int = Field(ge=0)
    instruction: str = Field(min_length=1, max_length=4_000)


class SaveWorkspaceFileRequest(WebRequest):
    path: str = Field(min_length=1, max_length=4096)
    content: str = Field(max_length=1_048_576)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExportBundleRequest(WebRequest):
    destination: str = Field(min_length=1, max_length=4096)


class RecoveryReviewRequest(WebRequest):
    action: RecoveryAction


class ResolveAgentApprovalRequest(WebRequest):
    expected_revision: int = Field(ge=0)


class DenyAgentApprovalRequest(ResolveAgentApprovalRequest):
    reason: str = Field(min_length=1, max_length=2_000)
