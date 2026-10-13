"""Numerical regressions for cancellation and explicit arithmetic provenance."""

from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[2]


def asymmetric_spec(spacing_nm: float = 5.0) -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "cancellation-regression",
            "dimension": 1,
            "regions": [
                {
                    "id": "p",
                    "material": "silicon",
                    "x0": "0 um",
                    "x1": "0.6 um",
                    "mesh_spacing": f"{spacing_nm} nm",
                },
                {
                    "id": "n",
                    "material": "silicon",
                    "x0": "0.6 um",
                    "x1": "1.5 um",
                    "mesh_spacing": f"{spacing_nm} nm",
                },
            ],
            "interfaces": [{"id": "join", "left_region": "p", "right_region": "n"}],
            "mesh_anchors": [{"position": "0.6 um", "spacing": f"{spacing_nm / 5} nm"}],
            "profiles": [
                {"kind": "constant", "region": "p", "species": "acceptor", "value": "3e16 cm^-3"},
                {"kind": "constant", "region": "n", "species": "donor", "value": "7e16 cm^-3"},
            ],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": ["boltzmann", "klaassen_mobility", "srh"],
                "temperature": "300 K",
                "parameters": {"electron_lifetime": "1 us", "hole_lifetime": "1 us"},
            },
            "study": {
                "kind": "dc_points",
                "contact": "left",
                "values": ["-0.2 V", "0 V", "0.15 V"],
            },
            "observables": ["terminal_current", "potential", "electron_density", "hole_density"],
        }
    )


@pytest.mark.integration
@pytest.mark.parametrize("spacing_nm", [5.0, 2.5])
def test_default_precision_conserves_small_terminal_currents(
    tmp_path: Path,
    spacing_nm: float,
) -> None:
    spec = asymmetric_spec(spacing_nm)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "precision"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    check = (
        ValidationEngine().validate(result, spec=spec).checks_by_id["terminal-current-conservation"]
    )
    assert check.status == "passed", check.model_dump_json()
    assert result.metadata["numerical_precision"]["effective"] == "extended"
    assert result.metadata["numerical_precision"]["requested"] == "backend_default"
    assert result.metadata["numerical_precision"]["resolved"] == "extended"
    assert result.metadata["numerical_precision"]["native_parameters"] == {
        "extended_model": True,
        "extended_equation": True,
        "extended_solver": True,
    }


@pytest.mark.integration
@pytest.mark.parametrize("ac", [False, True])
def test_adaptive_transport_preserves_state_across_full_gate_bias_schedule(
    tmp_path: Path, ac: bool
):
    schedule = {
        "kind": "dc",
        "contact": "gate",
        "start": "-5 V",
        "stop": "5 V",
        "step": "0.1 V",
        "strategy": "adaptive",
        "minimum_step": "1 mV",
        "maximum_retries": 16,
    }
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "bounded-recovery-regression",
            "dimension": 1,
            "regions": [
                {
                    "id": "oxide",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "10 nm",
                    "mesh_spacing": "0.5 nm",
                },
                {
                    "id": "substrate",
                    "material": "silicon",
                    "x0": "10 nm",
                    "x1": "1.01 um",
                    "mesh_spacing": "5 nm",
                },
            ],
            "interfaces": [{"id": "join", "left_region": "oxide", "right_region": "substrate"}],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "substrate",
                    "species": "acceptor",
                    "value": "1e16 cm^-3",
                }
            ],
            "contacts": [
                {
                    "id": "gate",
                    "location": "x_min",
                    "kind": "ideal_gate",
                    "work_function": "4.1 eV",
                },
                {"id": "bulk", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": ["boltzmann", "constant_mobility", "srh"],
                "temperature": "300 K",
            },
            "study": {
                "kind": "ac",
                "contact": "gate",
                "frequency": "1 MHz",
                "amplitude": "10 mV",
                "bias_schedule": schedule,
            }
            if ac
            else schedule,
            "observables": [
                "terminal_charge",
                "potential",
                "electric_field",
                "electron_density",
                "hole_density",
            ],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "transport-schedule"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    assert len(result.bias_points) == 101
    assert all(point.converged for point in result.bias_points)
    events = result.metadata["solver_events"]
    predictors = [event for event in events if event["phase"] == "stationary_equilibrium_predictor"]
    assert len(predictors) == 101
    assert all(event["carrier_equations_restored_before_verification"] for event in predictors)
    assert (
        len(
            [
                event
                for event in events
                if event["phase"] == "requested_operating_point" and event["outcome"] == "converged"
            ]
        )
        == 101
    )
    report = ValidationEngine().validate(result, spec=spec)
    assert report.checks_by_id["terminal-current-conservation"].status == "passed"
    if ac:
        dataset = result.datasets["ac_capacitance__gate"]
        assert dataset.shape == (101, 1)
        assert all(dataset.validity)
        assert report.checks_by_id["small-signal-grid-complete"].status == "passed"
        # At strong inversion the finite-frequency carrier response must differ
        # from the stationary charge derivative. Leaving the predictor's
        # Poisson-only equations active would instead return the static response.
        assert dataset.values[-1] < 0.2 * result.datasets["capacitance__gate"].values[-1]
