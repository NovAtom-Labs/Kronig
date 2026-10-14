"""Original-density acceptance must survive any solver coordinate conversion."""

import copy
import math

import pytest

from tcad_agent.adapters.devsim import runtime


def _iteration():
    return {
        "devices": [
            {
                "name": "native",
                "regions": [
                    {
                        "name": "a",
                        "equations": [
                            {
                                "name": "PotentialEquation",
                                "absolute_error": 0.25,
                                "relative_error": 0.125,
                            },
                            {
                                "name": "ElectronContinuityEquation",
                                "absolute_error": math.log(2),
                                "relative_error": 0.01,
                            },
                            {
                                "name": "HoleContinuityEquation",
                                "absolute_error": math.log(4 / 3),
                                "relative_error": 0.01,
                            },
                        ],
                    },
                    {
                        "name": "b",
                        "equations": [
                            {
                                "name": "PotentialEquation",
                                "absolute_error": 0.5,
                                "relative_error": 0.0625,
                            },
                            {
                                "name": "ElectronContinuityEquation",
                                "absolute_error": math.log(1.25),
                                "relative_error": 0.01,
                            },
                            {
                                "name": "HoleContinuityEquation",
                                "absolute_error": 0.0,
                                "relative_error": 0.0,
                            },
                        ],
                    },
                ],
            }
        ]
    }


def _states():
    return {
        "a": {"thermal_voltage_min": 1.0, "electron_density_max": 2.0, "hole_density_max": 3.0},
        "b": {"thermal_voltage_min": 1.0, "electron_density_max": 4.0, "hole_density_max": 5.0},
    }


def test_certificate_uses_physical_density_errors_and_native_global_aggregation():
    result = runtime.physical_density_update_certificate(
        _iteration(), _states(), absolute_limit=4.0, relative_limit=2.0
    )
    assert result["absolute_error_bound"] == pytest.approx(3.25)
    assert result["relative_error_bound"] == pytest.approx(1.7708333333333333)
    assert result["passed"] is True
    assert (
        runtime.physical_density_update_certificate(
            _iteration(), _states(), absolute_limit=4.0, relative_limit=0.5
        )["passed"]
        is False
    )


def test_exact_native_density_updates_preserve_original_thresholds_without_maximum_pairing():
    updates = {
        "a": {
            "ElectronContinuityEquation": {"absolute_error": 0.1, "relative_error": 0.05},
            "HoleContinuityEquation": {"absolute_error": 0.2, "relative_error": 0.1},
        },
        "b": {
            "ElectronContinuityEquation": {"absolute_error": 0.3, "relative_error": 0.075},
            "HoleContinuityEquation": {"absolute_error": 0.0, "relative_error": 0.0},
        },
    }
    result = runtime.physical_density_update_certificate(
        _iteration(),
        _states(),
        absolute_limit=1.0,
        relative_limit=0.5,
        density_updates=updates,
    )
    assert result["absolute_error_bound"] == pytest.approx(0.8)
    assert result["relative_error_bound"] == pytest.approx(0.4125)
    assert result["passed"] is True
    assert (
        runtime.physical_density_update_certificate(
            _iteration(),
            _states(),
            absolute_limit=0.8,
            relative_limit=0.5,
            density_updates=updates,
        )["passed"]
        is False
    )
    del updates["a"]["HoleContinuityEquation"]
    with pytest.raises(ValueError):
        runtime.physical_density_update_certificate(
            _iteration(),
            _states(),
            absolute_limit=1.0,
            relative_limit=0.5,
            density_updates=updates,
        )


