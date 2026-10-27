from pathlib import Path

import yaml

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.prompting.authority import plan_authority_issues
from tcad_agent.prompting.models import IntentField, ResolvedResearchIntent

ROOT = Path(__file__).resolve().parents[3]


def _spec():
    return ExperimentSpec.model_validate(
        yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    )


def _intent(path, value):
    return ResolvedResearchIntent(
        task_kind="simulation",
        objective="x",
        fields=(IntentField(path=path, value=value, origin="researcher"),),
    )


def test_a_differently_labelled_record_holding_the_confirmed_value_is_accepted():
    assert plan_authority_issues(_spec(), _intent("profiles.body.species", "acceptor")) == []


def test_a_label_cannot_hide_a_value_that_no_record_holds():
    issues = plan_authority_issues(_spec(), _intent("profiles.body.value", "5e20 cm^-3"))
    assert [issue["intent_path"] for issue in issues] == ["profiles.body.value"]


def _planar():
    import sys
    sys.path.insert(0, str(ROOT / "tests" / "unit" / "domain"))
    from test_two_dimensional_spec import planar_device

    return ExperimentSpec.model_validate(planar_device())


def test_a_confirmed_cut_depth_is_checked_against_the_cut_position():
    spec = _planar()
    at = spec.profile_cuts[0].at
    ok = _intent("profile_cuts.depth", f"{at.magnitude_si:.15g} m")
    assert plan_authority_issues(spec, ok) == []
    wrong = plan_authority_issues(spec, _intent("profile_cuts.depth", "999 nm"))
    assert [i["intent_path"] for i in wrong] == ["profile_cuts.depth"]


def test_region_extents_are_checked_against_the_region_bounds():
    spec = _spec()
    region = spec.regions[0]
    good = {"x_min": f"{region.x0.magnitude_si:.15g} m", "x_max": f"{region.x1.magnitude_si:.15g} m"}
    assert plan_authority_issues(spec, _intent("regions.extents", good)) == []

def test_a_region_extent_confirmed_as_material_and_thickness_is_accepted():
    spec = _spec()
    region = spec.regions[0]
    thickness = f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m"
    assert plan_authority_issues(
        spec, _intent("regions.extents", {"material": region.material, "thickness": thickness})
    ) == []


def test_a_confirmed_list_of_records_uses_the_specs_own_vocabulary():
    spec = _spec()
    region = spec.regions[0]
    thickness = f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m"
    held = [{"id": "anything", "material": region.material, "thickness": thickness}]
    assert plan_authority_issues(spec, _intent("regions.material", held)) == []
    profile = spec.profiles[0]
    doping = [{"profile": profile.kind, "species": profile.species.value,
               "concentration": f"{profile.value.magnitude_si:.15g} 1/m^3", "region": profile.region}]
    assert plan_authority_issues(spec, _intent("profiles.parameters", doping)) == []
    wrong = [{**held[0], "thickness": "123 nm"}]
    from tcad_agent.prompting.authority import _equal

    assert not _equal(region, wrong[0])


def test_keyed_and_element_named_records_are_checked_by_what_they_say():
    spec = _spec()
    region = spec.regions[0]
    thickness = f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m"
    keyed = {region.id: {"thickness": thickness}}
    assert plan_authority_issues(spec, _intent("regions.extents", keyed)) == []
    profile = spec.profiles[0]
    element = "boron" if profile.species.value == "acceptor" else "phosphorus"
    doping = {"type": "constant", "species": element, "region": profile.region,
              "concentration": f"{profile.value.magnitude_si:.15g} 1/m^3"}
    assert plan_authority_issues(spec, _intent("profiles.parameters", doping)) == []
    other = "phosphorus" if element == "boron" else "boron"
    from tcad_agent.prompting.authority import _holds_records

    assert _holds_records(spec.profiles, doping, "parameters")
    assert not _holds_records(spec.profiles, {**doping, "species": other}, "parameters")


def test_a_composite_confirmed_record_mixing_region_and_profile_keys_is_accepted():
    """regions.parameters = {thickness, concentration, profile, species} must not raise
    changed_confirmed_input even though no single spec model carries all four fields."""
    spec = _spec()
    region = spec.regions[0]
    profile = spec.profiles[0]
    thickness = f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m"
    composite = {
        "thickness": thickness,
        "concentration": f"{profile.value.magnitude_si:.15g} 1/m^3",
        "profile": profile.kind,
        "species": profile.species.value,
    }
    assert plan_authority_issues(spec, _intent("regions.parameters", composite)) == []


