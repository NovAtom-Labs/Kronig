import pytest

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


def test_structured_quantity_with_contact_identity_does_not_reask_work_function():
    from tcad_agent.prompting.completeness import _dimension_matches

    assert _dimension_matches(
        {"contact": "gate", "value": 4.1, "unit": "eV"}, "eV", ambiguous=False
    )
    assert not _dimension_matches({"value": 4.1, "unit": "V"}, "eV", ambiguous=False)


@pytest.mark.parametrize(
    ("capability", "path", "value"),
    [
        ("contact.metal_work_function", "contacts.work_function", {"gate_eV": 4.1}),
        (
            "contact.metal_work_function",
            "contacts.work_function",
            [
                {"contact": "left", "work_function": "4.25 eV"},
                {"contact": "right", "work_function": "4.4 eV"},
            ],
        ),
        (
            "material.generic_dielectric",
            "regions.relative_permittivity",
            [{"region": "insulator", "relative_permittivity": 7.2}],
        ),
        ("study.equilibrium", "physics.temperature", {"temperature_K": 315}),
    ],
)
def test_scoped_quantities_do_not_become_missing_researcher_inputs(capability, path, value):
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = PreparationDecision(
        status="clarification",
        summary="A supplied input was marked unresolved",
        questions=(question_for_path(path, catalog, selected=(capability,)),),
        unresolved_critical=(path,),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze the layered structure",
            selected_capabilities=(capability,),
            fields=(
                IntentField(path=path, value=value, origin="researcher"),
                IntentField(
                    path="regions.material", value="generic_dielectric", origin="researcher"
                ),
            ),
            unresolved_critical=(path,),
        ),
    )
    checked = enforce_completeness(decision, catalog)
    assert checked.status == "ready"
    assert checked.questions == ()
    assert checked.unresolved_critical == ()
    assert checked.intent.unresolved_critical == ()
    assert checked.intent.fields == decision.intent.fields


@pytest.mark.parametrize(
    "value",
    [
        {"gate_V": 4.1},
        [{"contact": "gate"}],
        [
            {"contact": "left", "work_function": "4.2 eV"},
            {"contact": "right", "work_function": None},
        ],
        {"value": 4.1, "unit": "V"},
        {"gate_eV": float("inf")},
        {"gate_eV": True},
    ],
)
def test_invalid_or_partial_scoped_quantities_still_need_clarification(value):
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = PreparationDecision(
        status="ready",
        summary="Check the supplied values",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(IntentField(path="contacts.work_function", value=value, origin="researcher"),),
        ),
    )
    checked = enforce_completeness(decision, catalog)
    assert checked.status == "clarification"
    assert "contacts.work_function" in checked.unresolved_critical


def test_resolved_input_is_removed_without_hiding_a_different_missing_input():
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    paths = ("contacts.work_function", "physics.temperature")
    decision = PreparationDecision(
        status="clarification",
        summary="Resolve physical conditions",
        unresolved_critical=paths,
        questions=tuple(
            question_for_path(
                path, catalog, selected=("contact.metal_work_function", "study.equilibrium")
            )
            for path in paths
        ),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function", "study.equilibrium"),
            fields=(
                IntentField(path="contacts.work_function", value="4.35 eV", origin="researcher"),
            ),
            unresolved_critical=paths,
        ),
    )
    checked = enforce_completeness(decision, catalog)
    assert checked.status == "clarification"
    assert checked.unresolved_critical == ("physics.temperature",)
    assert tuple(q.field_path for q in checked.questions) == ("physics.temperature",)


@pytest.mark.parametrize(
    "paths",
    [
        ("contacts.left.work_function", "contacts.right.work_function"),
        ("contacts.0.work_function", "contacts.1.work_function"),
    ],
)
def test_one_valid_contact_does_not_hide_a_second_unresolved_contact(paths):
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = PreparationDecision(
        status="ready",
        summary="Check both contacts",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(
                IntentField(path=paths[0], value=None, origin="researcher"),
                IntentField(path=paths[1], value="4.4 eV", origin="researcher"),
            ),
        ),
    )
    checked = enforce_completeness(decision, catalog)
    assert checked.status == "clarification"
    assert "contacts.work_function" in checked.unresolved_critical


