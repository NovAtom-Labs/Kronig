from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


def _run(payload: dict, workspace: Path):
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(ExperimentSpec.model_validate(payload), workspace),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    return result


@pytest.mark.integration
def test_constant_temperature_profile_matches_scalar_temperature(tmp_path: Path) -> None:
    scalar = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    scalar["study"] = {"kind": "equilibrium"}
    scalar["observables"] = ["potential", "electron_density", "hole_density"]
    profiled = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    profiled["study"] = {"kind": "equilibrium"}
    profiled["observables"] = [
        "potential",
        "electron_density",
        "hole_density",
        "lattice_temperature",
    ]
    profiled["physics"]["temperature_profiles"] = [
        {"kind": "constant", "region": region["id"], "value": "300 K"}
        for region in profiled["regions"]
    ]

    reference = _run(scalar, tmp_path / "scalar")
    candidate = _run(profiled, tmp_path / "profiled")

    reference_potential = reference.datasets["potential"].values
    candidate_potential = candidate.datasets["potential"].values
    offset = candidate_potential[0] - reference_potential[0]
    assert max(
        abs((candidate - reference_value) - offset)
        for candidate, reference_value in zip(
            candidate_potential, reference_potential, strict=True
        )
    ) < 2e-3
    for name in ("electron_density", "hole_density"):
        scale = max(max(abs(value) for value in reference.datasets[name].values), 1.0)
        difference = max(
            abs(left - right)
            for left, right in zip(
                reference.datasets[name].values,
                candidate.datasets[name].values,
                strict=True,
            )
        )
        assert difference / scale < 2e-3
    assert candidate.datasets["lattice_temperature"].values == pytest.approx(
        (300.0,) * len(candidate.datasets["lattice_temperature"].values)
    )


@pytest.mark.integration
def test_linear_temperature_profile_is_preserved_in_canonical_field(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    payload["study"] = {"kind": "equilibrium"}
    payload["physics"]["temperature_profiles"] = [
        {
            "kind": "linear",
            "region": "p_region",
            "start_value": "280 K",
            "end_value": "300 K",
        },
        {
            "kind": "linear",
            "region": "n_region",
            "start_value": "300 K",
            "end_value": "340 K",
        },
    ]
    payload["observables"] = ["potential", "lattice_temperature"]

    result = _run(payload, tmp_path / "linear")
    values = result.datasets["lattice_temperature"].values

    assert values[0] == pytest.approx(280.0)
    assert values[-1] == pytest.approx(340.0)
    assert all(value > 0 for value in values)
