from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]
OBSERVABLES = [
    "electron_current_density",
    "hole_current_density",
    "electron_drift_current_density",
    "electron_diffusion_current_density",
    "hole_drift_current_density",
    "hole_diffusion_current_density",
    "current_decomposition_residual",
]


def _run(payload: dict, workspace: Path):
    payload["observables"] = OBSERVABLES
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(ExperimentSpec.model_validate(payload), workspace),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    return result


@pytest.mark.integration
def test_uniform_equilibrium_current_components_are_negligible(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    payload["profiles"][0]["species"] = "donor"
    payload["profiles"][0]["value"] = "1e16 cm^-3"
    payload["profiles"][1]["value"] = "1e16 cm^-3"
    payload["study"] = {"kind": "equilibrium"}
    result = _run(payload, tmp_path / "uniform")

    for name in OBSERVABLES:
        assert max(abs(value) for value in result.datasets[name].values) < 1e-3


@pytest.mark.integration
def test_decomposition_reconstructs_solved_current_on_refined_mesh(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    for region in payload["regions"]:
        region["mesh_spacing"] = "2 nm"
    payload["study"] = {
        "kind": "dc",
        "contact": "anode",
        "start": "0.1 V",
        "stop": "0.1 V",
        "step": "0.1 V",
    }
    result = _run(payload, tmp_path / "biased")

    residual = result.datasets["current_decomposition_residual"].values
    component_scale = max(
        abs(value)
        for name in (
            "electron_drift_current_density",
            "electron_diffusion_current_density",
            "hole_drift_current_density",
            "hole_diffusion_current_density",
        )
        for value in result.datasets[name].values
    )
    assert max(abs(value) for value in residual) / max(component_scale, 1e-12) < 5e-3
    assert result.datasets["current_decomposition_residual"].metadata[
        "discretization"
    ] == "continuum edge-centered diagnostic"