@pytest.mark.parametrize("sign", [-1, 1])
def test_certificate_bounds_actual_positive_and_negative_density_updates(sign):
    delta = sign * 0.2
    old = 2.0
    new = old * math.exp(delta)
    iteration = {
        "devices": [
            {
                "name": "native",
                "regions": [
                    {
                        "name": "a",
                        "equations": [
                            {
                                "name": "PotentialEquation",
                                "absolute_error": 0.0,
                                "relative_error": 0.0,
                            },
                            {
                                "name": "ElectronContinuityEquation",
                                "absolute_error": abs(delta),
                                "relative_error": 0.001,
                            },
                            {
                                "name": "HoleContinuityEquation",
                                "absolute_error": 0.0,
                                "relative_error": 0.0,
                            },
                        ],
                    }
                ],
            }
        ]
    }
    state = {
        "a": {"thermal_voltage_min": 1.0, "electron_density_max": new, "hole_density_max": 1.0}
    }
    result = runtime.physical_density_update_certificate(
        iteration, state, absolute_limit=1.0, relative_limit=1.0
    )
    assert result["absolute_error_bound"] >= abs(new - old) - 1e-15
    assert result["relative_error_bound"] >= abs(new - old) / (new + 1e-10) - 1e-15


@pytest.mark.parametrize("absolute,relative", [(3.25, 2.0), (4.0, 1.0)])
def test_density_certificate_never_accepts_threshold_equality(absolute, relative):
    iteration = _iteration()
    for region in iteration["devices"][0]["regions"]:
        for equation in region["equations"]:
            equation.update(absolute_error=0.0, relative_error=0.0)
    iteration["devices"][0]["regions"][0]["equations"][0].update(
        absolute_error=3.25, relative_error=1.0
    )
    assert (
        runtime.physical_density_update_certificate(
            iteration, _states(), absolute_limit=absolute, relative_limit=relative
        )["passed"]
        is False
    )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 0.0])
def test_density_certificate_refuses_invalid_density_or_temperature(bad):
    for field in ("thermal_voltage_min", "electron_density_max", "hole_density_max"):
        states = _states()
        states["a"][field] = bad
        with pytest.raises(ValueError):
            runtime.physical_density_update_certificate(
                _iteration(), states, absolute_limit=4.0, relative_limit=2.0
            )


def test_density_certificate_requires_all_equations_and_regions():
    incomplete = copy.deepcopy(_iteration())
    incomplete["devices"][0]["regions"][0]["equations"].pop()
    with pytest.raises(ValueError):
        runtime.physical_density_update_certificate(
            incomplete, _states(), absolute_limit=4.0, relative_limit=2.0
        )
    incomplete = copy.deepcopy(_iteration())
    incomplete["devices"][0]["regions"].pop()
    with pytest.raises(ValueError):
        runtime.physical_density_update_certificate(
            incomplete, _states(), absolute_limit=4.0, relative_limit=2.0
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_density_certificate_refuses_invalid_native_update_evidence(bad):
    iteration = _iteration()
    iteration["devices"][0]["regions"][0]["equations"][1]["absolute_error"] = bad
    with pytest.raises(ValueError):
        runtime.physical_density_update_certificate(
            iteration, _states(), absolute_limit=4.0, relative_limit=2.0
        )


def test_electrochemical_certificate_includes_potential_in_density_change():
    iteration = _iteration()
    for region in iteration["devices"][0]["regions"]:
        for equation in region["equations"]:
            equation.update(absolute_error=0.0, relative_error=0.0)
    iteration["devices"][0]["regions"][0]["equations"][0].update(
        absolute_error=math.log(2), relative_error=0.01
    )
    result = runtime.physical_density_update_certificate(
        iteration, _states(), absolute_limit=10.0, relative_limit=3.0, potential_coupled=True
    )
    # A potential change moves both densities despite unchanged carrier
    # coordinates. Conservative bounds: 2*1 and 3*1 plus Potential's norm.
    assert result["absolute_error_bound"] == pytest.approx(5 + math.log(2))
    assert result["relative_error_bound"] == pytest.approx(2.01)
    assert result["passed"] is True
    assert (
        runtime.physical_density_update_certificate(
            iteration, _states(), absolute_limit=10.0, relative_limit=1.0, potential_coupled=True
        )["passed"]
        is False
    )
