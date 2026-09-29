from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_uniform_fixed_bulk_charge_matches_integrated_terminal_charge(
    tmp_path: Path,
) -> None:
    thickness_m = 100e-9
    density_c_per_m3 = 1.0
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "uniform charged dielectric",
            "dimension": 1,
            "regions": [
                {
                    "id": "film",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "100 nm",
                    "mesh_spacing": "1 nm",
                }
            ],
            "profiles": [
                {
                    "kind": "fixed_charge",
                    "region": "film",
                    "density": "1 C/m^3",
                }
            ],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ideal_gate"},
                {"id": "right", "location": "x_max", "kind": "ideal_gate"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {"kind": "equilibrium"},
            "observables": [
                "potential",
                "electric_field",
                "fixed_charge_density",
                "terminal_charge",
            ],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "fixed-bulk-charge"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.datasets["fixed_charge_density"].values[0] == pytest.approx(1.0)
    terminal_sum = sum(result.operating_points[0].terminal_charges_c_per_m2.values())
    assert terminal_sum == pytest.approx(
        density_c_per_m3 * thickness_m,
        rel=0.03,
    )
    report = ValidationEngine().validate(result, spec=spec)
    assert report.checks_by_id["contact-charge-balance"].status == "passed"
