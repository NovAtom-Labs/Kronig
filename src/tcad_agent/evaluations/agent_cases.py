"""Typed natural-language cases for evaluating TCAD agent behavior."""

from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import Field, PrivateAttr, model_validator

from tcad_agent.domain.models import StrictModel


class AgentEvaluationCase(StrictModel):
    """One prompt and the behavior an acceptable agent response must preserve."""

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9-]*$")
    title: str = Field(min_length=1)
    prompt_file: str = Field(min_length=1)
    requested_backend: str = Field(min_length=1)
    expected_stage: Literal[
        "clarification_required",
        "plan_ready",
        "capability_refusal",
        "completed",
    ]
    required_clarifications: tuple[str, ...] = ()
    preserved_facts: tuple[str, ...] = ()
    required_physics: tuple[str, ...] = ()
    required_observables: tuple[str, ...] = ()
    equilibrium_invariants: tuple[str, ...] = ()
    prohibited_behaviors: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


class AgentEvaluationSuite(StrictModel):
    """Versioned collection of agent cases loaded relative to its YAML file."""

    schema_version: Literal["1.0"]
    purpose: str = Field(min_length=1)
    cases: tuple[AgentEvaluationCase, ...]

    _source_path: Path | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> Self:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("agent evaluation case IDs must be unique")
        return self

    @classmethod
    def from_file(cls, path: Path) -> Self:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        suite = cls.model_validate(payload)
        object.__setattr__(suite, "_source_path", path.resolve())
        return suite

    def require_case(self, case_id: str) -> AgentEvaluationCase:
        for case in self.cases:
            if case.id == case_id:
                return case
        raise KeyError(f"unknown agent evaluation case: {case_id}")

    def read_prompt(self, case_id: str) -> str:
        if self._source_path is None:
            raise RuntimeError("agent evaluation suite was not loaded from a file")
        case = self.require_case(case_id)
        prompt_path = (self._source_path.parent / case.prompt_file).resolve()
        if not prompt_path.is_file():
            raise FileNotFoundError(f"agent evaluation prompt not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

