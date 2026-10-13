from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.devsim.runtime import configure_numerical_precision
from tcad_agent.domain.models import ExperimentSpec, SolverControls


class PrecisionBackend:
    def __init__(self, supported: bool):
        self.parameters = {"info": {"extended_precision": supported, "version": "test"}}

    def get_parameter(self, *, name):
        return self.parameters[name]

    def set_parameter(self, *, name, value):
        self.parameters[name] = value


def test_extended_precision_fails_before_setting_flags_when_unavailable():
    backend = PrecisionBackend(False)
    with pytest.raises(RuntimeError, match=r"extended precision.*unavailable"):
        configure_numerical_precision(backend, {"precision": "extended"})
    assert set(backend.parameters) == {"info"}


def test_standard_precision_explicitly_disables_all_extended_arithmetic():
    backend = PrecisionBackend(True)
    backend.parameters.update(extended_model=True, extended_equation=True, extended_solver=True)
    record = configure_numerical_precision(backend, {"precision": "standard"})
    assert record["requested"] == record["effective"] == "standard"
    assert record["native_parameters"] == {
        "extended_model": False,
        "extended_equation": False,
        "extended_solver": False,
    }


def test_extended_precision_fails_if_native_setting_does_not_take_effect():
    backend = SimpleNamespace(
        get_parameter=lambda **kwargs: (
            {"extended_precision": True} if kwargs["name"] == "info" else False
        ),
        set_parameter=lambda **kwargs: None,
    )
    with pytest.raises(RuntimeError, match="did not enable"):
        configure_numerical_precision(backend, {"precision": "extended"})


def test_precision_is_a_typed_simulator_neutral_control(valid_spec: ExperimentSpec):
    with pytest.raises(ValidationError, match="precision"):
        SolverControls.model_validate({"precision": "automatic"})
    spec = valid_spec.model_copy(update={"solver": SolverControls(precision="standard")})
    assert DevsimAdapter.from_defaults()._payload(spec).solver.precision == "standard"
