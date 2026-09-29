from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


def intrinsic_temperature_spec() -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "intrinsic slab temperature study",
            "dimension": 1,
            "regions": [
                {
                    "id": "bulk",
                    "material": "silicon",
                    "x0": "0 um",
                    "x1": "1 um",
                    "mesh_spacing": "0.02 um",
                }
            ],
            "profiles": [],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": [
                    "poisson",
                    "electron_continuity",
                    "hole_continuity",
                ],
                "models": ["boltzmann", "constant_mobility", "srh"],
            },
            "study": {
                "kind": "temperature",
                "values": ["250 K", "300 K", "350 K"],
            },
            "observables": [
                "potential",
                "electron_density",
                "hole_density",
                "conduction_band",
            ],
        }
    )


@pytest.mark.integration
def test_temperature_study_rebuilds_models_and_preserves_spatial_fields(
    tmp_path: Path,
) -> None:
    spec = intrinsic_temperature_spec()
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "temperature-study"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.axes["temperature"].values == pytest.approx((250.0, 300.0, 350.0))
    density = result.datasets["electron_density"]
    assert density.axes[0] == "temperature"
    assert density.shape[0] == 3
    node_count = density.shape[1]
    samples = tuple(density.values[index * node_count] for index in range(3))
    assert samples[0] < samples[1] < samples[2]
    assert result.datasets["conduction_band"].axes[0] == "temperature"


@pytest.mark.integration
def test_registered_physics_parameter_study_is_generic_and_axis_aware(
    tmp_path: Path,
) -> None:
    payload = intrinsic_temperature_spec().model_dump(mode="json")
    payload["profiles"] = [
        {
            "kind": "constant",
            "region": "bulk",
            "species": "donor",
            "value": "1e19 cm^-3",
        }
    ]
    payload["physics"]["models"].append("slotboom_bgn")
    payload["study"] = {
        "kind": "parameter",
        "parameter_path": "physics.parameters.bgn_reference_energy",
        "values": ["5 meV", "10 meV", "20 meV"],
    }
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "parameter-study"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.axes["parameter"].unit == "eV"
    assert result.axes["parameter"].values == pytest.approx((0.005, 0.01, 0.02))
    bands = result.datasets["conduction_band"]
    assert bands.axes[0] == "parameter"
    node_count = bands.shape[1]
    samples = tuple(bands.values[index * node_count] for index in range(3))
    assert len(set(samples)) == 3
