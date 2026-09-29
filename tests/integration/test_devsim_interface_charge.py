from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[2]


def _dielectric_stack(charge: str | None) -> ExperimentSpec:
    interface: dict[str, object] = {
        "id": "middle",
        "left_region": "left_layer",
        "right_region": "right_layer",
    }
    if charge is not None:
        interface["fixed_charge_density"] = charge
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "two dielectric layers",
            "dimension": 1,
            "regions": [
                {
                    "id": "left_layer",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "50 nm",
                    "mesh_spacing": "1 nm",
                },
                {
                    "id": "right_layer",
                    "material": "silicon_dioxide",
                    "x0": "50 nm",
                    "x1": "100 nm",
                    "mesh_spacing": "1 nm",
                },
            ],
            "interfaces": [interface],
            "profiles": [],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ideal_gate"},
                {"id": "right", "location": "x_max", "kind": "ideal_gate"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {"kind": "equilibrium"},
            "observables": [
                "potential",
                "electric_field",
                "terminal_charge",
                "interface_charge_density",
            ],
        }
    )


@pytest.mark.integration
def test_fixed_interface_charge_changes_field_and_balances_terminal_charge(
    tmp_path: Path,
) -> None:
    adapter = DevsimAdapter.from_defaults()
    spec = _dielectric_stack("1e11 cm^-2")
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "charged-interface"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    field = result.datasets["electric_field"].values
    midpoint = len(field) // 2
    assert sum(field[:midpoint]) / midpoint > 0
    assert sum(field[midpoint:]) / (len(field) - midpoint) < 0
    terminal_charge = sum(result.operating_points[0].terminal_charges_c_per_m2.values())
    sheet_charge = 1.602176634e-19 * 1.0e15
    assert terminal_charge == pytest.approx(sheet_charge, rel=0.03)
    assert result.datasets["interface_charge_density"].values == pytest.approx(
        (sheet_charge,)
    )
    report = ValidationEngine().validate(result, spec=spec)
    assert report.checks_by_id["contact-charge-balance"].status == "passed"


@pytest.mark.integration
def test_zero_interface_charge_reduces_to_continuous_zero_field(tmp_path: Path) -> None:
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(_dielectric_stack(None), tmp_path / "neutral-interface"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert max(abs(value) for value in result.datasets["electric_field"].values) < 1e-6
