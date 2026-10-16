"""Semantic clarification safeguards exercise the real preparation service."""

import pytest

from tcad_agent.capabilities.descriptors import CapabilityCatalog
from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.context import LocalEvidenceCollector, WorkspaceContextCollector
from tcad_agent.prompting.errors import ModelResponseError
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    ClarificationQuestion,
    IntentField,
    PreparationDecision,
    ResolvedResearchIntent,
)
from tcad_agent.prompting.service import PromptPreparationService, ScriptedPreparationModel


class EmptyKnowledge:
    def search(self, query, filters=None, limit=5):
        return ()


def service(decision):
    return PromptPreparationService(
        model=ScriptedPreparationModel([decision]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledge()),
        compiler=PromptCompiler(),
        capability_hashes={},
        capability_catalog=CapabilityCatalog.from_manifest(
            CapabilityManifest.from_backend("devsim")
        ),
    )


def decision(path="regions.structure", **question_fields):
    question = ClarificationQuestion(
        id="details",
        field_path=path,
        prompt="Please clarify this scientific input.",
        reason="The input affects the requested analysis.",
        **question_fields,
    )
    return PreparationDecision(
        status="clarification",
        summary="Input needed",
        questions=(question,),
        unresolved_critical=(path,),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Evaluate the structure",
            selected_capabilities=("study.equilibrium",),
            fields=(IntentField(path="physics.temperature", value="315 K", origin="researcher"),),
        ),
    )


def test_question_ids_must_be_unique_within_one_revision():
    payload = decision().model_dump(mode="json")
    second = {**payload["questions"][0], "field_path": "contacts.boundary_conditions"}
    payload["questions"].append(second)
    with pytest.raises(ValueError, match="unique question ids"):
        PreparationDecision.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        "physics.electron_mobility",
        "physics.constant_mobility.electron_mobility",
        "physics.models.constant_mobility.electron_mobility",
    ],
)
@pytest.mark.parametrize("value", ["0.135 m^2/V/s", 0.135])
def test_unsupported_explicit_physics_parameters_stop_before_planning(tmp_path, path, value):
    prepared = PreparationDecision(
        status="ready",
        summary="Use the requested parameters",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compute current",
            fields=(IntentField(path=path, value=value, origin="researcher"),),
        ),
    )
    outcome = service(prepared).prepare(
        root=tmp_path, original_prompt="Use 0.135 m^2/V/s", answers=()
    )
    assert outcome.decision.status == "blocked"
    assert path in outcome.decision.summary
    assert outcome.compiled_request is None


def test_unit_reformatting_is_not_a_changed_scientific_dependency():
    from tcad_agent.prompting.clarifications import validate_questions

    previous = decision("physics.temperature")
    changed = decision(
        "regions.structure",
        reason_kind="dependency_changed",
        dependency_fields=("physics.temperature",),
    )
    intent = changed.intent.model_copy(
        update={
            "fields": (
                IntentField(path="physics.temperature", value="315 kelvin", origin="researcher"),
            )
        }
    )
    changed = changed.model_copy(update={"intent": intent})
    with pytest.raises(ValueError, match="actual changed input"):
        validate_questions(changed, "Use 315 K", (), None, previous)


def test_model_names_that_are_also_unit_names_are_not_quantity_overrides():
    from tcad_agent.prompting.authority import unsupported_physics_inputs

    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Use Fermi statistics",
        fields=(
            IntentField(
                path="physics.models", value=["fermi", "constant_mobility"], origin="researcher"
            ),
        ),
    )
    assert unsupported_physics_inputs(intent) == []


def test_no_progress_after_an_answer_stops_instead_of_repeating_the_question(tmp_path):
    previous = decision()
    with pytest.raises(ModelResponseError, match="did not resolve"):
        service(previous).prepare(
            root=tmp_path,
            original_prompt="Evaluate this structure",
            previous_decision=previous,
            answers=(ClarificationAnswer(question_id="details", answer="Use a 3 um silicon slab"),),
        )


