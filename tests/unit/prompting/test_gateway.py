from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from openhands.sdk import Message, TextContent

from tcad_agent.prompting.gateway import (
    ModelResponseError,
    OpenHandsPreparationModel,
)
from tcad_agent.prompting.models import EvidenceExcerpt, WorkspaceContext, WorkspaceFileContext


@pytest.mark.parametrize("reference", ["repo/reference.md#temperature",
                                       "repository:reference.md#temperature",
                                       "reference.md; confirmed from the temperature table"])
def test_repository_reference_uses_known_workspace_relative_path_without_retry(reference):
    context = workspace().model_copy(
        update={
            "files": (
                WorkspaceFileContext(
                    path="reference.md", size=32, sha256="b" * 64, text_excerpt="Temperature300 K"
                ),
            )
        }
    )
    response = json.dumps(
        {
            "status": "ready",
            "summary": "Use the supplied study",
            "intent": {
                "task_kind": "simulation",
                "objective": "Repeat study",
                "fields": [
                    {
                        "path": "physics.temperature",
                        "value": "300 K",
                        "origin": "repository",
                        "source_reference": reference,
                    }
                ],
            },
        }
    )
    llm = ScriptedLLM([response])
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Repeat study", answers=(), workspace=context, evidence=()
    )
    assert decision.intent.fields[0].source_reference == (
        "reference.md" if ";" in reference else "reference.md#temperature"
    )
    if ";" in reference:
        assert "confirmed from the temperature table" in decision.intent.fields[0].rationale
    assert len(llm.messages) == 1


class ScriptedLLM:
    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = responses
        self.messages: list[list[Message]] = []
        self.model = "test/preparation-model"

    def completion(self, messages):
        self.messages.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(
            message=Message(role="assistant", content=[TextContent(text=response)])
        )


@pytest.mark.parametrize("value,origin", [(6.97e-19, "repository"),
                                         ("4.35 eV (both contacts)", "researcher")])
@pytest.mark.parametrize("status", ["ready", "clarification"])
def test_malformed_known_physical_quantity_is_repaired_not_reasked(value, origin, status):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    context = workspace().model_copy(update={"files": (WorkspaceFileContext(
        path="reference.md", size=40, sha256="b" * 64,
        text_excerpt="Contact work function: 4.35 eV",
    ),)})
    payload = {"status": status, "summary": "Use the confirmed contact",
               "intent": {"task_kind": "simulation", "objective": "Repeat contact study",
                          "selected_capabilities": ["contact.metal_work_function"],
                          "fields": [{"path": "contacts.work_function", "value": value,
                                      "origin": origin,
                                      "source_reference": (
                                          "reference.md" if origin == "repository" else None)}]}}
    if status == "clarification":
        payload["questions"] = [{"id": "temperature", "field_path": "physics.temperature",
                                 "prompt": "What temperature?", "reason": "Sets the study"}]
        payload["unresolved_critical"] = ["physics.temperature"]
        payload["intent"]["unresolved_critical"] = ["physics.temperature"]
    valid = json.loads(json.dumps(payload))
    valid["intent"]["fields"][0]["value"] = "4.35 eV"
    llm = ScriptedLLM([json.dumps(payload), json.dumps(valid)])
    catalog = CapabilityCatalog.from_manifest(
        CapabilityManifest.from_backend("devsim")
    ).public_view()
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Use the same 4.35 eV contact", answers=(), workspace=context,
        evidence=(), capabilities=catalog,
    )
    assert len(llm.messages) == 2
    assert decision.intent.fields[0].value == "4.35 eV"


def workspace() -> WorkspaceContext:
    return WorkspaceContext(
        display_name="repo",
        git_available=False,
        git_dirty=False,
        inventory_hash="a" * 64,
    )


@pytest.mark.parametrize("suffix", ["ev", "eV"])
def test_explicit_unit_suffix_is_normalized_without_another_model_call(suffix):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    payload = {"status": "ready", "summary": "Confirmed contact", "intent": {
        "task_kind": "simulation", "objective": "Analyze contact",
        "selected_capabilities": ["contact.metal_work_function"], "fields": [
            {"path": f"contacts.0.work_function_{suffix}", "value": 4.35,
             "origin": "researcher"},
        ],
    }}
    corrected = json.loads(json.dumps(payload))
    corrected["intent"]["fields"][0].update(
        path="contacts.0.work_function", value={"magnitude": 4.35, "unit": "eV"}
    )
    llm = ScriptedLLM([json.dumps(payload), json.dumps(corrected)])
    result = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Use a 4.35 eV contact", answers=(), workspace=workspace(), evidence=(),
        capabilities=CapabilityCatalog.from_manifest(
            CapabilityManifest.from_backend("devsim")
        ).public_view(),
    )
    assert len(llm.messages) == 1
    assert result.intent.fields[0].path == "contacts.0.work_function"
    from tcad_agent.domain.units import QuantityValue

    quantity = QuantityValue.model_validate(result.intent.fields[0].value)
    assert quantity.to("eV") == pytest.approx(4.35)


