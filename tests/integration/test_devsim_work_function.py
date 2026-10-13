import math
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


def _oxide_slab(kind: str, *, material: str = "silicon_dioxide") -> ExperimentSpec:
    left_contact: dict[str, object] = {
        "id": "left",
        "location": "x_min",
        "kind": kind,
    }
    if kind == "metal_work_function":
        left_contact["work_function"] = "4.10 eV"
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "work function boundary",
            "dimension": 1,
            "regions": [
                {
                    "id": "layer",
                    "material": material,
                    "x0": "0 nm",
                    "x1": "100 nm",
                    "mesh_spacing": "2 nm",
                }
            ],
            "profiles": [],
            "contacts": [
                left_contact,
                {
                    "id": "right",
                    "location": "x_max",
                    "kind": "ohmic" if material == "silicon" else "ideal_gate",
                },
            ],
            "physics": {
                "equations": (
                    ["poisson", "electron_continuity", "hole_continuity"]
                    if material == "silicon"
                    else ["poisson"]
                ),
                "models": (
                    ["boltzmann", "constant_mobility", "srh"]
                    if material == "silicon"
                    else []
                ),
            },
            "study": {"kind": "equilibrium"},
            "observables": ["potential", "electric_field", "terminal_charge"],
        }
    )


@pytest.mark.integration
def test_ideal_gate_work_function_is_not_silently_ignored(tmp_path: Path):
    spec = _oxide_slab("metal_work_function")
    spec = spec.model_copy(update={"contacts": (
        spec.contacts[0].model_copy(update={"kind": "ideal_gate"}), spec.contacts[1],
    )})
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "ideal-work-function"), RunBudget(seconds=120))
    result = adapter.normalize(native)
    assert result.status == "completed"
    potential = result.datasets["potential"].values
    thermal = 8.617333262145e-5 * 300
    expected = 4.05 + 1.124 / 2 + .5 * thermal * math.log(2.8e19 / 1.04e19) - 4.1
    assert potential[0] - potential[-1] == pytest.approx(expected, rel=2e-3)


@pytest.mark.integration
def test_metal_gate_work_function_creates_reviewed_flat_band_offset(
    tmp_path: Path,
) -> None:
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(_oxide_slab("metal_work_function"), tmp_path / "metal-gate"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    potential = result.datasets["potential"].values
    thermal_voltage = 8.617333262145e-5 * 300.0
    intrinsic_work_function = (
        4.05 + 1.124 / 2 + 0.5 * thermal_voltage * math.log(2.8e19 / 1.04e19)
    )
    expected_offset = intrinsic_work_function - 4.10
    assert potential[0] - potential[-1] == pytest.approx(expected_offset, rel=2e-3)


def test_direct_semiconductor_work_function_contact_compiles_as_schottky(
    tmp_path: Path,
) -> None:
    spec = _oxide_slab("metal_work_function", material="silicon")

    job = DevsimAdapter.from_defaults().compile(spec, tmp_path / "schottky")

    payload = job.input_files[0].read_text()
    assert '"kind": "metal_work_function"' in payload
    assert '"work_function_ev": 4.1' in payload
