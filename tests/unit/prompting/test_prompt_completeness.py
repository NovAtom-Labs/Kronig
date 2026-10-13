from tcad_agent.capabilities.descriptors import CapabilityCatalog
from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.prompting.completeness import enforce_completeness, question_for_path
from tcad_agent.prompting.models import IntentField, PreparationDecision, ResolvedResearchIntent


def test_coupled_frequency_bounds_do_not_supply_missing_dc_bounds():
    decision = PreparationDecision(
        status="ready",
        summary="Frequency over bias",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Frequency over bias",
            selected_capabilities=("study.frequency", "study.dc"),
            fields=tuple(
                IntentField(path=path, value=value, origin="researcher")
                for path, value in (
                    ("physics.temperature", "300 K"),
                    ("study.contact", "gate"),
                    ("study.start", "100 Hz"),
                    ("study.stop", "1 MHz"),
                    ("study.points", 7),
                    ("study.amplitude", "10 mV"),
                    ("study.bias_schedule.step", "0.1 V"),
                )
            ),
        ),
    )
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    result = enforce_completeness(decision, catalog)
    assert result.status == "clarification"
    assert set(result.unresolved_critical) == {
        "study.bias_schedule.start",
        "study.bias_schedule.stop",
    }


def test_frequency_question_uses_selected_frequency_descriptor():
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    question = question_for_path("study.start", catalog, selected=("study.frequency",))
    assert "frequency" in question.prompt.lower()
    assert "Hz" in question.prompt


def test_explicit_temperature_schedule_does_not_reask_a_single_temperature():
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = PreparationDecision(
        status="ready",
        summary="Run the given temperatures",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Compare equilibrium temperatures",
            selected_capabilities=("study.temperature",),
            fields=(
                IntentField(
                    path="study.values", value=["280 K", "300 K", "320 K"], origin="researcher"
                ),
            ),
        ),
    )
    assert enforce_completeness(decision, catalog).status == "ready"
    from tcad_agent.prompting.models import ClarificationQuestion

    unresolved = decision.model_copy(
        update={
            "status": "clarification",
            "unresolved_critical": ("physics.temperature",),
            "questions": (
                ClarificationQuestion(
                    id="temperature",
                    field_path="physics.temperature",
                    prompt="Temperature?",
                    reason="Physical conditions",
                ),
            ),
            "intent": decision.intent.model_copy(
                update={"unresolved_critical": ("physics.temperature",)}
            ),
        }
    )
    ready = enforce_completeness(unresolved, catalog)
    assert ready.status == "ready"
    assert ready.intent.unresolved_critical == ()


def test_question_reason_never_displays_internal_schema_paths():
    from tcad_agent.prompting.completeness import readable_questions
    from tcad_agent.prompting.models import ClarificationQuestion

    decision = PreparationDecision(
        status="clarification",
        summary="Need frequency",
        unresolved_critical=("study.frequency",),
        questions=(
            ClarificationQuestion(
                id="frequency",
                field_path="study.frequency",
                prompt="Frequency for the dc_points sweep?",
                reason="study.frequency is required by study.ac.",
            ),
        ),
    )
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    result = readable_questions(decision, catalog)
    assert "study." not in result.questions[0].reason
    assert "dc_points" not in result.questions[0].prompt


def test_missing_sweep_step_and_ac_conditions_are_batched():
    decision = PreparationDecision(
        status="ready",
        summary="Run the specified analysis",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze a layered structure",
            selected_capabilities=("study.dc", "study.ac"),
            fields=tuple(
                IntentField(path=path, value=value, origin="researcher")
                for path, value in (
                    ("study.contact", "drive"),
                    ("study.start", "-2 V"),
                    ("study.stop", "2 V"),
                    ("physics.temperature", "300 K"),
                )
            ),
        ),
    )
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    result = enforce_completeness(decision, catalog)
    assert result.status == "clarification"
    assert set(result.unresolved_critical) == {
        "study.bias_schedule.step",
        "study.frequency",
        "study.amplitude",
    }
    assert result.intent.fields == decision.intent.fields
    assert all("study." not in question.prompt for question in result.questions)


def test_indexed_fields_use_scientific_labels():
    for path in ("studies.0.type", "study.dc_points.values_v"):
        question = question_for_path(path)
        assert "studies 0" not in question.prompt
        assert "values v" not in question.prompt
        assert "Please confirm the intended value or choice" not in question.prompt


def test_explicit_values_and_non_simulation_tasks_do_not_trigger_questions():
    decision = PreparationDecision(
        status="ready",
        summary="Inspect the files",
        intent=ResolvedResearchIntent(
            task_kind="repository_change",
            objective="Inspect the workspace",
        ),
    )
    assert enforce_completeness(decision, None) == decision


def test_structured_profile_and_contact_checks_do_not_reask_supplied_fields():
    decision = PreparationDecision(
        status="ready",
        summary="Ready",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Run transport",
            selected_capabilities=("profile.gaussian", "contact.ohmic"),
            fields=(
                IntentField(
                    path="profiles.implant.standard_deviation", value="0.25 um", origin="researcher"
                ),
                IntentField(path="contacts.left.kind", value="ohmic", origin="researcher"),
            ),
        ),
    )
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    assert enforce_completeness(decision, catalog).status == "ready"