@pytest.mark.parametrize("source", ["Temperature: `300 kelvin`", "Temperature: 300 K",
                                   "Temperature: 300K"])
def test_repository_numeric_units_are_recovered_only_from_unique_cited_quantities(source):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest
    from tcad_agent.domain.units import QuantityValue

    context = workspace().model_copy(update={"files": (WorkspaceFileContext(
        path="reference.md", size=len(source), sha256="b" * 64, text_excerpt=source,
    ),)})
    payload = {"status": "ready", "summary": "Repeat supplied conditions", "intent": {
        "task_kind": "simulation", "objective": "Repeat conditions",
        "selected_capabilities": ["study.equilibrium"], "fields": [
            {"path": "physics.temperature", "value": 300, "origin": "repository",
             "source_reference": "reference.md"},
        ],
    }}
    llm = ScriptedLLM([json.dumps(payload)] * 2)
    result = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Repeat the saved study", answers=(), workspace=context, evidence=(),
        capabilities=CapabilityCatalog.from_manifest(
            CapabilityManifest.from_backend("devsim")
        ).public_view(),
    )
    assert len(llm.messages) == 1
    assert QuantityValue.model_validate(result.intent.fields[0].value).to("K") == 300


def test_repository_voltage_lists_preserve_each_signed_source_quantity():
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest
    from tcad_agent.domain.units import QuantityValue

    source = "Requested operating points: `2 V`, `-2 V`."
    context = workspace().model_copy(update={"files": (WorkspaceFileContext(
        path="reference.md", size=len(source), sha256="b" * 64, text_excerpt=source,
    ),)})
    payload = {"status": "ready", "summary": "Repeat saved points", "intent": {
        "task_kind": "simulation", "objective": "Repeat saved points",
        "selected_capabilities": ["study.dc_points"], "fields": [
            {"path": "study.values", "value": [2, -2], "origin": "repository",
             "source_reference": "reference.md"},
        ],
    }}
    llm = ScriptedLLM([json.dumps(payload)] * 2)
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Repeat the saved study", answers=(), workspace=context, evidence=(),
        capabilities=CapabilityCatalog.from_manifest(
            CapabilityManifest.from_backend("devsim")
        ).public_view(),
    )
    assert len(llm.messages) == 1
    assert [QuantityValue.model_validate(v).to("V")
            for v in decision.intent.fields[0].value] == [2, -2]


@pytest.mark.parametrize(
    ("path", "value", "source", "capability"),
    [("physics.temperature", 300, "`300 K` or `300 degC`", "study.equilibrium"),
     ("study.start", 2, "Applied voltage: \u22122 V", "study.dc"),
     ("study.start", 2, "Applied voltage: - 2 V", "study.dc"),
     ("study.start", 2, "Applied voltage: \u2212 2 V", "study.dc"),
     ("study.start", 2, "Applied voltage: \u20132 V", "study.dc")],
)
def test_ambiguous_or_opposite_signed_source_does_not_supply_a_numeric_unit(
    path, value, source, capability
):
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    context = workspace().model_copy(update={"files": (WorkspaceFileContext(
        path="reference.md", size=len(source), sha256="b" * 64, text_excerpt=source,
    ),)})
    payload = {"status": "ready", "summary": "Repeat study", "intent": {
        "task_kind": "simulation", "objective": "Repeat conditions",
        "selected_capabilities": [capability], "fields": [
            {"path": path, "value": value, "origin": "repository",
             "source_reference": "reference.md"},
        ],
    }}
    llm = ScriptedLLM([json.dumps(payload)] * 2)
    with pytest.raises(ModelResponseError, match="Normalize"):
        OpenHandsPreparationModel(llm).prepare(
            original_prompt="Repeat the saved study", answers=(), workspace=context, evidence=(),
            capabilities=CapabilityCatalog.from_manifest(
                CapabilityManifest.from_backend("devsim")
            ).public_view(),
        )


