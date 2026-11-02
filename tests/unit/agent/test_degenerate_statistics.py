import pytest

from tcad_agent.agent.tools import DomainTools
from tcad_agent.domain.models import Contact, ExperimentSpec
from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent


def _schottky(spec: ExperimentSpec, work_function: str, statistics: str) -> ExperimentSpec:
    contact = Contact.model_validate(
        {
            "id": spec.contacts[0].id,
            "location": spec.contacts[0].location,
            "kind": "metal_work_function",
            "work_function": work_function,
        }
    )
    models = tuple(m for m in spec.physics.models if m not in {"boltzmann", "fermi"})
    return spec.model_copy(
        update={
            "contacts": (contact, *spec.contacts[1:]),
            "physics": spec.physics.model_copy(update={"models": (*models, statistics)}),
        }
    )


def _code(tmp_path, spec, intent=None):
    tools = DomainTools(tmp_path, research_intent=intent) if intent else DomainTools(tmp_path)
    return tools._degenerate_surface_statistics_response(spec)


@pytest.mark.parametrize("work_function", ["4.10 eV", "5.15 eV"])
def test_band_edge_contact_refuses_planner_chosen_boltzmann(valid_spec, tmp_path, work_function):
    response = _code(tmp_path, _schottky(valid_spec, work_function, "boltzmann"))
    assert response is not None
    assert response.code == "degenerate_surface_requires_fermi_statistics"


def test_midgap_contact_and_fermi_statistics_are_left_alone(valid_spec, tmp_path):
    assert _code(tmp_path, _schottky(valid_spec, "4.60 eV", "boltzmann")) is None
    assert _code(tmp_path, _schottky(valid_spec, "4.10 eV", "fermi")) is None


def test_a_one_dimensional_devsim_schottky_contact_refuses_planner_chosen_boltzmann(
    valid_spec, tmp_path
):
    spec = _schottky(valid_spec, "4.60 eV", "boltzmann")
    tools = DomainTools(tmp_path)
    refused = tools._degenerate_surface_statistics_response(spec, "devsim")
    assert refused is not None
    assert refused.code == "schottky_contact_requires_fermi_statistics"
    # Other backends, and Fermi statistics, are left alone.
    assert tools._degenerate_surface_statistics_response(spec, "sentaurus") is None
    fermi = _schottky(valid_spec, "4.60 eV", "fermi")
    assert tools._degenerate_surface_statistics_response(fermi, "devsim") is None


def test_explicit_researcher_boltzmann_request_is_honored(valid_spec, tmp_path):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Use Boltzmann statistics",
        fields=(IntentField(path="physics.models", value=["boltzmann"], origin="researcher"),),
    )
    assert _code(tmp_path, _schottky(valid_spec, "4.10 eV", "boltzmann"), intent) is None


def test_planner_inferred_boltzmann_scope_is_met_by_fermi_statistics(valid_spec, tmp_path):
    models = tuple(m for m in valid_spec.physics.models if m not in {"boltzmann", "fermi"})
    spec = valid_spec.model_copy(
        update={"physics": valid_spec.physics.model_copy(update={"models": (*models, "fermi")})}
    )

    def code(*fields):
        intent = ResolvedResearchIntent(
            task_kind="simulation",
            objective="Band bending",
            fields=fields,
            selected_capabilities=("model.boltzmann",),
        )
        return DomainTools(tmp_path, research_intent=intent).prepare_experiment(
            spec.model_dump(mode="json"), backend="devsim"
        ).code

    assert code() != "requested_scope_missing"
    stated = IntentField(path="physics.models", value=["boltzmann"], origin="researcher")
    assert code(stated) == "requested_scope_missing"


def test_a_replaced_gate_answer_does_not_block_the_plan(valid_spec, tmp_path):
    spec = _schottky(valid_spec, "4.60 eV", "fermi")

    def code(*capabilities):
        intent = ResolvedResearchIntent(
            task_kind="simulation",
            objective="Gate contact",
            fields=(),
            selected_capabilities=capabilities,
        )
        return DomainTools(tmp_path, research_intent=intent).prepare_experiment(
            spec.model_dump(mode="json"), backend="devsim"
        ).code

    # The researcher first said ideal gate, then gave a work function: the metal gate is kept.
    assert code("contact.metal_work_function", "contact.ideal_gate") != "requested_scope_missing"
    # An ideal gate asked for on its own is not what the plan holds.
    assert code("contact.ideal_gate") == "requested_scope_missing"


def test_planner_added_bgn_does_not_block_a_two_dimensional_devsim_plan(tmp_path):
    from tests.unit.adapters.test_sentaurus_two_dimensional import spec_with

    spec = spec_with(
        lambda d: d["physics"].update(models=["fermi", "constant_mobility", "srh"])
    )

    def code(*fields):
        intent = ResolvedResearchIntent(
            task_kind="simulation",
            objective="MOSFET",
            fields=fields,
            selected_capabilities=("model.slotboom_bgn",),
        )
        return DomainTools(tmp_path, research_intent=intent).prepare_experiment(
            spec.model_dump(mode="json"), backend="devsim"
        ).code

    assert code() != "requested_scope_missing"
    asked = IntentField(path="physics.models", value=["slotboom_bgn"], origin="researcher")
    assert code(asked) == "requested_scope_missing"


def test_gate_over_an_insulator_refuses_planner_chosen_boltzmann(valid_spec, tmp_path):
    from tcad_agent.domain.models import Contact

    oxide = valid_spec.regions[0].model_copy(update={"material": "silicon_dioxide"})
    gate = Contact.model_validate(
        {"id": "gate", "location": "x_min", "kind": "metal_work_function", "work_function": "4.6 eV"}
    )
    spec = valid_spec.model_copy(
        update={"regions": (oxide, *valid_spec.regions[1:]), "contacts": (gate, *valid_spec.contacts[1:])}
    )
    spec = spec.model_copy(
        update={
            "physics": spec.physics.model_copy(
                update={
                    "models": tuple(
                        m for m in spec.physics.models if m not in {"boltzmann", "fermi"}
                    )
                    + ("boltzmann",)
                }
            )
        }
    )
    response = DomainTools(tmp_path)._degenerate_surface_statistics_response(spec)
    assert response is not None
    assert response.code == "gated_surface_requires_fermi_statistics"
