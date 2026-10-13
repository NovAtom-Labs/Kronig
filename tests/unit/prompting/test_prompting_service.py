from __future__ import annotations

from pathlib import Path

import pytest

from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.context import LocalEvidenceCollector, WorkspaceContextCollector
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    ClarificationQuestion,
    IntentField,
    IntentOrigin,
    PreparationDecision,
    ResolvedResearchIntent,
)
from tcad_agent.prompting.service import PromptPreparationService, ScriptedPreparationModel


class EmptyKnowledgeIndex:
    def search(self, query: str, filters=None, limit: int = 5):
        del query, filters, limit
        return ()


def test_researcher_changed_analysis_does_not_resurrect_old_study(tmp_path):
    previous = PreparationDecision(
        status="clarification",
        summary="Need frequency",
        questions=(
            ClarificationQuestion(
                id="frequency",
                field_path="study.frequency",
                prompt="Frequency?",
                reason="Controls AC",
            ),
        ),
        unresolved_critical=("study.frequency",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Capacitance",
            selected_capabilities=("study.ac",),
            fields=(IntentField(path="study.kind", value="ac", origin="researcher"),),
        ),
    )
    resolved = PreparationDecision(
        status="ready",
        summary="Researcher chose quasi-static",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Quasi-static charge response",
            selected_capabilities=("study.dc",),
            fields=(IntentField(path="study.kind", value="dc", origin="researcher"),),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([resolved]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    outcome = service.prepare(
        root=tmp_path,
        original_prompt="Extract capacitance",
        previous_decision=previous,
        answers=(
            ClarificationAnswer(
                question_id="frequency", answer="Quasi-static charge response instead of AC"
            ),
        ),
    )
    assert outcome.decision.intent.selected_capabilities == ("study.dc",)
    assert next(f.value for f in outcome.decision.intent.fields if f.path == "study.kind") == "dc"


@pytest.mark.parametrize("origin", ["researcher", "repository"])
def test_contact_answer_preserves_confirmed_models(tmp_path, origin):
    (tmp_path / "reference.md").write_text("Use Fermi statistics and SRH recombination.")
    previous = PreparationDecision(
        status="clarification",
        summary="Choose contact",
        unresolved_critical=("contacts.kind",),
        questions=(
            ClarificationQuestion(
                id="contact",
                field_path="contacts.kind",
                prompt="Contact?",
                reason="Boundary condition",
            ),
        ),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Transport",
            selected_capabilities=("model.fermi", "model.srh"),
            fields=(
                IntentField(
                    path="physics.models",
                    value=["fermi", "srh"],
                    origin=origin,
                    source_reference="reference.md" if origin == "repository" else None,
                ),
            ),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="Contact selected",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Transport",
            selected_capabilities=("model.boltzmann",),
            fields=(IntentField(path="physics.models", value=["boltzmann"], origin="researcher"),),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([current]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    result = service.prepare(
        root=tmp_path,
        original_prompt="Transport",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="contact", answer="Use ohmic contacts"),),
    )
    intent = result.decision.intent
    assert next(f.value for f in intent.fields if f.path == "physics.models") == ["fermi", "srh"]
    assert "model.fermi" in intent.selected_capabilities
    assert "model.srh" in intent.selected_capabilities
    assert "model.boltzmann" not in intent.selected_capabilities


def test_geometry_answer_preserves_all_confirmed_analyses(tmp_path):
    previous = PreparationDecision(
        status="clarification",
        summary="Length needed",
        unresolved_critical=("regions.length",),
        questions=(
            ClarificationQuestion(
                id="length", field_path="regions.length", prompt="Length?", reason="Geometry"
            ),
        ),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Equilibrium and AC",
            selected_capabilities=("study.equilibrium", "study.ac"),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="Length supplied",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Equilibrium and AC",
            selected_capabilities=("study.ac",),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([current]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    result = service.prepare(
        root=tmp_path,
        original_prompt="Equilibrium and AC",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="length", answer="1 um"),),
    )
    assert set(result.decision.intent.selected_capabilities) == {"study.equilibrium", "study.ac"}


def test_frequency_answer_is_not_an_analysis_replacement(tmp_path):
    previous = PreparationDecision(
        status="clarification",
        summary="Frequency needed",
        unresolved_critical=("study.frequency",),
        questions=(
            ClarificationQuestion(
                id="freq",
                field_path="study.frequency",
                prompt="Frequency?",
                reason="Measurement condition",
            ),
        ),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Equilibrium and AC",
            selected_capabilities=("study.equilibrium", "study.ac"),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="Frequency selected",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Equilibrium and AC",
            selected_capabilities=("study.ac",),
            fields=(IntentField(path="study.kind", value="ac", origin="researcher"),),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([current]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    result = service.prepare(
        root=tmp_path,
        original_prompt="Equilibrium and AC",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="freq", answer="1 MHz"),),
    )
    assert set(result.decision.intent.selected_capabilities) == {"study.equilibrium", "study.ac"}


def test_answered_statistics_choice_updates_models_without_losing_original_geometry(tmp_path):
    previous = PreparationDecision(
        status="clarification",
        summary="Choose statistics",
        questions=(
            ClarificationQuestion(
                id="statistics",
                field_path="physics.statistics",
                prompt="Carrier statistics?",
                reason="Controls populations",
            ),
        ),
        unresolved_critical=("physics.statistics",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Transport",
            selected_capabilities=("model.boltzmann",),
            fields=(
                IntentField(path="physics.models", value=["boltzmann", "srh"], origin="researcher"),
                IntentField(path="regions.length", value="2 um", origin="researcher"),
            ),
        ),
    )
    new = PreparationDecision(
        status="ready",
        summary="Fermi selected",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Transport",
            selected_capabilities=("model.fermi", "model.srh"),
            fields=(
                IntentField(path="physics.models", value=["fermi", "srh"], origin="researcher"),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([new]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    outcome = service.prepare(
        root=tmp_path,
        original_prompt="Transport",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="statistics", answer="Fermi statistics"),),
    )
    fields = {field.path: field.value for field in outcome.decision.intent.fields}
    assert fields["physics.models"] == ["fermi", "srh"]
    assert fields["regions.length"] == "2 um"
    assert "model.boltzmann" not in outcome.decision.intent.selected_capabilities


def test_heartbeat_does_not_replace_a_streaming_stage(monkeypatch, tmp_path: Path):
    import queue
    import threading

    from tcad_agent.prompting import service as service_module

    class ObservedQueue:
        def __init__(self, maxsize):
            self.ready = threading.Event()
            self.calls = 0

        def put(self, value):
            self.value = value
            self.ready.set()

        def get(self, timeout):
            assert self.ready.wait(2)
            self.calls += 1
            if self.calls == 1:
                raise queue.Empty
            return self.value

    class StreamingModel:
        def prepare(self, on_progress, **kwargs):
            on_progress("receiving_preparation_response")
            return PreparationDecision(
                status="ready",
                summary="Ready",
                intent=ResolvedResearchIntent(
                    task_kind="analysis",
                    objective="Inspect the evidence",
                ),
            )

    monkeypatch.setattr(service_module.queue, "Queue", ObservedQueue)
    phases = []
    service = PromptPreparationService(
        model=StreamingModel(),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    service.prepare(
        root=tmp_path, original_prompt="Inspect evidence", answers=(), on_progress=phases.append
    )
    streamed = phases.index("receiving_preparation_response")
    assert "awaiting_model_response" not in phases[streamed:]


def test_evidence_cache_reuses_same_answers_and_invalidates_changed_context(tmp_path: Path):
    class RecordingIndex(EmptyKnowledgeIndex):
        def __init__(self):
            self.queries = []

        def search(self, query, filters=None, limit=5):
            self.queries.append(query)
            return ()

    index = RecordingIndex()
    decision = PreparationDecision(
        status="ready",
        summary="Ready",
        intent=ResolvedResearchIntent(
            task_kind="analysis",
            objective="Inspect research",
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([decision] * 4),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(index),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    answers = (ClarificationAnswer(question_id="material", answer="germanium"),)
    service.prepare(root=tmp_path, original_prompt="Analyze material", answers=answers)
    assert "germanium" in index.queries
    count = len(index.queries)
    service.prepare(root=tmp_path, original_prompt="Analyze material", answers=answers)
    assert len(index.queries) == count
    (tmp_path / "notes.md").write_text("New research context")
    service.prepare(root=tmp_path, original_prompt="Analyze material", answers=answers)
    assert len(index.queries) > count


def test_service_preserves_confirmed_fields_between_rounds(tmp_path: Path) -> None:
    previous = PreparationDecision(
        status="clarification",
        summary="Need a bias",
        questions=(
            ClarificationQuestion(
                id="bias", field_path="study.stop", prompt="End voltage?", reason="Sets range"
            ),
        ),
        unresolved_critical=("study.stop",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Measure transport",
            fields=(IntentField(path="regions.length", value="2 um", origin="researcher"),),
        ),
    )
    ready = PreparationDecision(
        status="ready",
        summary="Ready",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Measure transport",
            fields=(IntentField(path="study.stop", value="1 V", origin="researcher"),),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([ready]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    result = service.prepare(
        root=tmp_path,
        original_prompt="Measure transport",
        answers=(ClarificationAnswer(question_id="bias", answer="1 V"),),
        previous_decision=previous,
    )
    assert {field.path: field.value for field in result.decision.intent.fields} == {
        "regions.length": "2 um",
        "study.stop": "1 V",
    }


def test_literal_answers_update_typed_intent_without_another_model_call(tmp_path: Path):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    previous = PreparationDecision(
        status="clarification",
        summary="Frequency needed",
        questions=(
            ClarificationQuestion(
                id="frequency",
                field_path="study.frequency",
                prompt="Frequency in Hz?",
                reason="Sets the small signal analysis",
            ),
        ),
        unresolved_critical=("study.frequency",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Measure response",
            selected_capabilities=("study.ac",),
            fields=(
                IntentField(path="study.contact", value="drive", origin="researcher"),
                IntentField(path="study.amplitude", value="10 mV", origin="researcher"),
                IntentField(path="physics.temperature", value="300 K", origin="researcher"),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
        capability_catalog=CapabilityCatalog.from_manifest(
            CapabilityManifest.from_backend("devsim")
        ),
    )
    result = service.prepare(
        root=tmp_path,
        original_prompt="Measure response",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="frequency", answer="1 MHz"),),
    )
    assert result.decision.status == "ready"
    assert (
        next(
            field.value
            for field in result.decision.intent.fields
            if field.path == "study.frequency"
        )
        == "1 MHz"
    )


def test_service_returns_questions_without_compiling(tmp_path: Path) -> None:
    model = ScriptedPreparationModel(
        [
            PreparationDecision(
                status="clarification",
                summary="The temperature is required.",
                questions=(
                    ClarificationQuestion(
                        id="temperature",
                        field_path="study.temperature",
                        prompt="What temperature should be used?",
                        reason="Material properties and carrier statistics depend on it.",
                    ),
                ),
                unresolved_critical=("study.temperature",),
            )
        ]
    )
    service = PromptPreparationService(
        model=model,
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "d" * 64},
    )

    outcome = service.prepare(
        root=tmp_path, original_prompt="Simulate the requested structure", answers=()
    )

    assert outcome.decision.status == "clarification"
    assert outcome.compiled_request is None


def test_service_compiles_after_structured_answers(tmp_path: Path) -> None:
    ready = PreparationDecision(
        status="ready",
        summary="The researcher supplied the missing condition.",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Run the requested study at the confirmed temperature.",
            fields=(
                IntentField(
                    path="study.temperature",
                    value="300 K",
                    origin=IntentOrigin.RESEARCHER,
                ),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([ready]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "d" * 64},
    )

    outcome = service.prepare(
        root=tmp_path,
        original_prompt="Simulate the requested structure",
        answers=(ClarificationAnswer(question_id="temperature", answer="300 K"),),
    )

    assert outcome.compiled_request is not None
    assert outcome.compiled_request.answers[0].answer == "300 K"


def test_service_reports_safe_preparation_phases_in_order(tmp_path: Path) -> None:
    ready = PreparationDecision(
        status="ready",
        summary="The request is ready.",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Run the specified study.",
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([ready]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "d" * 64},
    )
    phases: list[str] = []

    service.prepare(
        root=tmp_path,
        original_prompt="Run the specified study",
        answers=(),
        on_progress=phases.append,
    )

    assert phases == [
        "reviewing_workspace",
        "consulting_local_knowledge",
        "reasoning_about_scientific_intent",
        "compiling_request",
    ]
