import pytest

from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.derive import DerivationRegistry
from tcad_agent.results.models import OperatingPoint


def test_generic_extrema_gradient_integral_and_endpoint_difference() -> None:
    axis = ScientificAxis(
        id="x", kind="position", label="Position", unit="m", values=(0.0, 1.0, 2.0)
    )
    dataset = Dataset(
        id="potential",
        label="Potential",
        unit="V",
        axes=("x",),
        shape=(3,),
        values=(0.0, 1.0, 4.0),
    )
    registry = DerivationRegistry.default()

    assert registry.scalar("maximum", dataset, {"x": axis}).value == 4.0
    assert registry.scalar("endpoint_difference", dataset, {"x": axis}).value == 4.0
    assert registry.scalar("integral", dataset, {"x": axis}).value == pytest.approx(3.0)
    gradient = registry.dataset("gradient", dataset, {"x": axis})
    assert gradient.values == pytest.approx((1.0, 2.0, 3.0))
    assert gradient.unit == "V/m"


def test_capacitance_is_derived_from_charge_and_voltage_axes() -> None:
    voltage = ScientificAxis(
        id="voltage", kind="bias", label="Gate bias", unit="V", values=(-1.0, 0.0, 1.0)
    )
    charge = Dataset(
        id="terminal_charge",
        label="Terminal charge density",
        unit="C/m^2",
        axes=("voltage",),
        shape=(3,),
        values=(-2e-3, 0.0, 4e-3),
    )

    capacitance = DerivationRegistry.default().dataset(
        "derivative", charge, {"voltage": voltage}
    )

    assert capacitance.unit == "C/m^2/V"
    assert capacitance.values == pytest.approx((2e-3, 3e-3, 4e-3))


def test_current_balance_uses_canonical_operating_point_currents() -> None:
    point = OperatingPoint(
        index=0,
        state="converged",
        coordinates={"bias": 0.0},
        terminal_currents_a_per_m2={"left": 2.0, "right": -1.999999},
    )

    balance = DerivationRegistry.current_balance(point)

    assert balance.value == pytest.approx(1e-6)
    assert balance.unit == "A/m^2"
