from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_piecewise_constant_profile_is_preserved_in_canonical_donor_field(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "piecewise profile",
            "dimension": 1,
            "regions": [
                {
                    "id": "bulk",
                    "material": "silicon",
                    "x0": "0 um",
                    "x1": "1 um",
                    "mesh_spacing": "0.05 um",
                }
            ],
            "profiles": [
                {
                    "kind": "piecewise_constant",
                    "region": "bulk",
                    "species": "donor",
                    "boundaries": ["0 um", "0.5 um", "1 um"],
                    "values": ["1e15 cm^-3", "1e17 cm^-3"],
                }
            ],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "mesh_anchors": [{"position": "0.45 um", "spacing": "0.01 um"}],
            "physics": {"equations": ["poisson"]},
            "study": {"kind": "equilibrium"},
            "observables": ["potential", "donor_concentration", "net_doping"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "piecewise"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    donors = result.datasets["donor_concentration"]
    position_axis = result.axes[donors.axes[0]].values
    assert donors.values[1] == pytest.approx(1e21)
    right_value = next(
        value
        for position, value in zip(position_axis, donors.values, strict=True)
        if position > 0.5e-6
    )
    assert right_value == pytest.approx(1e23)
    assert any(abs(position - 0.45e-6) < 1e-15 for position in position_axis)
