"""Fixed reported points do not require a single unconditioned Newton jump."""

import copy

import pytest

from tcad_agent.adapters.devsim import runtime


@pytest.mark.parametrize("temperature", [250.0, 300.0, 360.0])
def test_fixed_positive_density_grid_gets_native_thermal_starting_controls(temperature):
    original = {
        "kind": "dc_points",
        "values_v": [-1.7, 0.0, 1.4],
        "strategy": "fixed",
        "maximum_retries": 6,
    }
    untouched = copy.deepcopy(original)
    controls = runtime._native_dc_starting_controls(original, temperature, True)
    assert original == untouched
    assert controls["values_v"] == original["values_v"]
    assert controls["maximum_retries"] == original["maximum_retries"]
    assert controls["strategy"] == "adaptive"
    assert controls["minimum_step_v"] == pytest.approx(8.617333262145e-5 * temperature / 128)
    assert abs(runtime._initial_dc_bias(0, -1.7, temperature, controls)) < 1.7


def test_explicit_adaptive_controls_and_other_solver_paths_are_unchanged():
    adaptive = {"strategy": "adaptive", "minimum_step_v": 0.004, "maximum_retries": 2}
    assert runtime._native_dc_starting_controls(adaptive, 300, True) == adaptive
    fixed = {"strategy": "fixed", "maximum_retries": 0}
    assert runtime._native_dc_starting_controls(fixed, 300, False) == fixed
    assert runtime._native_dc_starting_controls(fixed, 300, True)["maximum_retries"] == 0
