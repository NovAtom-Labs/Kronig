from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_one_dimensional_velocity_saturation_matches_uniform_resistor_reference(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "uniform high-field slab",
            "dimension": 1,
            "regions": [
                {
                    "id": "slab",
                    "material": "silicon",
                    "x0": "0 um",
                    "x1": "1 um",
                    "mesh_spacing": "0.02 um",
                }
            ],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "slab",
                    "species": "donor",
                    "value": "1e16 cm^-3",
                }
            ],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": [
                    "boltzmann",
                    "constant_mobility",
                    "high_field_saturation",
                    "srh",
                ],
            },
            "study": {
                "kind": "dc_points",
                "contact": "right",
                "values": ["0 V", "5 V"],
                "strategy": "adaptive",
                "minimum_step": "0.01 V",
                "maximum_retries": 12,
            },
            "observables": [
                "terminal_current",
                "electric_field",
                "electron_mobility",
                "electron_density",
                "net_doping",
                "total_current_density",
            ],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "high-field"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.datasets["net_doping"].values[0] == pytest.approx(1e22)
    mobility = result.datasets["electron_mobility"]
    assert mobility.centering == "edge"
    assert min(mobility.values) < 0.7 * 400e-4
    field_v_per_cm = 5.0 / 1e-4
    low_field_mobility = 400.0
    saturation_velocity = 1.0e7
    expected_mobility = 2 * low_field_mobility / (
        1 + (1 + 4 * (low_field_mobility * field_v_per_cm / saturation_velocity) ** 2)
        ** 0.5
    )
    expected_current = 1.602176634e-19 * 1e16 * expected_mobility * field_v_per_cm
    measured = abs(result.datasets["terminal_current__right"].values[-1]) / 1e4
    assert measured == pytest.approx(expected_current, rel=0.12)
