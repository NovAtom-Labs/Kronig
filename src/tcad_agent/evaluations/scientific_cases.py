"""Researcher-level scientific cases spanning evidence, simulation, and viewing."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlparse

import yaml
from pydantic import Field, PrivateAttr, model_validator

from tcad_agent.domain.models import StrictModel
from tcad_agent.ide.results import WorkspaceResultView
from tcad_agent.knowledge.models import SearchHit, WebEvidenceRecord


class ScientificEvaluationCase(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9-]*$")
    title: str = Field(min_length=1)
    prompt_file: str = Field(min_length=1)
    spec_file: str = Field(min_length=1)
    backend: Literal["devsim", "sentaurus"]
    study_kind: Literal["equilibrium", "dc"]
    region_count: int = Field(ge=1)
    web_research_required: bool = False
    web_query: str | None = None
    preferred_domains: tuple[str, ...] = ()
    required_local_source_ids: tuple[str, ...] = ()
    expected_fields: tuple[str, ...]
    required_validation_checks: tuple[str, ...] = ()
    minimum_graphable_fields: int = Field(ge=1)

    @model_validator(mode="after")
    def require_web_contract(self) -> Self:
        if self.web_research_required and not self.web_query:
            raise ValueError("web_query is required when web research is required")
        if self.web_research_required and not self.preferred_domains:
            raise ValueError(
                "preferred_domains are required when web research is required"
            )
        return self


class ScientificEvaluationSuite(StrictModel):
    schema_version: Literal["1.0"]
    purpose: str = Field(min_length=1)
    cases: tuple[ScientificEvaluationCase, ...]

    _source_path: Path | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> Self:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("scientific evaluation case IDs must be unique")
        return self

    @classmethod
    def from_file(cls, path: Path) -> Self:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        suite = cls.model_validate(payload)
        object.__setattr__(suite, "_source_path", path.resolve())
        return suite

    def require_case(self, case_id: str) -> ScientificEvaluationCase:
        for case in self.cases:
            if case.id == case_id:
                return case
        raise KeyError(f"unknown scientific evaluation case: {case_id}")

    def read_prompt(self, case_id: str) -> str:
        return self._resolve(self.require_case(case_id).prompt_file).read_text(
            encoding="utf-8"
        )

    def spec_path(self, case_id: str) -> Path:
        return self._resolve(self.require_case(case_id).spec_file)

    def _resolve(self, relative: str) -> Path:
        if self._source_path is None:
            raise RuntimeError("scientific evaluation suite was not loaded from a file")
        target = (self._source_path.parent / relative).resolve()
        if not target.is_file():
            raise FileNotFoundError(f"scientific evaluation artifact not found: {target}")
        return target


class ScientificEvaluationScore(StrictModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    checks: dict[str, bool]


class ScientificIntakeCase(StrictModel):
    """Natural researcher request with externally observable preparation criteria."""

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9-]*$")
    title: str = Field(min_length=1)
    prompt_file: str = Field(min_length=1)
    expected_status: Literal["ready", "clarification", "blocked"]
    expected_study: Literal[
        "equilibrium", "dc", "dc_points", "ac", "frequency", "transient"
    ] | None = None
    required_concepts: tuple[str, ...] = Field(min_length=1)
    forbidden_inventions: tuple[str, ...] = ()
    maximum_questions: int = Field(default=7, ge=1, le=7)


class ScientificIntakeSuite(StrictModel):
    schema_version: Literal["1.0"]
    purpose: str = Field(min_length=1)
    cases: tuple[ScientificIntakeCase, ...]

    _source_path: Path | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> Self:
        identifiers = [case.id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("scientific intake case IDs must be unique")
        return self

    @classmethod
    def from_file(cls, path: Path) -> Self:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        suite = cls.model_validate(payload)
        object.__setattr__(suite, "_source_path", path.resolve())
        return suite

    def require_case(self, case_id: str) -> ScientificIntakeCase:
        for case in self.cases:
            if case.id == case_id:
                return case
        raise KeyError(f"unknown scientific intake case: {case_id}")

    def read_prompt(self, case_id: str) -> str:
        if self._source_path is None:
            raise RuntimeError("scientific intake suite was not loaded from a file")
        relative = self.require_case(case_id).prompt_file
        target = (self._source_path.parent / relative).resolve()
        if not target.is_file():
            raise FileNotFoundError(f"scientific intake prompt not found: {target}")
        return target.read_text(encoding="utf-8")


def _matches_domain(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(
        host == domain.lower().rstrip(".")
        or host.endswith(f".{domain.lower().rstrip('.')}")
        for domain in domains
    )


def _graphable_fields(view: WorkspaceResultView) -> set[str]:
    graphable: set[str] = set()
    for name, field in view.result.fields.items():
        if (
            len(field.positions_m) >= 2
            and len(field.positions_m) == len(field.values)
            and all(math.isfinite(value) for value in field.positions_m)
            and all(math.isfinite(value) for value in field.values)
        ):
            graphable.add(name)
    return graphable


def score_scientific_case(
    case: ScientificEvaluationCase,
    view: WorkspaceResultView,
    local_hits: tuple[SearchHit, ...],
    web_evidence: tuple[WebEvidenceRecord, ...],
) -> ScientificEvaluationScore:
    """Score externally observable research and result-workbench contracts."""

    local_sources = {hit.citation.source_id for hit in local_hits}
    validation = {check.id: check.status for check in view.validation.checks}
    graphable = _graphable_fields(view)
    required_fields = set(case.expected_fields)
    checks = {
        "backend": view.result.backend == case.backend,
        "structure": len(view.experiment.regions) == case.region_count,
        "study": view.experiment.study.kind == case.study_kind,
        "local-evidence": set(case.required_local_source_ids).issubset(local_sources),
        "web-evidence": (
            not case.web_research_required
            or any(
                evidence.content_hash
                and evidence.authority in {"primary", "scholarly"}
                and _matches_domain(evidence.url, case.preferred_domains)
                for evidence in web_evidence
            )
        ),
        "validation": view.validation.overall == "passed",
        "expected-fields": required_fields.issubset(view.result.fields),
        "validation-checks": all(
            validation.get(identifier) == "passed"
            for identifier in case.required_validation_checks
        ),
        "viewer-fields": (
            required_fields.issubset(graphable)
            and len(graphable) >= case.minimum_graphable_fields
        ),
        "provenance": all(
            (
                bool(view.manifest.input_digest),
                bool(view.manifest.runtime_digest),
                bool(view.manifest.compiler_version),
                bool(view.manifest.simulator_version),
                "results/canonical.json" in view.manifest.artifacts,
                "validation/report.json" in view.manifest.artifacts,
            )
        ),
    }
    passed_count = sum(checks.values())
    return ScientificEvaluationScore(
        passed=passed_count == len(checks),
        score=round(100 * passed_count / len(checks)),
        checks=checks,
    )
