import pytest
from pydantic import ValidationError

from tcad_agent.domain.models import Contact, ExperimentSpec, Observable
from tcad_agent.domain.units import QuantityValue


def minimal_spec() -> dict:
    return {
        "schema_version": "1.0",
        "name": "two-region-study",
        "dimension": 1,
        "regions": [
            {"id": "left", "material": "silicon", "x0": "0 um", "x1": "0.5 um"},
            {"id": "right", "material": "silicon", "x0": "0.5 um", "x1": "1 um"},
        ],
        "profiles": [
            {
                "kind": "constant",
                "region": "left",
                "species": "acceptor",
                "value": "1e17 cm^-3",
            },
            {
                "kind": "constant",
                "region": "right",
                "species": "donor",
                "value": "1e16 cm^-3",
            },
        ],
        "contacts": [
            {"id": "anode", "location": "x_min", "kind": "ohmic"},
            {"id": "cathode", "location": "x_max", "kind": "ohmic"},
        ],
        "physics": {"equations": ["poisson", "electron_continuity", "hole_continuity"]},
        "study": {
            "kind": "dc",
            "contact": "anode",
            "start": "0 V",
            "stop": "0.2 V",
            "step": "0.1 V",
        },
        "observables": [
            "terminal_current",
            "potential",
            "electron_density",
            "hole_density",
        ],
    }


def test_rejects_unknown_keys() -> None:
    data = minimal_spec() | {"device_type": "pn_diode"}
    with pytest.raises(ValidationError, match="device_type"):
        ExperimentSpec.model_validate(data)


def test_rejects_incompatible_units() -> None:
    data = minimal_spec()
    data["regions"][0]["x1"] = "5 V"
    with pytest.raises(ValidationError, match="length"):
        ExperimentSpec.model_validate(data)


def test_rejects_gaps_between_regions() -> None:
    data = minimal_spec()
    data["regions"][1]["x0"] = "0.6 um"
    with pytest.raises(ValidationError, match="contiguous"):
        ExperimentSpec.model_validate(data)


def test_normalization_is_independent_of_input_units() -> None:
    first = ExperimentSpec.model_validate(minimal_spec()).normalized()
    second_data = minimal_spec()
    second_data["regions"][0]["x1"] = "500 nm"
    second = ExperimentSpec.model_validate(second_data).normalized()
    assert first == second


def test_normalized_spec_round_trips_through_persistence() -> None:
    spec = ExperimentSpec.model_validate(minimal_spec())
    assert ExperimentSpec.model_validate(spec.normalized()) == spec


def test_canonical_quantity_accepts_equivalent_dimensionality_factor_order() -> None:
    quantity = QuantityValue.model_validate(
        {
            "magnitude_si": 0.2,
            "si_unit": "kilogram * meter ** 2 / ampere / second ** 3",
            "dimensionality": "[mass] * [length] ** 2 / [time] ** 3 / [current]",
        }
    )

    assert quantity.to("V") == pytest.approx(0.2)


def test_default_temperature_is_validated_as_a_quantity() -> None:
    spec = ExperimentSpec.model_validate(minimal_spec())
    assert spec.physics.temperature.to("K") == 300.0


def test_metal_contact_requires_energy_work_function() -> None:
    contact = Contact.model_validate(
        {
            "id": "anode",
            "location": "x_min",
            "kind": "metal_work_function",
            "work_function": "4.10 eV",
        }
    )
    assert contact.work_function is not None
    assert contact.work_function.to("eV") == pytest.approx(4.10)


def test_metal_contact_rejects_missing_work_function() -> None:
    with pytest.raises(ValidationError, match="metal work-function contact"):
        Contact.model_validate(
            {"id": "anode", "location": "x_min", "kind": "metal_work_function"}
        )


def test_ohmic_contact_rejects_work_function() -> None:
    with pytest.raises(ValidationError, match="ohmic contact"):
        Contact.model_validate(
            {
                "id": "anode",
                "location": "x_min",
                "kind": "ohmic",
                "work_function": "4.10 eV",
            }
        )


def test_contact_rejects_voltage_as_work_function() -> None:
    with pytest.raises(ValidationError, match="energy"):
        Contact.model_validate(
            {
                "id": "anode",
                "location": "x_min",
                "kind": "metal_work_function",
                "work_function": "4.10 V",
            }
        )


def test_schema_represents_requested_equilibrium_observables() -> None:
    requested = {
        "charge_density",
        "conduction_band",
        "valence_band",
        "fermi_level",
        "electron_current_density",
        "hole_current_density",
        "electron_mobility",
        "hole_mobility",
        "recombination_rate",
    }
    assert requested <= {observable.value for observable in Observable}