def test_si_unit_suffix_case_does_not_turn_conductance_into_time():
    from tcad_agent.capabilities.descriptors import CapabilityCatalog
    from tcad_agent.capabilities.models import CapabilityManifest

    payload = {"status": "ready", "summary": "Transient study", "intent": {
        "task_kind": "simulation", "objective": "Analyze transient response",
        "selected_capabilities": ["study.transient"], "fields": [
            {"path": "study.stop_S", "value": 2, "origin": "researcher"},
        ],
    }}
    llm = ScriptedLLM([json.dumps(payload)] * 2)
    with pytest.raises(ModelResponseError):
        OpenHandsPreparationModel(llm).prepare(
            original_prompt="Analyze a transient", answers=(), workspace=workspace(), evidence=(),
            capabilities=CapabilityCatalog.from_manifest(
                CapabilityManifest.from_backend("devsim")
            ).public_view(),
        )


def test_nested_intent_warnings_are_preserved_in_decision_without_retry():
    payload = {
        "status": "ready",
        "summary": "Analyze the supplied contact",
        "warnings": ["No experimental calibration supplied"],
        "intent": {
            "task_kind": "analysis",
            "objective": "Analyze the contact",
            "fields": [
                {"path": "contacts.work_function", "value": "4.35 eV", "origin": "researcher"}
            ],
            "warnings": ["No area specified", "No experimental calibration supplied"],
        },
    }
    llm = ScriptedLLM([json.dumps(payload)] * 2)
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Analyze a contact with work function 4.35 eV",
        answers=(), workspace=workspace(), evidence=(),
    )
    assert decision.warnings == ("No experimental calibration supplied", "No area specified")
    assert decision.intent.fields[0].value == "4.35 eV"
    assert len(llm.messages) == 1


def test_changed_study_representation_is_repaired_before_retaining_old_requirements():
    from tcad_agent.prompting.models import ClarificationAnswer, PreparationDecision

    previous = PreparationDecision.model_validate({
        "status": "clarification", "summary": "Confirm measurement schedule",
        "questions": [{"id": "step", "field_path": "study.step",
                       "prompt": "Step?", "reason": "Schedule"}],
        "unresolved_critical": ["study.step"],
        "intent": {"task_kind": "simulation", "objective": "Voltage response",
                   "selected_capabilities": ["study.dc"]},
    })
    payload = {
        "status": "ready", "summary": "Researcher selected specific operating points",
        "intent": {"task_kind": "simulation", "objective": "Voltage response",
                   "selected_capabilities": ["study.dc_points"],
                   "fields": [{"path": "study.values", "value": ["-1 V", "1 V"],
                               "origin": "researcher"}]},
    }
    repaired = json.loads(json.dumps(payload))
    repaired["intent"]["fields"].append({
        "path": "study.kind", "value": "dc_points", "origin": "researcher",
    })
    decision = OpenHandsPreparationModel(ScriptedLLM([
        json.dumps(payload), json.dumps(repaired),
    ])).prepare(
        original_prompt="Measure the voltage response", workspace=workspace(), evidence=(),
        previous_decision=previous,
        answers=(ClarificationAnswer(question_id="step", answer="Only -1 V and +1 V, no sweep"),),
    )
    assert next(f.value for f in decision.intent.fields if f.path == "study.kind") == "dc_points"


def test_prose_unresolved_paths_are_repaired_before_reaching_the_input_checker():
    payload = {
        "status": "clarification",
        "summary": "Clarify the physical thickness",
        "questions": [
            {
                "id": "thickness",
                "field_path": "regions.geometry.thickness",
                "prompt": "What thickness and unit should be used?",
                "reason": "The original unit is ambiguous",
            }
        ],
        "unresolved_critical": ["regions.geometry.thickness"],
        "intent": {
            "task_kind": "simulation",
            "objective": "Analyze the layered structure",
            "unresolved_critical": ["Thickness unit ('original unit is ambiguous')"],
        },
    }
    repaired = json.loads(json.dumps(payload))
    repaired["intent"]["unresolved_critical"] = ["regions.geometry.thickness"]
    llm = ScriptedLLM([json.dumps(payload), json.dumps(repaired)])
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Analyze the layered structure",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )
    assert decision.intent.unresolved_critical == ("regions.geometry.thickness",)
    assert len(llm.messages) == 2


