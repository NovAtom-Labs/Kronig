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


@pytest.mark.parametrize("new_right", [4.4, 4.5])
def test_current_aggregate_keeps_answered_slice_and_retains_unchanged_previous_slice(
    tmp_path, new_right
):
    previous = PreparationDecision(
        status="clarification",
        summary="Confirm left contact",
        questions=(
            ClarificationQuestion(
                id="left",
                field_path="contacts.left.work_function",
                prompt="Left work function?",
                reason="Boundary condition",
            ),
        ),
        unresolved_critical=("contacts.left.work_function",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            fields=(
                IntentField(
                    path="contacts.work_function",
                    value={"left_eV": None, "right_eV": 4.4},
                    origin="researcher",
                ),
            ),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="Left contact confirmed",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            fields=(
                IntentField(
                    path="contacts.work_function",
                    value={"left_eV": 4.2, "right_eV": new_right},
                    origin="researcher",
                ),
            ),
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
        original_prompt="Analyze transport",
        previous_decision=previous,
        answers=(
            ClarificationAnswer(question_id="left", answer="Use 4.2 eV for the left contact"),
        ),
    )
    assert next(
        f.value for f in result.decision.intent.fields if f.path == "contacts.work_function"
    ) == {
        "left_eV": 4.2,
        "right_eV": 4.4,
    }


def test_indexed_quantity_list_keeps_unmodified_entries_after_a_scoped_answer(tmp_path):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    previous = PreparationDecision(
        status="clarification",
        summary="Confirm first contact",
        questions=(
            ClarificationQuestion(
                id="first",
                field_path="contacts.0.work_function",
                prompt="First work function?",
                reason="Boundary condition",
            ),
        ),
        unresolved_critical=("contacts.0.work_function",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(
                IntentField(path="contacts.work_function", value=[None, 4.4], origin="researcher"),
            ),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="First contact confirmed",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(
                IntentField(path="contacts.0.work_function", value="4.2 eV", origin="researcher"),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([current]),
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
        original_prompt="Analyze transport",
        previous_decision=previous,
        answers=(
            ClarificationAnswer(question_id="first", answer="Use 4.2 eV for the first contact"),
        ),
    )
    assert result.decision.status == "ready"
    assert {f.path: f.value for f in result.decision.intent.fields} == {
        "contacts.0.work_function": "4.2 eV",
        "contacts.work_function": {"1": 4.4},
    }


def test_unit_only_answer_does_not_turn_a_previous_number_into_one_unit(tmp_path):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    previous = PreparationDecision(
        status="clarification",
        summary="Confirm the quantity unit",
        questions=(
            ClarificationQuestion(
                id="unit",
                field_path="contacts.work_function",
                prompt="Which unit applies to the number?",
                reason="Unit is ambiguous",
            ),
        ),
        unresolved_critical=("contacts.work_function",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(IntentField(path="contacts.work_function", value=4.35, origin="researcher"),),
        ),
    )
    ready = PreparationDecision(
        status="ready",
        summary="Units confirmed",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(
                IntentField(path="contacts.work_function", value="4.35 eV", origin="researcher"),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([ready]),
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
        original_prompt="Use a work function of 4.35",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="unit", answer="eV"),),
    )
    assert result.decision.status == "ready"
    assert (
        next(f.value for f in result.decision.intent.fields if f.path == "contacts.work_function")
        == "4.35 eV"
    )


def test_stale_checker_questions_are_reconciled_with_confirmed_previous_values(tmp_path):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest
    from tcad_agent.prompting.completeness import question_for_path

    catalog = CapabilityCatalog.from_manifest(CapabilityManifest.from_backend("devsim"))

    previous = PreparationDecision(
        status="clarification",
        summary="Temperature needed",
        questions=(
            ClarificationQuestion(
                id="temperature",
                field_path="physics.temperature",
                prompt="Temperature?",
                reason="Physical conditions",
            ),
        ),
        unresolved_critical=("physics.temperature",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze the layered structure",
            selected_capabilities=("contact.metal_work_function", "study.equilibrium"),
            fields=(
                IntentField(
                    path="contacts.work_function", value={"left_eV": 4.35}, origin="researcher"
                ),
            ),
        ),
    )
    repeated = PreparationDecision(
        status="clarification",
        summary="Confirm work function",
        questions=(
            question_for_path(
                "contacts.work_function",
                catalog.public_view(),
                selected=("contact.metal_work_function", "study.equilibrium"),
            ),
        ),
        unresolved_critical=("contacts.work_function",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze the layered structure",
            selected_capabilities=("contact.metal_work_function", "study.equilibrium"),
            fields=(IntentField(path="physics.temperature", value="315 K", origin="researcher"),),
            unresolved_critical=("contacts.work_function",),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([repeated]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
        capability_catalog=catalog,
    )
    result = service.prepare(
        root=tmp_path,
        original_prompt="Use a 4.35 eV metal contact",
        answers=(ClarificationAnswer(question_id="temperature", answer="Use 315 K throughout"),),
        previous_decision=previous,
    )
    assert result.decision.status == "ready"
    assert result.compiled_request is not None
    fields = {field.path: field.value for field in result.compiled_request.decision.intent.fields}
    assert fields["contacts.work_function"] == {"left_eV": 4.35}
    assert fields["physics.temperature"] == "315 K"


def test_one_contact_answer_retains_the_other_contacts_confirmed_value(tmp_path):
    previous = PreparationDecision(
        status="clarification",
        summary="Left contact input is needed",
        questions=(
            ClarificationQuestion(
                id="left",
                field_path="contacts.0.work_function",
                prompt="Left contact work function?",
                reason="Boundary condition",
            ),
        ),
        unresolved_critical=("contacts.0.work_function",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            fields=(
                IntentField(path="contacts.1.work_function", value="4.4 eV", origin="researcher"),
            ),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="Left contact input supplied",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            fields=(
                IntentField(path="contacts.0.work_function", value="4.2 eV", origin="researcher"),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([current]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    outcome = service.prepare(
        root=tmp_path,
        original_prompt="Analyze transport",
        previous_decision=previous,
        answers=(
            ClarificationAnswer(question_id="left", answer="Use 4.2 eV for the left contact"),
        ),
    )
    assert {field.path: field.value for field in outcome.decision.intent.fields} == {
        "contacts.0.work_function": "4.2 eV",
        "contacts.1.work_function": "4.4 eV",
    }


def test_literal_answers_do_not_clear_unasked_contacts_in_the_next_batch(tmp_path):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    paths = tuple(f"contacts.{index}.work_function" for index in range(8))
    previous = PreparationDecision(
        status="clarification",
        summary="Contact values needed",
        questions=tuple(
            ClarificationQuestion(
                id=f"contact_{i}",
                field_path=path,
                prompt="Contact work function?",
                reason="Boundary condition",
            )
            for i, path in enumerate(paths[:7])
        ),
        unresolved_critical=paths,
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            unresolved_critical=paths,
        ),
    )
    pending = PreparationDecision(
        status="clarification",
        summary="One contact is still missing",
        questions=(
            ClarificationQuestion(
                id="contact_7",
                field_path=paths[7],
                prompt="Last contact work function?",
                reason="Boundary condition",
            ),
        ),
        unresolved_critical=(paths[7],),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=tuple(
                IntentField(path=path, value="4.35 eV", origin="researcher") for path in paths[:7]
            ),
            unresolved_critical=(paths[7],),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([pending]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={},
        capability_catalog=CapabilityCatalog.from_manifest(
            CapabilityManifest.from_backend("devsim")
        ),
    )
    outcome = service.prepare(
        root=tmp_path,
        original_prompt="Analyze transport",
        previous_decision=previous,
        answers=tuple(
            ClarificationAnswer(question_id=f"contact_{i}", answer="4.35 eV") for i in range(7)
        ),
    )
    assert outcome.decision.status == "clarification"
    assert outcome.decision.unresolved_critical == (paths[7],)
    assert outcome.decision.questions[0].field_path == paths[7]


@pytest.mark.parametrize("old_left", [None, 4.1])
@pytest.mark.parametrize("other", ["right_eV", "left_aux_eV"])
def test_scoped_contact_answer_replaces_only_its_slice_of_a_retained_aggregate(
    tmp_path, old_left, other
):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    previous = PreparationDecision(
        status="clarification",
        summary="Left contact needs confirmation",
        questions=(
            ClarificationQuestion(
                id="left",
                field_path="contacts.left.work_function",
                prompt="Left contact work function?",
                reason="Boundary condition",
            ),
        ),
        unresolved_critical=("contacts.left.work_function",),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(
                IntentField(
                    path="contacts.work_function",
                    value={"left_eV": old_left, other: 4.4},
                    origin="researcher",
                ),
            ),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="Left input supplied",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(
                IntentField(
                    path="contacts.left.work_function", value="4.2 eV", origin="researcher"
                ),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([current]),
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
        original_prompt="Analyze transport",
        previous_decision=previous,
        answers=(
            ClarificationAnswer(question_id="left", answer="Use 4.2 eV for the left contact"),
        ),
    )
    assert result.decision.status == "ready"
    assert {field.path: field.value for field in result.decision.intent.fields} == {
        "contacts.left.work_function": "4.2 eV",
        "contacts.work_function": {other: 4.4},
    }


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


def test_expert_statistics_choice_can_be_reconsidered_after_intake_answers(tmp_path):
    from tcad_agent.prompting.models import EvidenceExcerpt

    class EvidenceCollector:
        index = None

        def collect(self, *_args):
            return (
                EvidenceExcerpt(
                    id="guide",
                    title="Carrier statistics",
                    url="https://example.org/statistics",
                    version="1",
                    content_hash="a" * 64,
                    reviewed=True,
                    content="Bias-induced surface populations may require Fermi statistics.",
                ),
            )

    previous = PreparationDecision(
        status="clarification",
        summary="Confirm operating conditions",
        unresolved_critical=("study.type",),
        questions=(
            ClarificationQuestion(
                id="method",
                field_path="study.type",
                prompt="Measurement method?",
                reason="Physical study",
            ),
        ),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Charge response",
            selected_capabilities=("model.boltzmann",),
            fields=(
                IntentField(
                    path="physics.models",
                    value=["boltzmann"],
                    origin="evidence",
                    rationale="Initial low injection estimate",
                    evidence_refs=("guide",),
                ),
            ),
        ),
    )
    current = PreparationDecision(
        status="ready",
        summary="Strong accumulation requires Fermi",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Charge response",
            selected_capabilities=("model.fermi",),
            fields=(
                IntentField(
                    path="physics.models",
                    value=["fermi"],
                    origin="evidence",
                    rationale="Whole bias range can be degenerate",
                    evidence_refs=("guide",),
                ),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([current]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=EvidenceCollector(),
        compiler=PromptCompiler(),
        capability_hashes={},
    )
    result = service.prepare(
        root=tmp_path,
        original_prompt="Charge response",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="method", answer="Use quasi-static extraction"),),
    )
    assert "model.fermi" in result.decision.intent.selected_capabilities
    assert "model.boltzmann" not in result.decision.intent.selected_capabilities


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
