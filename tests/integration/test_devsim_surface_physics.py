from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


def _surface_stack(*, trap_type: str = "acceptor", bias: float = 0.0) -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "surface physics benchmark",
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
                    "id": "silicon",
                    "material": "silicon",
                    "x0": "10 nm",
                    "x1": "1 um",
                    "mesh_spacing": "10 nm",
                },
            ],
            "interfaces": [
                {
                    "id": "oxide_silicon",
                    "left_region": "oxide",
                    "right_region": "silicon",
                    "surface_electron_velocity": "1e4 cm/s",
                    "surface_hole_velocity": "1e4 cm/s",
                    "trap_density": "5e11 cm^-2",
                    "trap_energy": "0.15 eV",
                    "trap_type": trap_type,
                }
            ],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "silicon",
                    "species": "acceptor",
                    "value": "1e16 cm^-3",
                }
            ],
            "contacts": [
                {
                    "id": "gate",
                    "location": "x_min",
                    "kind": "metal_work_function",
                    "work_function": "4.1 eV",
                },
                {"id": "back", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": ["boltzmann", "constant_mobility", "srh"],
                "temperature": "300 K",
            },
            "study": {
                "kind": "dc",
                "contact": "gate",
                "start": f"{bias} V",
                "stop": f"{bias} V",
                "step": "0.1 V",
            },
            "observables": [
                "terminal_current",
                "potential",
                "surface_recombination_rate",
                "interface_trap_occupancy",
                "interface_charge_density",
            ],
        }
    )


def _run(spec: ExperimentSpec, workspace: Path):
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, workspace), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    return result


def _biased_internal_surface() -> ExperimentSpec:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    payload["interfaces"] = [
        {
            "id": "p_n_surface",
            "left_region": "p_region",
            "right_region": "n_region",
            "surface_electron_velocity": "1e4 cm/s",
            "surface_hole_velocity": "1e4 cm/s",
        }
    ]
    payload["study"] = {
        "kind": "dc",
        "contact": "anode",
        "start": "0.5 V",
        "stop": "0.5 V",
        "step": "0.1 V",
    }
    payload["observables"] = [
        "terminal_current",
        "surface_recombination_rate",
    ]
    return ExperimentSpec.model_validate(payload)


@pytest.mark.integration
def test_surface_srh_is_near_zero_at_equilibrium_and_exposes_trap_state(
    tmp_path: Path,
) -> None:
    result = _run(_surface_stack(), tmp_path / "equilibrium")

    assert abs(result.datasets["surface_recombination_rate"].values[0]) < 1e5
    occupancy = result.datasets["interface_trap_occupancy"].values[0]
    assert 0.0 <= occupancy <= 1.0
    assert result.datasets["interface_charge_density"].values[0] < 0


@pytest.mark.integration
def test_surface_srh_responds_to_bias_and_conserves_terminal_current(
    tmp_path: Path,
) -> None:
    result = _run(_biased_internal_surface(), tmp_path / "biased")

    rate = result.datasets["surface_recombination_rate"].values[0]
    assert abs(rate) > 1e5
    currents = tuple(result.bias_points[0].terminal_currents_a_per_m2.values())
    assert abs(sum(currents)) < max(max(abs(value) for value in currents) * 5e-3, 1e-6)


@pytest.mark.integration
def test_interface_trap_charge_sign_follows_trap_type(tmp_path: Path) -> None:
    acceptor = _run(_surface_stack(trap_type="acceptor"), tmp_path / "acceptor")
    donor = _run(_surface_stack(trap_type="donor"), tmp_path / "donor")

    assert acceptor.datasets["interface_charge_density"].values[0] < 0
    assert donor.datasets["interface_charge_density"].values[0] > 0
