"""A temporary Poisson-only predictor must restore full carrier equations."""

from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_refined_fermi_sweep_converges_without_adding_recombination(tmp_path):
    from tcad_agent.validation.engine import ValidationEngine

    spec = ExperimentSpec.model_validate_json(
        (ROOT / "tests/fixtures/devsim/insulated-gate-fermi.json").read_text()
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "native"), RunBudget(seconds=400)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    assert len(result.bias_points) == 101
    assert all(point.converged for point in result.bias_points)
    assert result.metadata["physics_models"] == ["fermi"]
    for name in ("electron_quasi_fermi_level", "hole_quasi_fermi_level"):
        values = result.datasets[name].values
        assert max(values) - min(values) < 1e-6
    report = ValidationEngine().validate(result, spec=spec)
    for name in (
        "terminal-current-conservation",
        "electric-field-potential-gradient",
        "poisson-residual-consistency",
        "contact-charge-balance",
    ):
        assert report.checks_by_id[name].status == "passed", report.checks_by_id[name]


@pytest.mark.integration
def test_fermi_gate_predictor_restores_positive_density_coordinates_and_converges(tmp_path):
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "arbitrary-layered-study",
            "dimension": 1,
            "regions": [
                {
                    "id": "oxide",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "10 nm",
                    "mesh_spacing": "5 nm",
                },
                {
                    "id": "substrate",
                    "material": "silicon",
                    "x0": "10 nm",
                    "x1": "110 nm",
                    "mesh_spacing": "10 nm",
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
                "models": ["fermi", "constant_mobility", "srh"],
                "temperature": "300 K",
            },
            "study": {
                "kind": "dc_points",
                "contact": "gate",
                "values": ["0 V"],
                "strategy": "adaptive",
                "minimum_step": "0.001 V",
                "maximum_retries": 0,
            },
            "observables": [
                "potential",
                "electron_density",
                "hole_density",
                "electron_quasi_fermi_level",
                "hole_quasi_fermi_level",
                "terminal_current",
            ],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "native"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    assert all(point.converged for point in result.bias_points), result.bias_points
    assert (
        max(
            abs(value)
            for point in result.bias_points
            for value in point.terminal_currents_a_per_m2.values()
        )
        < 1e-6
    )
    for field in ("electron_density", "hole_density"):
        assert min(result.datasets[field].values) > 0