def test_authority_recovery_preserves_the_original_unanswered_questions():
    payload = {
        "status": "clarification",
        "summary": "Temperature is missing",
        "questions": [
            {
                "id": "temperature",
                "field_path": "physics.temperature",
                "prompt": "What temperature should be used?",
                "reason": "Physical conditions",
            }
        ],
        "unresolved_critical": ["physics.temperature"],
        "intent": {
            "task_kind": "simulation",
            "objective": "Analyze the layered structure",
            "fields": [
                {
                    "path": "contacts.boundary_conditions",
                    "value": "ohmic contacts",
                    "origin": "evidence",
                    "rationale": "Typical example",
                    "evidence_refs": ["example-document"],
                },
                {
                    "path": "contacts.work_function",
                    "value": "4.35 eV",
                    "origin": "researcher",
                },
            ],
            "unresolved_critical": ["physics.temperature"],
        },
    }
    llm = ScriptedLLM([json.dumps(payload)])
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Use a 4.35 eV metal contact",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )
    assert {q.field_path for q in decision.questions} == {
        "physics.temperature",
        "contacts.boundary_conditions",
    }
    assert set(decision.unresolved_critical) == {
        "physics.temperature",
        "contacts.boundary_conditions",
    }
    assert set(decision.intent.unresolved_critical) == set(decision.unresolved_critical)
    assert [(f.path, f.value) for f in decision.intent.fields] == [
        ("contacts.work_function", "4.35 eV")
    ]


def test_gateway_preserves_unresolved_lists_without_spending_another_model_call():
    payload = {
        "status": "clarification",
        "summary": "Confirm physical thickness",
        "questions": [
            {
                "id": "thickness",
                "field_path": "regions.thickness",
                "prompt": "Which thickness and unit?",
                "reason": "Physical dimension",
            }
        ],
        "unresolved_critical": ["regions.thickness"],
        "intent": {
            "task_kind": "simulation",
            "objective": "Analyze the layered structure",
            "unresolved_critical": ["regions.thickness_unit"],
        },
    }
    corrected = json.loads(json.dumps(payload))
    corrected["intent"]["unresolved_critical"] = ["regions.thickness"]
    llm = ScriptedLLM([json.dumps(payload), json.dumps(corrected)])
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Analyze the layered structure",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )
    assert decision.intent.unresolved_critical == decision.unresolved_critical
    assert set(decision.unresolved_critical) == {"regions.thickness", "regions.thickness_unit"}
    assert len(llm.messages) == 1


def test_gateway_discards_ancillary_citations_from_researcher_owned_values():
    response = json.dumps(
        {
            "status": "ready",
            "summary": "User supplied the temperature.",
            "intent": {
                "task_kind": "simulation",
                "objective": "Evaluate at 300 K",
                "fields": [
                    {
                        "path": "physics.temperature",
                        "value": "300 K",
                        "origin": "researcher",
                        "evidence_refs": ["unrelated-doc"],
                    }
                ],
            },
        }
    )
    llm = ScriptedLLM([response])
    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Evaluate at 300 K",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )
    assert decision.intent.fields[0].value == "300 K"
    assert decision.intent.fields[0].origin == "researcher"
    assert decision.intent.fields[0].evidence_refs == ()
    assert len(llm.messages) == 1


def test_preparation_budget_reserves_room_for_reasoning_and_structured_output(monkeypatch):
    from tcad_agent.prompting import gateway

    captured = {}

    class Configuration:
        def model_copy(self, *, update):
            captured.update(update)
            return self

    monkeypatch.setattr(gateway, "llm_from_environment", Configuration)
    OpenHandsPreparationModel.from_environment()
    assert captured["num_retries"] == 0
    assert captured["max_output_tokens"] >= 16384
    assert captured["timeout"] <= 120


def test_system_policy_distinguishes_absolute_current_from_current_density() -> None:
    policy = OpenHandsPreparationModel._system_policy()

    assert "absolute terminal current" in policy
    assert "contact area" in policy
    assert "current density" in policy


