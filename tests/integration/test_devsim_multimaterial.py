from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_silicon_dielectric_stack_runs_one_portable_electrostatic_path(tmp_path: Path) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "arbitrary-mixed-stack",
            "dimension": 1,
            "regions": [
                {
                    "id": "insulating_layer",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "10 nm",
                    "mesh_spacing": "0.5 nm",
                },
                {
                    "id": "semiconductor_layer",
                    "material": "silicon",
                    "x0": "10 nm",
                    "x1": "1.01 um",
                    "mesh_spacing": "10 nm",
                },
            ],
            "interfaces": [
                {
                    "id": "layer_boundary",
                    "left_region": "insulating_layer",
                    "right_region": "semiconductor_layer",
                }
            ],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "semiconductor_layer",
                    "species": "acceptor",
                    "value": "1e16 cm^-3",
                }
            ],
            "contacts": [
                {"id": "control", "location": "x_min", "kind": "ideal_gate"},
                {"id": "reference", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {"equations": ["poisson"], "models": ["boltzmann"]},
            "study": {"kind": "equilibrium"},
            "observables": ["potential", "electric_field", "terminal_charge"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    job = adapter.compile(spec, tmp_path / "mixed")
    native = LocalRunner(devsim_python=resolve_devsim_python(ROOT)).run(
        job, RunBudget(seconds=120)
    )

    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.datasets["potential"].values
    assert result.datasets["electric_field"].centering == "edge"
    assert result.operating_points[0].terminal_charges_c_per_m2