def test_a_confirmed_value_needs_a_specific_reason_to_be_questioned_again(tmp_path):
    with pytest.raises(ModelResponseError, match="already confirmed"):
        service(decision("physics.temperature")).prepare(
            root=tmp_path, original_prompt="Use 315 K", answers=()
        )


def test_conflict_cannot_be_justified_with_invented_researcher_quotes(tmp_path):
    conflicting = decision(
        "physics.temperature", reason_kind="conflict", evidence_quotes=("300 K", "350 K")
    )
    with pytest.raises(ModelResponseError, match="researcher"):
        service(conflicting).prepare(root=tmp_path, original_prompt="Use 315 K", answers=())


def test_genuine_conflicting_researcher_values_still_require_clarification(tmp_path):
    conflicting = decision(
        "physics.temperature", reason_kind="conflict", evidence_quotes=("300 K", "350 K")
    )
    result = service(conflicting).prepare(
        root=tmp_path,
        original_prompt="My note says 300 K but the measurement says 350 K. Which should we use?",
        answers=(),
    )
    assert result.decision.status == "clarification"
    assert result.compiled_request is None


def test_invalid_new_answer_can_be_corrected_without_hiding_the_unit_error(tmp_path):
    previous = decision("physics.temperature")
    invalid = decision("physics.temperature", reason_kind="invalid", evidence_quotes=("300 V",))
    result = service(invalid).prepare(
        root=tmp_path,
        original_prompt="Use 315 K initially",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="details", answer="Change it to 300 V"),),
    )
    assert result.decision.status == "clarification"
    assert result.decision.questions[0].reason_kind == "invalid"


def test_historical_id_does_not_authorize_changing_an_unanswered_optional_field(tmp_path):
    previous = decision()
    optional = previous.questions[0].model_copy(update={"id": "setting", "required": False})
    current = optional.model_copy(
        update={"id": "boundary", "field_path": "study.contact", "required": True}
    )
    previous = previous.model_copy(
        update={
            "questions": (optional, current),
            "intent": previous.intent.model_copy(
                update={
                    "fields": (
                        *previous.intent.fields,
                        IntentField(
                            path="regions.structure", value="3 um silicon slab", origin="researcher"
                        ),
                    )
                }
            ),
        }
    )
    proposed = PreparationDecision(
        status="ready",
        summary="Ready",
        intent=previous.intent.model_copy(
            update={
                "fields": (
                    previous.intent.fields[0],
                    IntentField(
                        path="regions.structure", value="5 um silicon slab", origin="researcher"
                    ),
                    IntentField(path="study.contact", value="right", origin="researcher"),
                )
            }
        ),
    )
    old = ClarificationAnswer.model_construct(
        question_id="setting",
        answer="315 K",
        field_path="physics.temperature",
        question_prompt="Temperature?",
        question_revision=1,
    )
    latest = ClarificationAnswer.model_construct(
        question_id="boundary",
        answer="right",
        field_path="study.contact",
        question_prompt="Boundary?",
        question_revision=3,
    )
    result = service(proposed).prepare(
        root=tmp_path,
        original_prompt="Use a 3 um slab at 315 K",
        previous_decision=previous,
        answers=(old, latest),
    )
    assert (
        next(f.value for f in result.decision.intent.fields if f.path == "regions.structure")
        == "3 um silicon slab"
    )