def test_gateway_parses_a_generic_clarification_decision() -> None:
    response = json.dumps(
        {
            "status": "clarification",
            "summary": "One physical boundary condition is missing.",
            "questions": [
                {
                    "id": "contact_behavior",
                    "field_path": "contacts.behavior",
                    "prompt": "What contact behavior should be used?",
                    "reason": "This changes the electrical boundary condition.",
                    "required": True,
                }
            ],
            "intent": None,
            "unresolved_critical": ["contacts.behavior"],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    gateway = OpenHandsPreparationModel(ScriptedLLM([response]))

    decision = gateway.prepare(
        original_prompt="Simulate the structure at equilibrium.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.status == "clarification"
    assert decision.questions[0].field_path == "contacts.behavior"


def test_gateway_derives_missing_clarification_paths_from_typed_questions() -> None:
    response = json.dumps(
        {
            "status": "clarification",
            "summary": "Two researcher-owned conditions are missing.",
            "questions": [
                {
                    "id": "temperature",
                    "field_path": "physics.temperature",
                    "prompt": "What scalar reference temperature should be used?",
                    "reason": "The simulation contract requires this value.",
                    "required": True,
                },
                {
                    "id": "fixed_contact",
                    "field_path": "contacts.right.voltage",
                    "prompt": "What fixed voltage should be applied on the right?",
                    "reason": "It defines the applied bias.",
                    "required": True,
                },
            ],
            "intent": None,
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    llm = ScriptedLLM([response])

    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Simulate the stated spatial-temperature study.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.unresolved_critical == (
        "physics.temperature",
        "contacts.right.voltage",
    )
    assert len(llm.messages) == 1


def test_gateway_repairs_one_invalid_structured_response() -> None:
    valid = {
        "status": "ready",
        "summary": "The repository request is complete.",
        "questions": [],
        "intent": {
            "task_kind": "repository_change",
            "objective": "Inspect the repository and fix the failing test.",
            "fields": [],
            "exclusions": [],
            "deliverables": [],
            "validation_expectations": ["Run the relevant tests."],
            "unresolved_noncritical": [],
            "unresolved_critical": [],
        },
        "unresolved_critical": [],
        "warnings": [],
        "runtime_research_needed": False,
        "runtime_research_reason": None,
    }
    llm = ScriptedLLM(["not json", json.dumps(valid)])

    decision = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Inspect the repository and fix the failing test.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.status == "ready"
    assert len(llm.messages) == 2


def test_gateway_sanitizes_provider_errors() -> None:
    gateway = OpenHandsPreparationModel(
        ScriptedLLM([RuntimeError("credential secret-value was rejected")])
    )

    with pytest.raises(ModelResponseError) as captured:
        gateway.prepare(
            original_prompt="Inspect the repository",
            answers=(),
            workspace=workspace(),
            evidence=(),
        )

    assert "secret-value" not in str(captured.value)


def test_gateway_allows_platform_to_choose_an_output_file_format() -> None:
    response = json.dumps(
        {
            "status": "ready",
            "summary": "The simulation request is executable.",
            "questions": [],
            "intent": {
                "task_kind": "simulation",
                "objective": "Run the requested equilibrium simulation.",
                "fields": [
                    {
                        "path": "outputs.file_format",
                        "value": "canonical-json",
                        "origin": "platform_default",
                        "source_reference": "platform output contract",
                        "evidence_refs": [],
                    }
                ],
                "exclusions": [],
                "deliverables": [],
                "validation_expectations": [],
                "unresolved_noncritical": [],
                "unresolved_critical": [],
            },
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )

    decision = OpenHandsPreparationModel(ScriptedLLM([response])).prepare(
        original_prompt="Run the specified simulation.",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )

    assert decision.intent is not None
    assert decision.intent.fields[0].path == "outputs.file_format"


def test_gateway_allows_reviewed_evidence_to_choose_interface_coupling() -> None:
    response = json.dumps(
        {
            "status": "ready",
            "summary": "The material adjacency is complete.",
            "questions": [],
            "intent": {
                "task_kind": "simulation",
                "objective": "Run the requested layered simulation.",
                "fields": [
                    {
                        "path": "interfaces.oxide_silicon.coupling",
                        "value": "continuity",
                        "origin": "evidence",
                        "rationale": "The reviewed backend guide supports this coupling.",
                        "evidence_refs": ["guide:interfaces"],
                    }
                ],
                "exclusions": [],
                "deliverables": [],
                "validation_expectations": [],
                "unresolved_noncritical": [],
                "unresolved_critical": [],
            },
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    evidence = EvidenceExcerpt(
        id="guide:interfaces",
        title="Reviewed guide",
        url="internal://guide",
        version="1",
        content_hash="a" * 64,
        reviewed=True,
        content="Continuity coupling is supported.",
    )

    decision = OpenHandsPreparationModel(ScriptedLLM([response])).prepare(
        original_prompt="Model the stated oxide and silicon layers.",
        answers=(),
        workspace=workspace(),
        evidence=(evidence,),
    )

    assert decision.status == "ready"


def test_gateway_reconciles_explicit_researcher_value_mislabeled_as_evidence() -> None:
    response = json.dumps(
        {
            "status": "ready",
            "summary": "The requested profile is complete.",
            "questions": [],
            "intent": {
                "task_kind": "simulation",
                "objective": "Run the requested silicon study.",
                "fields": [
                    {
                        "path": "regions.p.profile.type",
                        "value": "uniform",
                        "origin": "evidence",
                        "rationale": "The guide describes uniform profiles.",
                        "evidence_refs": ["guide:profiles"],
                    }
                ],
                "exclusions": [],
                "deliverables": [],
                "validation_expectations": [],
                "unresolved_noncritical": [],
                "unresolved_critical": [],
            },
            "unresolved_critical": [],
            "warnings": [],
            "runtime_research_needed": False,
            "runtime_research_reason": None,
        }
    )
    evidence = EvidenceExcerpt(
        id="guide:profiles",
        title="Reviewed profile guide",
        url="internal://profiles",
        version="1",
        content_hash="b" * 64,
        reviewed=True,
        content="Uniform profiles are supported.",
    )

    decision = OpenHandsPreparationModel(ScriptedLLM([response])).prepare(
        original_prompt="Use uniform boron doping in the p region.",
        answers=(),
        workspace=workspace(),
        evidence=(evidence,),
    )

    assert decision.intent is not None
    field = decision.intent.fields[0]
    assert field.origin.value == "researcher"
    assert field.evidence_refs == ()


def test_gateway_does_not_reconcile_value_absent_from_researcher_input() -> None:
    invalid = {
        "status": "ready",
        "summary": "The profile is complete.",
        "questions": [],
        "intent": {
            "task_kind": "simulation",
            "objective": "Run a silicon study.",
            "fields": [
                {
                    "path": "regions.p.profile.type",
                    "value": "gaussian",
                    "origin": "evidence",
                    "rationale": "The guide describes Gaussian profiles.",
                    "evidence_refs": ["guide:profiles"],
                }
            ],
            "exclusions": [],
            "deliverables": [],
            "validation_expectations": [],
            "unresolved_noncritical": [],
            "unresolved_critical": [],
        },
        "unresolved_critical": [],
        "warnings": [],
        "runtime_research_needed": False,
        "runtime_research_reason": None,
    }
    evidence = EvidenceExcerpt(
        id="guide:profiles",
        title="Reviewed profile guide",
        url="internal://profiles",
        version="1",
        content_hash="b" * 64,
        reviewed=True,
        content="Gaussian profiles are supported.",
    )
    gateway = OpenHandsPreparationModel(ScriptedLLM([json.dumps(invalid), json.dumps(invalid)]))

    decision = gateway.prepare(
        original_prompt="Use boron doping in the p region.",
        answers=(),
        workspace=workspace(),
        evidence=(evidence,),
    )
    assert decision.status == "clarification"
    assert decision.questions[0].field_path == "regions.p.profile.type"
    assert len(gateway._llm.messages) == 1


def test_model_schema_requires_real_citations_for_expert_evidence_fields():
    schema = OpenHandsPreparationModel._decision_schema()
    evidence_rule = next(
        rule
        for rule in schema["$defs"]["IntentField"]["allOf"]
        if rule["if"]["properties"]["origin"]["const"] == "evidence"
    )
    assert evidence_rule["then"]["properties"]["evidence_refs"]["minItems"] == 1
    assert evidence_rule["then"]["properties"]["rationale"]["minLength"] == 1
    assert "exact IDs from local_evidence" in OpenHandsPreparationModel._system_policy()


def test_unregistered_display_intent_is_repaired_before_the_execution_agent_starts():
    payload = {
        "status": "ready",
        "summary": "Extract density",
        "intent": {
            "task_kind": "simulation",
            "objective": "Extract electron density",
            "fields": [
                {
                    "path": "display_units",
                    "value": {"concentration": "cm^-3"},
                    "origin": "researcher",
                }
            ],
        },
    }
    repaired = json.loads(json.dumps(payload))
    repaired["intent"]["fields"][0]["value"] = {"electron_density": "cm^-3"}
    llm = ScriptedLLM([json.dumps(payload), json.dumps(repaired)])
    result = OpenHandsPreparationModel(llm).prepare(
        original_prompt="Extract electron density in cm^-3",
        answers=(),
        workspace=workspace(),
        evidence=(),
    )
    assert result.intent.fields[0].value == {"electron_density": "cm^-3"}
    assert len(llm.messages) == 2
    packet = json.loads(llm.messages[0][1].content[0].text)
    assert packet["display_quantity_units"]["electron_density"] == "m^-3"
