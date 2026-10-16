import pytest

from tcad_agent.reporting.markdown import MarkdownReport
from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationReport


@pytest.mark.parametrize(
    "quantity,canonical,requested,value,expected",
    [
        ("terminal_current", "A/m^2", "mA/cm^2", 100.0, "1.000000e+01"),
        ("terminal_charge", "C/m^2", "nC/cm^2", 0.001, "1.000000e+02"),
        ("complex_admittance", "S/m^2", "mS/cm^2", 100.0, "real 1.000000e+01"),
    ],
)
def test_root_selected_terminal_units_are_rendered_in_report(
    valid_spec, quantity, canonical, requested, value, expected
):
    name = quantity + "__contact"
    result = CanonicalResult(
        backend="devsim", status="completed",
        axes={"bias": ScientificAxis(
            id="bias", kind="bias", label="Bias", unit="V", values=(0.0,)
        )},
        datasets={name: Dataset(
            id=name, label=quantity, unit=canonical, axes=("bias",), shape=(1,),
            values=(value,),
            imaginary_values=(value / 2,) if quantity == "complex_admittance" else None,
        )},
    )
    spec = valid_spec.model_copy(update={"display_units": {quantity: requested}})
    text = MarkdownReport().render(spec, result, ValidationReport(overall="passed", checks=()))
    assert requested in text
    assert expected in text
    if quantity == "complex_admittance":
        assert "imaginary 5.000000e+00" in text
    assert result.datasets[name].values == (value,)


def test_failed_result_still_has_a_report_and_unavailable_unit_requested_outputs(valid_spec):
    spec = valid_spec.model_copy(update={"display_units": {"capacitance": "F/cm^2"}})
    result = CanonicalResult(backend="devsim", status="timed_out")
    text = MarkdownReport().render(spec, result, ValidationReport(overall="failed", checks=()))
    assert "unavailable" in text
    assert "Outcome:** Failed" in text


def test_failed_ac_sample_is_not_published_as_zero_capacitance(valid_spec):
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        axes={
            "f": ScientificAxis(
                id="f", kind="frequency", label="Frequency", unit="Hz", values=(1e3, 2e3)
            )
        },
        datasets={
            "ac_capacitance__g": Dataset(
                id="ac_capacitance__g",
                label="Capacitance",
                unit="F/m^2",
                axes=("f",),
                shape=(2,),
                values=(0.003, 0),
                validity=(True, False),
            )
        },
    )
    text = MarkdownReport().render(
        valid_spec, result, ValidationReport(overall="failed", checks=())
    )
    assert "unavailable (failed sample)" in text
    assert "| 2.000000e+03 | 0.000000e+00 |" not in text