def test_a_composite_record_with_wrong_concentration_is_refused():
    spec = _spec()
    region = spec.regions[0]
    thickness = f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m"
    profile = spec.profiles[0]
    wrong_conc = "5e20 cm^-3" if profile.value.magnitude_si < 1e25 else "1e12 cm^-3"
    composite = {
        "thickness": thickness,
        "concentration": wrong_conc,
        "profile": profile.kind,
        "species": profile.species.value,
    }
    issues = plan_authority_issues(spec, _intent("regions.parameters", composite))
    assert [i["intent_path"] for i in issues] == ["regions.parameters"]


def test_a_composite_record_with_wrong_species_is_refused():
    spec = _spec()
    region = spec.regions[0]
    profile = spec.profiles[0]
    thickness = f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m"
    wrong_species = "donor" if profile.species.value == "acceptor" else "acceptor"
    composite = {
        "thickness": thickness,
        "concentration": f"{profile.value.magnitude_si:.15g} 1/m^3",
        "profile": profile.kind,
        "species": wrong_species,
    }
    issues = plan_authority_issues(spec, _intent("regions.parameters", composite))
    assert [i["intent_path"] for i in issues] == ["regions.parameters"]


def test_a_composite_record_filed_under_profiles_is_checked_the_same_way():
    spec = _spec()
    region = spec.regions[0]
    profile = spec.profiles[0]
    composite = {
        "thickness": f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m",
        "concentration": f"{profile.value.magnitude_si:.15g} 1/m^3",
        "profile": profile.kind,
        "species": profile.species.value,
    }
    assert plan_authority_issues(spec, _intent("profiles.parameters", composite)) == []


def test_a_composite_on_a_single_region_spec_is_not_falsely_rejected():
    # Regression: on a single-region spec _resolve returns the lone Region1D via the
    # lone-record fallback, not _UNMAPPED.  _equal(Region1D, composite) then fails
    # because Region1D carries no doping fields, and the old code incorrectly fired
    # changed_confirmed_input.  The composite guard must activate in this case too.
    single = ExperimentSpec.model_validate({
        "schema_version": "1.0",
        "name": "schottky-single",
        "dimension": 1,
        "regions": [{"id": "silicon", "material": "silicon", "x0": "0 nm", "x1": "1000 nm"}],
        "profiles": [{"kind": "constant", "region": "silicon", "species": "acceptor", "value": "1e18 cm^-3"}],
        "contacts": [
            {"id": "gate", "location": "x_min", "kind": "metal_work_function",
             "work_function": "4.1 eV", "voltage_offset": "0 V"},
            {"id": "back", "location": "x_max", "kind": "ohmic", "voltage_offset": "0 V"},
        ],
        "physics": {"equations": ["poisson"], "temperature": "300 K"},
        "study": {"kind": "equilibrium"},
        "observables": ["potential"],
    })
    region = single.regions[0]
    profile = single.profiles[0]
    thickness = f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m"
    composite = {
        "thickness": thickness,
        "concentration": f"{profile.value.magnitude_si:.15g} 1/m^3",
        "profile": profile.kind,
        "species": profile.species.value,
    }
    assert plan_authority_issues(single, _intent("regions.parameters", composite)) == []
    wrong = {**composite, "species": "donor"}
    issues = plan_authority_issues(single, _intent("regions.parameters", wrong))
    assert [i["intent_path"] for i in issues] == ["regions.parameters"]


def test_an_owner_prefixed_key_names_the_owners_field():
    spec = _spec()
    region = spec.regions[0]
    profile = spec.profiles[0]
    composite = {
        "region_thickness": f"{region.x1.magnitude_si - region.x0.magnitude_si:.15g} m",
        "concentration": f"{profile.value.magnitude_si:.15g} 1/m^3",
        "profile": profile.kind,
        "species": profile.species.value,
    }
    assert plan_authority_issues(spec, _intent("profiles.parameters", composite)) == []
    composite["region_thickness"] = "123 nm"
    assert plan_authority_issues(spec, _intent("profiles.parameters", composite)) != []
