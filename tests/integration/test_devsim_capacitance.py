from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_terminal_charge_sweep_produces_generic_quasistatic_capacitance(tmp_path: Path) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "charge-voltage-stack",
            "dimension": 1,
            "regions": [
                {
                    "id": "layer_a",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "10 nm",
                    "mesh_spacing": "0.5 nm",
                },
                {
                    "id": "layer_b",
                    "material": "silicon",
                    "x0": "10 nm",
                    "x1": "1.01 um",
                    "mesh_spacing": "10 nm",
                },
            ],
            "interfaces": [
                {"id": "ab", "left_region": "layer_a", "right_region": "layer_b"}
            ],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "layer_b",
                    "species": "acceptor",
                    "value": "1e16 cm^-3",
                }
            ],
            "contacts": [
                {"id": "control", "location": "x_min", "kind": "ideal_gate"},
                {"id": "reference", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {"equations": ["poisson"], "models": ["boltzmann"]},
            "study": {
                "kind": "dc",
                "contact": "control",
                "start": "-1 V",
                "stop": "1 V",
                "step": "0.5 V",
                "strategy": "adaptive",
                "minimum_step": "10 mV",
                "maximum_retries": 10,
            },
            "observables": ["terminal_charge", "potential", "electric_field"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "charge-voltage"), RunBudget(seconds=120)
    )

    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.datasets["terminal_charge__control"].unit == "C/m^2"
    assert result.datasets["capacitance__control"].unit == "F/m^2"
    assert len(result.datasets["capacitance__control"].values) == 5
