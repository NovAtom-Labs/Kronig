"""The controller must reject a small damped update or incomplete evidence."""

import copy
import math

import pytest

from tcad_agent.adapters.devsim.density_solver import NativeDensitySolver
from tcad_agent.adapters.devsim.runtime import physical_density_update_certificate


class NativeBoundary:
    """Only the expensive native solve/API boundary is replaced in these tests."""

    def __init__(self, scales, *, omit_carrier=False, nonfinite=False):
        self.scales = iter(scales)
        self.calls = []
        self.owner = None
        self.nonfinite = nonfinite
        names = ["PotentialEquation", "ElectronContinuityEquation", "HoleContinuityEquation"]
        if omit_carrier:
            names.pop()
        self.iteration = {
            "devices": [
                {
                    "name": "native",
                    "regions": [
                        {
                            "name": "r",
                            "equations": [
                                {"name": name, "absolute_error": 0.0, "relative_error": 0.0}
                                for name in names
                            ],
                        }
                    ],
                }
            ]
        }

    def get_parameter(self, **scope):
        return (lambda **arguments: {}) if scope["name"] == "solver_callback" else 0.025

    def get_node_model_values(self, **scope):
        if scope["name"] in {"Electrons", "Holes"}:
            return [1e17, 1e17]
        if scope["name"].startswith("Physical"):
            return [math.nan if self.nonfinite else 0.0, 0.0]
        raise AssertionError("Unspecified native evidence requested")

    def solve(self, **arguments):
        self.calls.append(arguments)
        self.owner.last_scale = next(self.scales)
        return {"converged": True, "iterations": [copy.deepcopy(self.iteration)]}


def controller(native):
    result = NativeDensitySolver(
        native,
        "native",
        {"regions": [{"id": "r", "material": "silicon"}]},
        physical_density_update_certificate,
    )
    native.owner = result
    return result


def test_scaled_final_newton_direction_cannot_be_accepted_as_physical_convergence():
    native = NativeBoundary([1e-12, 1.0])
    solve = controller(native)
    solve.solve(type="dc", absolute_error=1e10, relative_error=1e-6, maximum_iterations=2)
    assert len(native.calls) == 2
    assert [call["maximum_iterations"] for call in native.calls] == [2, 1]
    assert solve.last_certificate["final_step_scale"] == 1
    assert solve.last_certificate["passed"] is True


def test_only_scaled_updates_exhaust_the_original_allowance_instead_of_succeeding():
    native = NativeBoundary([1e-12])
    with pytest.raises(RuntimeError, match="convergence allowance exhausted"):
        controller(native).solve(
            type="dc", absolute_error=1e10, relative_error=1e-6, maximum_iterations=1
        )


@pytest.mark.parametrize("invalid", ["omit_carrier", "nonfinite"])
def test_native_missing_or_nonfinite_evidence_is_never_convergence(invalid):
    native = NativeBoundary([1.0], **{invalid: True})
    with pytest.raises(ValueError):
        controller(native).solve(
            type="dc", absolute_error=1e10, relative_error=1e-6, maximum_iterations=1
        )
