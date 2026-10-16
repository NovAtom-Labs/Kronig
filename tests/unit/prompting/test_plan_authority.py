"""Confirmed schema-addressable intent must survive agent plan generation."""

import pytest

from tcad_agent.agent.tools import DomainTools
from tcad_agent.domain.units import QuantityValue
from tcad_agent.prompting.authority import _equal
from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent


def test_quantity_comparison_is_independent_of_serialized_dimension_order():
    stored = QuantityValue.model_validate("100 mV").model_dump(mode="json")
    stored["dimensionality"] = "[current] ** -1 * [time] ** -3 * [length] ** 2 * [mass]"
    assert _equal(QuantityValue.model_validate(stored), "0.1 V")


@pytest.mark.parametrize(
    "path,value",
    [
        ("physics.temperature", "315 K"),
        ("study.stop", "0.4 V"),
        ("regions.p_region.x1", "0.4 um"),
        ("regions.0.thickness", "0.4 um"),
        ("geometry.length", "2 um"),
        ("profiles.0.value", "2e17 cm^-3"),
        ("contacts.left.voltage_offset", "0.1 V"),
        ("contacts.anode.kind", "schottky"),
        ("physics.electron_mobility", "0.135 m^2/V/s"),
        ("physics.hole_mobility", "0.048 m^2/V/s"),
    ],
)
def test_plan_refuses_changed_confirmed_schema_value(tmp_path, valid_spec, path, value):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Preserve my inputs",
        fields=(IntentField(path=path, value=value, origin="researcher"),),
    )
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        valid_spec.model_dump(mode="json"), backend="devsim"
    )
    assert response.code == "scientific_input_authority_violation", response
    assert response.data["issues"][0]["intent_path"] == path


@pytest.mark.parametrize(
    "path,value",
    [
        ("physics.temperature", "300 K"),
        ("study.stop", "200 mV"),
        ("regions.p_region.x1", "500 nm"),
        ("regions.0.thickness", "500 nm"),
        ("geometry.length", "1000 nm"),
        ("profiles.0.value", "1e23 m^-3"),
        ("contacts.left.voltage_offset", "0 mV"),
    ],
)
def test_plan_accepts_equivalent_units(tmp_path, valid_spec, path, value):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Preserve my inputs",
        fields=(IntentField(path=path, value=value, origin="researcher"),),
    )
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        valid_spec.model_dump(mode="json"), backend="devsim"
    )
    assert response.status == "ok", response


def test_portable_physics_parameter_cannot_be_dropped_through_a_short_path(tmp_path, valid_spec):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Preserve my lifetime",
        fields=(IntentField(path="physics.electron_lifetime", value="2 us", origin="researcher"),),
    )
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        valid_spec.model_dump(mode="json"), backend="devsim"
    )
    assert response.code == "scientific_input_authority_violation", response


def test_aggregate_parameter_record_accepts_only_matching_declared_values(tmp_path, valid_spec):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Use this lifetime",
        fields=(
            IntentField(
                path="physics.parameters", value={"electron_lifetime": "2 us"}, origin="researcher"
            ),
        ),
    )
    payload = valid_spec.model_dump(mode="json")
    payload["physics"]["parameters"]["electron_lifetime"] = "2 us"
    tools = DomainTools(tmp_path, research_intent=intent)
    assert tools.prepare_experiment(payload, backend="devsim").status == "ok"
    payload["physics"]["parameters"]["electron_lifetime"] = "3 us"
    assert tools.prepare_experiment(payload, backend="devsim").code == (
        "scientific_input_authority_violation"
    )
