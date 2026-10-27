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


def test_peak_location_average_and_builtin_potential_use_canonical_values() -> None:
    axis = ScientificAxis(
        id="x", kind="position", label="Position", unit="m", values=(0.0, 1.0, 2.0)
    )
    field = Dataset(
        id="electric_field",
        label="Electric field",
        unit="V/m",
        axes=("x",),
        shape=(3,),
        values=(-2.0, 5.0, -4.0),
    )
    potential = Dataset(
        id="potential",
        label="Potential",
        unit="V",
        axes=("x",),
        shape=(3,),
        values=(-0.2, 0.1, 0.7),
    )
    registry = DerivationRegistry.default()

    peak = registry.scalar("peak_magnitude", field, {"x": axis})
    assert peak.value == 5.0
    assert peak.coordinate == 1.0
    assert peak.coordinate_unit == "m"
    assert registry.scalar("average", field, {"x": axis}).value == pytest.approx(-1 / 3)
    assert registry.scalar("built_in_potential", potential, {"x": axis}).value == pytest.approx(
        0.9
    )


def test_resistance_is_derived_from_compatible_canonical_voltage_and_current() -> None:
    axis = ScientificAxis(
        id="bias", kind="bias", label="Bias", unit="V", values=(0.0, 1.0, 2.0)
    )
    voltage = Dataset(
        id="applied_voltage",
        label="Applied voltage",
        unit="V",
        axes=("bias",),
        shape=(3,),
        centering="operating_point",
        values=(0.0, 1.0, 2.0),
    )
    current = Dataset(
        id="terminal_current__right",
        label="Terminal current density",
        unit="A/m^2",
        axes=("bias",),
        shape=(3,),
        centering="operating_point",
        values=(0.0, 0.5, 1.0),
    )

    resistance = DerivationRegistry.resistance(voltage, current, {"bias": axis})

    assert resistance.unit == "ohm*m^2"
    assert resistance.values == pytest.approx((0.0, 2.0, 2.0))
    assert resistance.validity == (False, True, True)
    assert resistance.source == "derived:ratio:applied_voltage/terminal_current__right"


def test_resistance_refuses_incompatible_axes_or_units() -> None:
    axis = ScientificAxis(
        id="bias", kind="bias", label="Bias", unit="V", values=(0.0, 1.0)
    )
    voltage = Dataset(
        id="applied_voltage",
        label="Applied voltage",
        unit="V",
        axes=("bias",),
        shape=(2,),
        centering="operating_point",
        values=(0.0, 1.0),
    )
    incompatible = Dataset(
        id="terminal_current",
        label="Current",
        unit="V",
        axes=("bias",),
        shape=(2,),
        centering="operating_point",
        values=(1.0, 1.0),
    )

    with pytest.raises(ValueError, match="canonical current"):
        DerivationRegistry.resistance(voltage, incompatible, {"bias": axis})


def _transfer(values):
    axis = ScientificAxis(
        id="vg", kind="bias", label="Gate bias", unit="V", values=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    )
    dataset = Dataset(
        id="drain_current", label="Drain current", unit="A", axes=("vg",), shape=(6,), values=values
    )
    return dataset, {"vg": axis}


def test_device_metrics_recover_a_known_transfer_curve() -> None:
    # Off below 0.4 V at one decade per 0.1 V, then ohmic: I = 1e-3 * (Vg - 0.5) above it.
    values = (1e-12, 1e-10, 1e-8, 1e-4, 3e-4, 5e-4)
    dataset, axes = _transfer(values)
    registry = DerivationRegistry.default()
    gm = registry.scalar("maximum_transconductance", dataset, axes)
    assert gm.value == pytest.approx(1e-3, rel=0.2) and gm.unit == "A/V"
    vt = registry.scalar("threshold_voltage", dataset, axes)
    assert vt.value == pytest.approx(0.5, abs=0.06) and vt.unit == "V"
    swing = registry.scalar("subthreshold_swing", dataset, axes)
    assert swing.value == pytest.approx(100.0) and swing.unit == "mV/dec"  # 0.2 V per 2 decades
    assert registry.scalar("on_off_ratio", dataset, axes).value == pytest.approx(5e8)


def test_device_metrics_refuse_what_the_sweep_cannot_support() -> None:
    dataset, axes = _transfer((1e-3,) * 6)
    registry = DerivationRegistry.default()
    with pytest.raises(ValueError):
        registry.scalar("subthreshold_swing", dataset, axes)
    with pytest.raises(ValueError):
        registry.scalar("threshold_voltage", dataset, axes)
