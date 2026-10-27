"""Composition service for context, model preparation, and compilation."""

from __future__ import annotations

import inspect
import os
import queue
import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from tcad_agent.capabilities.descriptors import CapabilityCatalog, CapabilityCatalogView
from tcad_agent.domain.models import StrictModel
from tcad_agent.domain.units import QuantityValue
from tcad_agent.prompting.authority import unsupported_physics_inputs
from tcad_agent.prompting.clarifications import (
    current_answers,
    state_fingerprint,
    validate_questions,
)
from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.completeness import (
    _matches_scope,
    _scoped_path,
    _without_entity,
    canonical_path,
    complete_input,
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
        catalog_resolver: Callable[[str], CapabilityCatalog] | None = None,
    ) -> None:
        self.catalog_resolver = catalog_resolver
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
        prior_decisions: Sequence[PreparationDecision] = (),
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
        # The backend follows the simulator the researcher names, on every round.
        request_catalog = self.capability_catalog
        if self.catalog_resolver is not None:
            request_catalog = self.catalog_resolver(original_prompt)
        catalog_view = request_catalog.public_view() if request_catalog else None
        incremental = self._literal_answer_decision(previous_decision, answers, request_catalog)
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
            capabilities=catalog_view,
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
        timeout = max(1, float(os.getenv("AGENT_KRONIG_PREPARATION_TIMEOUT", "900")))
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
            active_answers = current_answers(answers)
            changed = {
                _scoped_path(q.field_path)
                for q in previous_decision.questions
                if any(answer.question_id == q.id and (
                    answer.field_path is None
                    or _scoped_path(answer.field_path) == _scoped_path(q.field_path)
                ) for answer in active_answers)
            }
            fields = {_scoped_path(field.path): field for field in decision.intent.fields}
            previous_fields = {
                _scoped_path(field.path): field for field in previous_decision.intent.fields
            }
            # A measurement choice may be answered under a related field (e.g.
            # frequency), but replacing an analysis requires explicit researcher
            # provenance for the new study kind, not a partial model response.
            new_kind = next(
                (
                    field
                    for field in decision.intent.fields
                    if canonical_path(field.path) == "study.kind"
                    and field.origin.value == "researcher"
                ),
                None,
            )
            old_kind = previous_fields.get("study.kind")
            analysis_changed = "study.kind" in changed or bool(
                any(path.startswith("study.") for path in changed)
                and new_kind is not None
                and (
                    (old_kind is not None and old_kind.value != new_kind.value)
                    or (
                        old_kind is None
                        and "study." + str(new_kind.value)
                        not in previous_decision.intent.selected_capabilities
                    )
                )
            )
            preserve_models = (
                "physics.models" in previous_fields
                and "physics.models" not in changed
                and previous_fields["physics.models"].origin.value in {"researcher", "repository"}
            )
            if analysis_changed:
                changed.add("study.kind")
            retained = tuple(
                cap
                for cap in previous_decision.intent.selected_capabilities
                if (not cap.startswith("study.") or not analysis_changed)
                and not (
                    ("physics.models" in changed or not preserve_models)
                    and cap.startswith("model.")
                )
            )
            current_caps = tuple(
                cap
                for cap in decision.intent.selected_capabilities
                if not (preserve_models and cap.startswith("model."))
            )
            for field in previous_decision.intent.fields:
                if analysis_changed and _scoped_path(field.path).startswith("study."):
                    # Analysis-specific fields are revalidated in the new study context.
                    # Never replace a newly confirmed voltage with an old frequency.
                    if _scoped_path(field.path) in fields:
                        continue
                    candidate = decision.intent.model_copy(update={"fields": (field,)})
                    if not complete_input(candidate, field.path, catalog_view):
                        continue
                if field.origin.value in {"researcher", "repository"} and not any(
                    _matches_scope(field.path, path) for path in changed
                ):
                    previous_value = field.value
                    for path in changed:
                        parts = _scoped_path(path).split(".")
                        if (
                            len(parts) == 3
                            and parts[0] in {"contacts", "regions", "profiles", "interfaces"}
                            and _scoped_path(field.path) == parts[0] + "." + parts[2]
                        ):
                            field = field.model_copy(
                                update={"value": _without_entity(field.value, parts[0], parts[1])}
                            )
                    if field.value == {}:
                        continue
                    current = fields.get(_scoped_path(field.path))
                    if current and field.value != previous_value and isinstance(field.value, dict):
                        current_value = current.value
                        if isinstance(current_value, list):
                            current_value = {
                                str(index): value for index, value in enumerate(current_value)
                            }
                        if isinstance(current_value, dict):
                            field = current.model_copy(
                                update={"value": {**current_value, **field.value}}
                            )
                    fields[_scoped_path(field.path)] = field
            decision = decision.model_copy(
                update={
                    "intent": decision.intent.model_copy(
                        update={
                            "fields": tuple(fields.values()),
                            "selected_capabilities": tuple(
                                dict.fromkeys(
                                    (
                                        *retained,
                                        *current_caps,
                                    )
                                )
                            ),
                        }
                    )
                }
            )
        unsupported = unsupported_physics_inputs(decision.intent) if decision.intent else []
        if unsupported:
            decision = PreparationDecision(
                status="blocked",
                summary="The portable physics contract cannot represent these explicit inputs: "
                + ", ".join(unsupported)
                + ". No replacement defaults were applied and no simulation was started.",
            )
        decision = enforce_completeness(decision, catalog_view)
        decision = readable_questions(decision, catalog_view)
        try:
            validate_questions(decision, original_prompt, answers, catalog_view, previous_decision)
        except ValueError as exc:
            raise ModelResponseError(str(exc)) from exc
        if answers and decision.status == "clarification" and not any(
            question.reason_kind in {"invalid", "conflict", "ambiguous", "dependency_changed"}
            for question in decision.questions
        ) and state_fingerprint(decision) in {
            state_fingerprint(item) for item in (*prior_decisions, previous_decision)
            if item is not None
        }:
            raise ModelResponseError(
                "Request preparation did not resolve the submitted answers. No simulation was "
                "started and the same questions will not be repeated. Your answers are retained; "
                "retry preparation or revise the request."
            )
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

    def _literal_answer_decision(self, previous, answers, request_catalog):
        """Apply only literal, unit-checked scalar answers to already reasoned questions.

        Free text, choices, structured values and unresolved new intent still go to
        the model. This is not a replacement for scientific intent reasoning.
        """
        if not previous or not previous.intent or not request_catalog:
            return None
        if previous.status != "clarification":
            return None
        catalog = request_catalog.public_view()
        supplied = {answer.question_id: answer.answer.strip() for answer in current_answers(answers)
            if answer.field_path is None or any(
                _scoped_path(answer.field_path) == _scoped_path(q.field_path)
                for q in previous.questions
            )}
        fields = {field.path: field for field in previous.intent.fields}
        for question in previous.questions:
            if question.id not in supplied:
                return None
            if re.match(r"^[+-]?(?:\d|\.\d)", supplied[question.id]) is None:
                # Unit-only and conversational replies require reasoning about
                # the previous quantity, not implicit replacement with 1 unit.
                return None
            descriptor = descriptor_for_path(
                question.field_path, catalog, previous.intent.selected_capabilities
            )
            if not descriptor or not descriptor.unit:
                return None
            try:
                literal = supplied[question.id]
                if (re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", literal)
                        and re.search(
                            r"(?<!\w)" + re.escape(descriptor.unit) + r"(?!\w)", question.prompt
                        )):
                    literal = f"{literal} {descriptor.unit}"
                value = QuantityValue.model_validate(literal)
                value.require(descriptor.unit, descriptor.description)
            except ValueError:
                return None
            parts = _scoped_path(question.field_path).split(".")
            if len(parts) == 3 and parts[0] in {"contacts", "regions", "profiles", "interfaces"}:
                for key, field in tuple(fields.items()):
                    if _scoped_path(key) != parts[0] + "." + parts[2]:
                        continue
                    remaining = _without_entity(field.value, parts[0], parts[1])
                    if remaining == {}:
                        del fields[key]
                    else:
                        fields[key] = field.model_copy(update={"value": remaining})
            fields[question.field_path] = IntentField(
                path=question.field_path, value=literal, origin="researcher"
            )
        answered = {_scoped_path(question.field_path) for question in previous.questions}
        remaining = tuple(
            path for path in previous.unresolved_critical if _scoped_path(path) not in answered
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

    from tcad_agent.capabilities.active import catalog_for_request
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
        catalog_resolver=catalog_for_request,
    )
