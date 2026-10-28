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
        # A reverse sweep's step is stored as a magnitude; its direction comes from start/stop.
        ("study.step", "-0.1 V"),
        ("study.step", "-100 mV"),
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


def test_band_gap_narrowing_intent_is_met_by_the_slotboom_model(tmp_path, valid_spec):
    payload = valid_spec.model_dump(mode="json")
    payload["physics"]["models"] = [*payload["physics"]["models"], "slotboom_bgn"]
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Include band-gap narrowing",
        fields=(),
        selected_capabilities=("model.band_gap_narrowing",),
    )
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        payload, backend="devsim"
    )
    assert response.code != "requested_scope_missing", response


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


@pytest.mark.parametrize("origin", ["researcher", "repository"])
@pytest.mark.parametrize(
    "path,value",
    [
        ("contacts.gate.voltage_offset", "0 V"),
        ("contacts.gate.kind", "ohmic"),
        ("contacts.2.voltage_offset", "0 V"),
        ("contacts.gate", {"voltage_offset": "0 V"}),
        ("regions.removed.x1", "0.5 um"),
        ("regions.removed.thickness", "0.5 um"),
        ("profiles.2.value", "1e17 cm^-3"),
        ("interfaces.0.fixed_charge_density", "1e10 cm^-2"),
    ],
)
def test_plan_refuses_missing_confirmed_entity(tmp_path, valid_spec, path, value, origin):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Keep the confirmed entities and their inputs",
        fields=(
            IntentField(
                path=path,
                value=value,
                origin=origin,
                source_reference="experiment.yaml" if origin == "repository" else None,
            ),
        ),
    )
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        valid_spec.model_dump(mode="json"), backend="devsim"
    )
    assert response.code == "scientific_input_authority_violation", response
    assert response.data["issues"][0]["intent_path"] == path
    assert response.data["issues"][0]["reason"] == "missing_confirmed_input"
    assert not (tmp_path / "experiments").exists()


def test_plan_refuses_renaming_confirmed_contact_even_with_the_same_value(tmp_path, valid_spec):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Keep my anode contact",
        fields=(
            IntentField(path="contacts.anode.voltage_offset", value="0 V", origin="researcher"),
        ),
    )
    payload = valid_spec.model_dump(mode="json")
    payload["contacts"][0]["id"] = "renamed"
    payload["study"]["contact"] = "renamed"
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        payload, backend="devsim"
    )
    assert response.code == "scientific_input_authority_violation", response


@pytest.mark.parametrize(
    "path,value",
    [
        ("contacts.left.voltage_offset", "0 V"),
        ("contacts.x_min.voltage_offset", "0 V"),
        ("contacts.anode", {"voltage_offset": "0 V"}),
        ("contacts.boundary_conditions", "Ohmic endpoint contacts"),
        (
            "contacts.boundary_conditions",
            {"contact": "anode", "kind": "ohmic", "voltage_offset": "0 V"},
        ),
        ("regions.structure", "Two adjoining silicon regions"),
        ("research.notes", "Check the electrical response"),
    ],
)
def test_missing_entity_guard_preserves_valid_aliases_and_free_text(
    tmp_path, valid_spec, path, value
):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Preserve typed inputs without inventing free-text mappings",
        fields=(IntentField(path=path, value=value, origin="researcher"),),
    )
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        valid_spec.model_dump(mode="json"), backend="devsim"
    )
    assert response.status == "ok", response


@pytest.mark.parametrize("offset,expected", [("0 V", "ok"), ("1 V", "refused")])
def test_explicit_contact_location_binds_values_without_losing_authority(
    tmp_path, valid_spec, offset, expected
):
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Use the supplied boundary role",
        fields=(
            IntentField(path="contacts.injecting.location", value="x_min", origin="researcher"),
            IntentField(
                path="contacts.injecting.voltage_offset", value=offset, origin="researcher"
            ),
        ),
    )
    response = DomainTools(tmp_path, research_intent=intent).prepare_experiment(
        valid_spec.model_dump(mode="json"), backend="devsim"
    )
    assert response.status == expected, response
