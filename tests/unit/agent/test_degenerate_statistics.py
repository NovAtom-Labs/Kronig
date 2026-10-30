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
