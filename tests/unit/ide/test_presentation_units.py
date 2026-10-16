import pytest

from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult
from tcad_agent.results.presentation import display_projection


def result(unit="F/m^2"):
    return CanonicalResult(
        backend="devsim",
        status="completed",
        axes={"v": ScientificAxis(id="v", kind="bias", label="Voltage", unit="V", values=(0, 1))},
        datasets={
            "capacitance__arbitrary": Dataset(
                id="capacitance__arbitrary",
                label="Capacitance",
                unit=unit,
                axes=("v",),
                shape=(2,),
                values=(0.003, 0.004),
            )
        },
    )


def test_density_unit_projection_preserves_canonical_numbers():
    original = result()
    projection = display_projection(original, {"capacitance": "F/cm^2"})
    assert projection["capacitance__arbitrary"]["scale"] == pytest.approx(1e-4)
    assert projection["capacitance__arbitrary"]["unit"] == "F/cm^2"
    assert original.datasets["capacitance__arbitrary"].values == (0.003, 0.004)


@pytest.mark.parametrize("unit", ["F", "V", "made_up_unit"])
def test_absolute_capacitance_cannot_be_obtained_by_density_unit_conversion(unit):
    with pytest.raises(ValueError):
        display_projection(result(), {"capacitance": unit})


def test_unmatched_unit_request_is_not_silently_ignored():
    with pytest.raises(ValueError, match="unavailable"):
        display_projection(result(), {"hole_density": "cm^-3"})


def test_affine_temperature_projection_is_explicit():
    projection = display_projection(result("K"), {"capacitance": "degC"})
    assert projection["capacitance__arbitrary"]["scale"] == 1
    assert projection["capacitance__arbitrary"]["offset"] == pytest.approx(-273.15)


def test_portable_spec_preserves_requested_display_units(valid_spec):
    payload = valid_spec.model_dump(mode="json")
    payload["display_units"] = {"electron_density": "cm^-3"}
    spec = type(valid_spec).model_validate(payload)
    assert spec.display_units == {"electron_density": "cm^-3"}


def test_capacitance_density_is_a_quantity_alias_not_an_absolute_quantity(valid_spec):
    payload = valid_spec.model_dump(mode="json")
    payload["display_units"] = {"capacitance_density": "nF/cm^2"}
    spec = type(valid_spec).model_validate(payload)
    assert spec.display_units == {"capacitance": "nF/cm^2"}
    converted = display_projection(result(), spec.display_units)
    assert converted["capacitance__arbitrary"]["scale"] == pytest.approx(1e5)


def test_incompatible_portable_display_request_is_refused_before_simulation(valid_spec):
    payload = valid_spec.model_dump(mode="json")
    payload["display_units"] = {"capacitance": "V"}
    with pytest.raises(ValueError, match="incompatible"):
        type(valid_spec).model_validate(payload)


def test_unknown_quantity_cannot_run_hours_then_lose_results_to_report_error(valid_spec):
    payload = valid_spec.model_dump(mode="json")
    payload["display_units"] = {"unregistered_quantity": "V"}
    with pytest.raises(ValueError, match="Unknown"):
        type(valid_spec).model_validate(payload)


@pytest.mark.parametrize("name", ["carrier_density", "carrier_concentration"])
def test_portable_carrier_unit_group_expands_without_changing_the_observable(valid_spec, name):
    payload = valid_spec.model_dump(mode="json")
    payload["display_units"] = {name: "cm^-3", "potential": "mV"}
    spec = type(valid_spec).model_validate(payload)
    assert spec.display_units == {
        "electron_density": "cm^-3",
        "hole_density": "cm^-3",
        "potential": "mV",
    }
    assert spec.observables == valid_spec.observables


def test_group_and_individual_unit_conflicts_are_not_silently_overwritten(valid_spec):
    payload = valid_spec.model_dump(mode="json")
    payload["display_units"] = {"carrier_density": "cm^-3", "electron_density": "m^-3"}
    with pytest.raises(ValueError, match="Conflicting"):
        type(valid_spec).model_validate(payload)