@pytest.mark.parametrize("old_left", [None, 4.1])
def test_literal_contact_correction_removes_only_the_old_aggregate_slice(tmp_path, old_left):
    previous = decision("contacts.left.work_function", reason_kind="missing")
    previous = previous.model_copy(
        update={
            "intent": previous.intent.model_copy(
                update={
                    "selected_capabilities": ("contact.metal_work_function", "study.equilibrium"),
                    "fields": (
                        *previous.intent.fields,
                        IntentField(
                            path="contacts.work_function",
                            value={"left_eV": old_left, "right_eV": 4.4},
                            origin="researcher",
                        ),
                    ),
                }
            )
        }
    )
    result = service(previous).prepare(
        root=tmp_path,
        original_prompt="Change only the left contact",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="details", answer="4.2 eV"),),
    )
    assert result.decision.status == "ready"
    fields = {field.path: field.value for field in result.decision.intent.fields}
    assert fields["contacts.work_function"] == {"right_eV": 4.4}
    assert fields["contacts.left.work_function"] == "4.2 eV"


def test_corrected_input_cannot_be_questioned_using_a_superseded_invalid_answer(tmp_path):
    invalid = decision("physics.temperature", reason_kind="invalid", evidence_quotes=("300 V",))
    answers = tuple(
        ClarificationAnswer.model_construct(
            question_id="details",
            answer=text,
            field_path="physics.temperature",
            question_prompt="Temperature?",
            question_revision=revision,
        )
        for revision, text in ((1, "300 V"), (3, "Please use 315 K"))
    )
    with pytest.raises(ModelResponseError, match="researcher"):
        service(invalid).prepare(
            root=tmp_path,
            original_prompt="Evaluate at the temperature I choose",
            previous_decision=decision("physics.temperature"),
            answers=answers,
        )


def test_analysis_change_replaces_dependent_bounds_but_keeps_unrelated_physics(tmp_path):
    previous = decision("study.kind")
    previous = previous.model_copy(
        update={
            "intent": previous.intent.model_copy(
                update={
                    "selected_capabilities": ("study.frequency", "model.fermi"),
                    "fields": (
                        *previous.intent.fields,
                        IntentField(path="study.kind", value="frequency", origin="researcher"),
                        IntentField(path="study.start", value="1 kHz", origin="researcher"),
                        IntentField(path="study.stop", value="1 MHz", origin="researcher"),
                        IntentField(path="study.contact", value="gate", origin="researcher"),
                        IntentField(path="physics.models", value=["fermi"], origin="researcher"),
                    ),
                }
            )
        }
    )
    current = PreparationDecision(
        status="ready",
        summary="Voltage sweep",
        intent=previous.intent.model_copy(
            update={
                "selected_capabilities": ("study.dc", "model.fermi"),
                "fields": tuple(
                    IntentField(path=path, value=value, origin="researcher")
                    for path, value in (
                        ("study.kind", "dc"),
                        ("study.contact", "gate"),
                        ("study.start", "0 V"),
                        ("study.stop", "1 V"),
                        ("study.step", "0.1 V"),
                    )
                ),
            }
        ),
    )
    result = service(current).prepare(
        root=tmp_path,
        original_prompt="Change my analysis",
        previous_decision=previous,
        answers=(
            ClarificationAnswer(
                question_id="details", answer="Use DC from 0 to 1 V in 0.1 V steps"
            ),
        ),
    )
    assert result.decision.status == "ready"
    fields = {field.path: field.value for field in result.decision.intent.fields}
    assert fields["study.start"] == "0 V"
    assert fields["study.stop"] == "1 V"
    assert fields["physics.temperature"] == "315 K"
    assert fields["physics.models"] == ["fermi"]


def test_bare_scalar_uses_a_unit_only_when_the_question_explicitly_stated_it(tmp_path):
    previous = decision("physics.temperature", reason_kind="missing")
    previous = previous.model_copy(
        update={
            "questions": (
                previous.questions[0].model_copy(update={"prompt": "What temperature in K?"}),
            )
        }
    )
    result = service(previous).prepare(
        root=tmp_path,
        original_prompt="Set the temperature",
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="details", answer="320"),),
    )
    from tcad_agent.domain.units import QuantityValue

    assert QuantityValue.model_validate(result.decision.intent.fields[0].value).to("K") == 320
