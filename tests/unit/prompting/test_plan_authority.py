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


@pytest.mark.parametrize(
    "path,value",
    [
        ("regions.region.material", "p_region"),
        ("regions.material.material", "silicon, 1 um thick, 1D stack"),
        ("regions.location.material", "x_min_to_x_max"),
    ],
)
def test_material_path_restating_label_extent_or_narrative_is_honored(valid_spec, path, value):
    from tcad_agent.prompting.authority import plan_authority_issues

    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Keep my region",
        fields=(IntentField(path=path, value=value, origin="researcher"),),
    )
    assert plan_authority_issues(valid_spec, intent) == []


def test_material_path_naming_a_different_material_is_refused(valid_spec):
    from tcad_agent.prompting.authority import plan_authority_issues

    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Keep my region",
        fields=(IntentField(path="regions.p_region.material", value="hafnium_oxide", origin="researcher"),),
    )
    assert plan_authority_issues(valid_spec, intent)


def test_profile_record_naming_its_region_by_region_id_is_held(valid_spec):
    from tcad_agent.prompting.authority import plan_authority_issues

    profile = valid_spec.profiles[0]
    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Keep my doping",
        fields=(
            IntentField(
                path="profiles.parameters",
                value=[
                    {
                        "concentration": "1e17 cm^-3",
                        "profile_type": "constant",
                        "region_id": profile.region,
                        "species": "acceptor",
                    }
                ],
                origin="researcher",
            ),
        ),
    )
    assert plan_authority_issues(valid_spec, intent) == []


def test_record_keys_carrying_their_unit_in_the_name_are_compared_by_value(valid_spec):
    from tcad_agent.prompting.authority import _holds_records

    region = valid_spec.regions[0]
    thickness_um = round((region.x1.to("m") - region.x0.to("m")) * 1e6, 9)
    profile = valid_spec.profiles[0]
    concentration_cm3 = profile.value.to("1/m^3") * 1e-6 if hasattr(profile.value, "to") else None
    assert _holds_records(
        valid_spec.regions, [{"region": region.id, "thickness_um": thickness_um}], "extents"
    )
    assert not _holds_records(
        valid_spec.regions, [{"region": region.id, "thickness_um": thickness_um * 2}], "extents"
    )
    if concentration_cm3 is not None:
        assert _holds_records(
            valid_spec.profiles,
            [{"region": profile.region, "concentration_cm3": concentration_cm3, "profile": "constant"}],
            "parameters",
        )


def test_dopant_element_in_confirmed_species_is_met_by_the_dopant_type(valid_spec):
    from tcad_agent.prompting.authority import plan_authority_issues

    intent = ResolvedResearchIntent(
        task_kind="simulation",
        objective="Keep my dopant",
        fields=(
            IntentField(path="profiles.p_region.species", value="boron", origin="researcher"),
        ),
    )
    assert plan_authority_issues(valid_spec, intent) == []


def test_descriptive_doping_keys_are_read_by_meaning(valid_spec):
    from tcad_agent.prompting.authority import plan_authority_issues

    def issues(path, value):
        intent = ResolvedResearchIntent(
            task_kind="simulation",
            objective="Keep my substrate",
            fields=(IntentField(path=path, value=value, origin="researcher"),),
        )
        return plan_authority_issues(valid_spec, intent)

    assert issues("profiles.substrate_doping_type", "p-type") == []
    assert issues("profiles.substrate_doping_concentration", "1e17 cm^-3") == []


def test_mesh_spacing_is_judged_by_value_not_by_the_models_label(valid_spec):
    from tcad_agent.prompting.authority import plan_authority_issues

    region = valid_spec.regions[0]
    payload = valid_spec.model_dump(mode="json")
    payload["regions"][0]["minimum_mesh_spacing"] = "2 nm"
    payload["regions"][0]["maximum_mesh_spacing"] = "10 nm"
    spec = type(valid_spec).model_validate(payload)
    thickness_um = round((region.x1.to("m") - region.x0.to("m")) * 1e6, 9)

    def issues(*fields):
        intent = ResolvedResearchIntent(
            task_kind="simulation",
            objective="Keep my mesh",
            fields=tuple(IntentField(path=p, value=v, origin="researcher") for p, v in fields),
        )
        return plan_authority_issues(spec, intent)

    assert issues(
        ("regions.min_nm.mesh_spacing", "2 nm"),
        ("regions.max_nm.mesh_spacing", "10 nm"),
        ("regions.refines_at.mesh_spacing", "Al-Si interface (x_min)"),
        ("regions.extent", f"{thickness_um} um"),
    ) == []
    assert issues(("regions.min_nm.mesh_spacing", "3 nm"))


def test_list_of_composite_region_and_doping_records_is_held_by_the_spec(valid_spec):
    from tcad_agent.prompting.authority import _composite_records_held

    region = valid_spec.regions[0]
    profile = valid_spec.profiles[0]
    thickness_um = round((region.x1.to("m") - region.x0.to("m")) * 1e6, 9)
    record = {
        "id": "silicon_layer",
        "material": region.material,
        "thickness": f"{thickness_um} um",
        "profile": "constant",
        "species": profile.species,
    }
    assert _composite_records_held(valid_spec, [record])
    assert not _composite_records_held(valid_spec, [{**record, "thickness": f"{thickness_um * 7.3} um"}])
    assert not _composite_records_held(valid_spec, [])