@pytest.mark.parametrize(
    ("missing", "provided", "value"),
    [
        ("contacts.0.work_function", "contacts.1.work_function", "4.4 eV"),
        ("contacts.left.work_function", "contacts.work_function", {"right_eV": 4.4}),
        ("contacts.left.work_function", "contacts.work_function", {"left_aux_eV": 4.4}),
    ],
)
def test_other_contact_value_cannot_answer_a_scoped_question(missing, provided, value):
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = PreparationDecision(
        status="clarification",
        summary="One contact input is missing",
        questions=(question_for_path(missing, catalog, selected=("contact.metal_work_function",)),),
        unresolved_critical=(missing,),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(IntentField(path=provided, value=value, origin="researcher"),),
            unresolved_critical=(missing,),
        ),
    )
    checked = enforce_completeness(decision, catalog)
    assert checked.status == "clarification"
    assert missing in checked.unresolved_critical
    assert any(q.field_path == missing for q in checked.questions)


def test_coupled_frequency_and_voltage_bounds_do_not_contaminate_each_other():
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = PreparationDecision(
        status="ready",
        summary="Measure frequency over DC biases",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Measure frequency over DC biases",
            selected_capabilities=("study.frequency", "study.dc"),
            fields=tuple(
                IntentField(path=path, value=value, origin="researcher")
                for path, value in (
                    ("physics.temperature", "300 K"),
                    ("study.contact", "drive"),
                    ("study.start", "100 Hz"),
                    ("study.stop", "1 MHz"),
                    ("study.points", 5),
                    ("study.amplitude", "10 mV"),
                    ("study.bias_schedule.contact", "drive"),
                    ("study.bias_schedule.start", "-1 V"),
                    ("study.bias_schedule.stop", "1 V"),
                    ("study.bias_schedule.step", "0.1 V"),
                )
            ),
        ),
    )
    checked = enforce_completeness(decision, catalog)
    assert checked.status == "ready"
    assert checked.questions == ()
    assert checked.intent.fields == decision.intent.fields


@pytest.mark.parametrize(
    "value",
    [
        {"left_eV": 4.35, "right_eV": 4.4},
        [
            {"contact": "left", "work_function": "4.35 eV"},
            {"contact": "right", "work_function": "4.4 eV"},
        ],
    ],
)
def test_scoped_question_can_use_its_own_quantity_in_an_aggregate_record(value):
    path = "contacts.left.work_function"
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = PreparationDecision(
        status="clarification",
        summary="Check this contact",
        questions=(question_for_path(path, catalog, selected=("contact.metal_work_function",)),),
        unresolved_critical=(path,),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(IntentField(path="contacts.work_function", value=value, origin="researcher"),),
            unresolved_critical=(path,),
        ),
    )
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    assert enforce_completeness(decision, catalog).status == "ready"


def test_indexed_missing_contact_questions_keep_distinct_ids_and_scopes():
    from tcad_agent.prompting.models import ClarificationQuestion

    paths = ("contacts.0.work_function", "contacts.1.work_function")
    decision = PreparationDecision(
        status="clarification",
        summary="Two contact inputs missing",
        questions=tuple(
            ClarificationQuestion(
                id=f"contact_{i}",
                field_path=path,
                prompt="Contact work function?",
                reason="Boundary condition",
            )
            for i, path in enumerate(paths)
        ),
        unresolved_critical=paths,
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            unresolved_critical=paths,
        ),
    )
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    checked = enforce_completeness(decision, catalog)
    assert tuple(q.field_path for q in checked.questions) == paths
    assert tuple(q.id for q in checked.questions) == ("contact_0", "contact_1")


@pytest.mark.parametrize(
    "value",
    [
        4.1,
        [
            {"contact": "gate", "work_function": "4.1 eV"},
            {"contact": "gate", "work_function": "4.4 eV"},
        ],
    ],
)
def test_model_owned_unit_or_value_conflicts_are_not_dismissed_by_quantity_presence(value):
    from tcad_agent.prompting.models import ClarificationQuestion

    path = "contacts.work_function"
    decision = PreparationDecision(
        status="clarification",
        summary="Resolve conflicting inputs",
        questions=(
            ClarificationQuestion(
                id="resolve_contact",
                field_path=path,
                prompt="Which value and unit should be used?",
                reason="The supplied inputs are conflicting or unit-ambiguous",
            ),
        ),
        unresolved_critical=(path,),
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Analyze transport",
            selected_capabilities=("contact.metal_work_function",),
            fields=(IntentField(path=path, value=value, origin="researcher"),),
            unresolved_critical=(path,),
        ),
    )
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    checked = enforce_completeness(decision, catalog)
    assert checked.status == "clarification"
    assert checked.questions == decision.questions
