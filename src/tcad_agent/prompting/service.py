"""Composition service for context, model preparation, and compilation."""

from __future__ import annotations

import inspect
import os
import queue
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from tcad_agent.capabilities.descriptors import CapabilityCatalog, CapabilityCatalogView
from tcad_agent.domain.models import StrictModel
from tcad_agent.domain.units import QuantityValue
from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.completeness import (
    canonical_path,
    descriptor_for_path,
    enforce_completeness,
    readable_questions,
)
from tcad_agent.prompting.context import LocalEvidenceCollector, WorkspaceContextCollector
from tcad_agent.prompting.errors import ModelResponseError
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    CompiledAgentRequest,
    EvidenceExcerpt,
    IntentField,
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
        self._evidence_cache: dict[tuple[str, str, str], tuple[EvidenceExcerpt, ...]] = {}

    def prepare(
        self,
        *,
        root: Path,
        original_prompt: str,
        answers: Sequence[ClarificationAnswer],
        on_progress: Callable[[str], None] | None = None,
        previous_decision: PreparationDecision | None = None,
    ) -> PreparationOutcome:
        def report(phase: str) -> None:
            if on_progress is not None:
                on_progress(phase)

        report("reviewing_workspace")
        workspace = self.workspace_collector.collect(root)
        report("consulting_local_knowledge")
        knowledge_path = getattr(self.evidence_collector.index, "path", None)
        knowledge_version = (
            knowledge_path.stat().st_mtime_ns if knowledge_path and knowledge_path.exists() else 0
        )
        cache_key = (
            str(root.resolve()),
            workspace.inventory_hash,
            f"{knowledge_version}:{original_prompt}:"
            + repr(tuple((answer.question_id, answer.answer) for answer in answers)),
        )
        evidence = self._evidence_cache.get(cache_key)
        if evidence is None:
            evidence = self.evidence_collector.collect(
                original_prompt, tuple(answer.answer for answer in answers)
            )
            if len(self._evidence_cache) >= 16:
                self._evidence_cache.clear()
            self._evidence_cache[cache_key] = evidence
        report("reasoning_about_scientific_intent")
        catalog_view = self.capability_catalog.public_view() if self.capability_catalog else None
        incremental = self._literal_answer_decision(previous_decision, answers)
        if incremental is not None:
            report("validating_research_intent")
            incremental = readable_questions(
                enforce_completeness(incremental, catalog_view), catalog_view
            )
            return PreparationOutcome(
                decision=incremental,
                workspace=workspace,
                evidence=evidence,
                compiled_request=(
                    self.compiler.compile(
                        original_prompt=original_prompt,
                        answers=answers,
                        decision=incremental,
                        workspace=workspace,
                        evidence=evidence,
                        capability_hashes=self.capability_hashes,
                    )
                    if incremental.status == "ready"
                    else None
                ),
            )
        model_arguments = dict(
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
        if "previous_decision" in inspect.signature(self.model.prepare).parameters:
            model_arguments["previous_decision"] = previous_decision
        heartbeat_phase = "awaiting_model_response"

        def model_progress(phase: str) -> None:
            nonlocal heartbeat_phase
            heartbeat_phase = phase
            report(phase)

        if "on_progress" in inspect.signature(self.model.prepare).parameters:
            model_arguments["on_progress"] = model_progress
        response: queue.Queue = queue.Queue(maxsize=1)

        def infer() -> None:
            try:
                response.put((True, self.model.prepare(**model_arguments)))
            except Exception as error:
                response.put((False, error))

        threading.Thread(target=infer, daemon=True, name="kronig-preparation-inference").start()
        started = time.monotonic()
        timeout = max(1, float(os.getenv("AGENT_KRONIG_PREPARATION_TIMEOUT", "300")))
        while True:
            try:
                successful, result = response.get(
                    timeout=min(8, max(0.01, timeout - (time.monotonic() - started)))
                )
                if not successful:
                    raise result
                decision = result
                break
            except queue.Empty:
                if time.monotonic() - started >= timeout:
                    raise ModelResponseError(
                        "Request preparation timed out. No simulation was started. "
                        "Try again or simplify the request."
                    ) from None
                report(heartbeat_phase)
        if previous_decision and previous_decision.intent and decision.intent:
            changed = {
                canonical_path(q.field_path)
                for q in previous_decision.questions
                if q.id in {answer.question_id for answer in answers}
            }
            fields = {field.path: field for field in decision.intent.fields}
            for field in previous_decision.intent.fields:
                if field.origin.value == "researcher" and canonical_path(field.path) not in changed:
                    fields[field.path] = field
            decision = decision.model_copy(
                update={
                    "intent": decision.intent.model_copy(
                        update={
                            "fields": tuple(fields.values()),
                            "selected_capabilities": tuple(
                                dict.fromkeys(
                                    (
                                        *previous_decision.intent.selected_capabilities,
                                        *decision.intent.selected_capabilities,
                                    )
                                )
                            ),
                        }
                    )
                }
            )
        decision = enforce_completeness(
            decision, self.capability_catalog.public_view() if self.capability_catalog else None
        )
        decision = readable_questions(decision, catalog_view)
        compiled = None
        if decision.status == "ready":
            report("compiling_request")
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

    def _literal_answer_decision(self, previous, answers):
        """Apply only literal, unit-checked scalar answers to already reasoned questions.

        Free text, choices, structured values and unresolved new intent still go to
        the model. This is not a replacement for scientific intent reasoning.
        """
        if not previous or not previous.intent or not self.capability_catalog:
            return None
        if previous.status != "clarification":
            return None
        catalog = self.capability_catalog.public_view()
        supplied = {answer.question_id: answer.answer.strip() for answer in answers}
        fields = {field.path: field for field in previous.intent.fields}
        for question in previous.questions:
            if question.id not in supplied:
                return None
            descriptor = descriptor_for_path(
                question.field_path, catalog, previous.intent.selected_capabilities
            )
            if not descriptor or not descriptor.unit:
                return None
            try:
                value = QuantityValue.model_validate(supplied[question.id])
                value.require(descriptor.unit, descriptor.description)
            except ValueError:
                return None
            fields[question.field_path] = IntentField(
                path=question.field_path, value=supplied[question.id], origin="researcher"
            )
        answered = {canonical_path(question.field_path) for question in previous.questions}
        remaining = tuple(
            path for path in previous.unresolved_critical if canonical_path(path) not in answered
        )
        if remaining:
            return None
        return previous.model_copy(
            update={
                "status": "ready",
                "questions": (),
                "unresolved_critical": (),
                "intent": previous.intent.model_copy(
                    update={
                        "fields": tuple(fields.values()),
                        "unresolved_critical": (),
                    }
                ),
            }
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
        configured_index or project_root / "knowledge-sources" / "index" / "knowledge.sqlite3"
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
