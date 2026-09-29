"""Composition service for context, model preparation, and compilation."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from tcad_agent.capabilities.descriptors import CapabilityCatalog, CapabilityCatalogView
from tcad_agent.domain.models import StrictModel
from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.context import LocalEvidenceCollector, WorkspaceContextCollector
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    CompiledAgentRequest,
    EvidenceExcerpt,
    PreparationDecision,
    WorkspaceContext,
)


class PreparationModel(Protocol):
    def prepare(
        self,
        *,
        original_prompt: str,
        answers: Sequence[ClarificationAnswer],
        workspace: WorkspaceContext,
        evidence: Sequence[EvidenceExcerpt],
        capabilities: CapabilityCatalogView | None = None,
    ) -> PreparationDecision: ...


class PreparationOutcome(StrictModel):
    decision: PreparationDecision
    workspace: WorkspaceContext
    evidence: tuple[EvidenceExcerpt, ...]
    compiled_request: CompiledAgentRequest | None = None


class ScriptedPreparationModel:
    """Deterministic model double used by lifecycle and end-to-end tests."""

    def __init__(self, decisions: Sequence[PreparationDecision]) -> None:
        self._decisions = tuple(decisions)
        self._index = 0

    def prepare(
        self,
        *,
        original_prompt: str,
        answers: Sequence[ClarificationAnswer],
        workspace: WorkspaceContext,
        evidence: Sequence[EvidenceExcerpt],
        capabilities: CapabilityCatalogView | None = None,
    ) -> PreparationDecision:
        del original_prompt, answers, workspace, evidence, capabilities
        if self._index >= len(self._decisions):
            raise RuntimeError("scripted preparation model has no remaining decision")
        decision = self._decisions[self._index]
        self._index += 1
        return decision


class PromptPreparationService:
    def __init__(
        self,
        *,
        model: PreparationModel,
        workspace_collector: WorkspaceContextCollector,
        evidence_collector: LocalEvidenceCollector,
        compiler: PromptCompiler,
        capability_hashes: Mapping[str, str],
        capability_catalog: CapabilityCatalog | None = None,
    ) -> None:
        self.model = model
        self.workspace_collector = workspace_collector
        self.evidence_collector = evidence_collector
        self.compiler = compiler
        self.capability_hashes = dict(capability_hashes)
        self.capability_catalog = capability_catalog

    def prepare(
        self,
        *,
        root: Path,
        original_prompt: str,
        answers: Sequence[ClarificationAnswer],
    ) -> PreparationOutcome:
        workspace = self.workspace_collector.collect(root)
        evidence = self.evidence_collector.collect(
            original_prompt, tuple(answer.answer for answer in answers)
        )
        decision = self.model.prepare(
            original_prompt=original_prompt,
            answers=answers,
            workspace=workspace,
            evidence=evidence,
            capabilities=(
                self.capability_catalog.public_view()
                if self.capability_catalog is not None
                else None
            ),
        )
        compiled = None
        if decision.status == "ready":
            compiled = self.compiler.compile(
                original_prompt=original_prompt,
                answers=answers,
                decision=decision,
                workspace=workspace,
                evidence=evidence,
                capability_hashes=self.capability_hashes,
            )
        return PreparationOutcome(
            decision=decision,
            workspace=workspace,
            evidence=evidence,
            compiled_request=compiled,
        )


def build_default_prompt_preparation(project_root: Path) -> PromptPreparationService:
    """Compose production preprocessing from the same environment model settings."""

    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest
    from tcad_agent.knowledge.retrieve import KnowledgeIndex
    from tcad_agent.prompting.context import capability_hashes
    from tcad_agent.prompting.gateway import EnvironmentPreparationModel

    configured_index = os.getenv("TCAD_KNOWLEDGE_INDEX")
    index_path = Path(
        configured_index
        or project_root / "knowledge-sources" / "index" / "knowledge.sqlite3"
    )
    return PromptPreparationService(
        model=EnvironmentPreparationModel(),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(KnowledgeIndex(index_path)),
        compiler=PromptCompiler(),
        capability_hashes=capability_hashes(project_root / "src" / "tcad_agent"),
        capability_catalog=CapabilityCatalog.from_manifest(
            CapabilityManifest.from_backend("devsim")
        ),
    )
