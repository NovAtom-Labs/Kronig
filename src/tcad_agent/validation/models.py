"""Validation evidence schema."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from tcad_agent.domain.models import StrictModel

ValidationStatus = Literal["passed", "warning", "failed", "not_applicable"]
EvidenceOrigin = Literal[
    "configured",
    "simulator_observed",
    "derived",
    "statically_verified",
]


class ValidationCheck(StrictModel):
    id: str
    level: Literal["execution", "numerical", "physical", "provenance"]
    status: ValidationStatus
    measured_value: float | int | str | None = None
    limit: float | int | str | None = None
    message: str
    evidence_origin: EvidenceOrigin = "derived"
    evidence_paths: tuple[str, ...] = ()
    unit: str | None = None
    absolute_tolerance: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    relative_tolerance: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    scale: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    applicability_reason: str | None = None

    @model_validator(mode="after")
    def explain_applicability(self) -> "ValidationCheck":
        if self.applicability_reason is None:
            object.__setattr__(self, "applicability_reason", self.message)
        return self


class ValidationReport(StrictModel):
    overall: ValidationStatus
    checks: tuple[ValidationCheck, ...]
    acceptance_limits: dict[str, Annotated[float, Field(ge=0, allow_inf_nan=False)]] | None = None
    validation_policy_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @property
    def checks_by_id(self) -> dict[str, ValidationCheck]:
        return {check.id: check for check in self.checks}
