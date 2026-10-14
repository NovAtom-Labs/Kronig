from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.studies import EquilibriumStudy
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


def _with_statistics(spec: ExperimentSpec, statistics: str) -> ExperimentSpec:
    models = tuple(statistics if model == "boltzmann" else model for model in spec.physics.models)
    return spec.model_copy(
        update={
            "physics": spec.physics.model_copy(update={"models": models}),
            "observables": tuple(
                sorted(
                    {
                        *(str(item) for item in spec.observables),
                        "charge_density",
                        "electron_quasi_fermi_level",
                        "hole_quasi_fermi_level",
                    }
                )
            ),
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


@pytest.mark.integration
def test_fermi_statistics_match_boltzmann_in_non_degenerate_limit(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    equilibrium = valid_spec.model_copy(update={"study": EquilibriumStudy(kind="equilibrium")})
    boltzmann = _run(_with_statistics(equilibrium, "boltzmann"), tmp_path / "boltzmann")
    fermi = _run(_with_statistics(equilibrium, "fermi"), tmp_path / "fermi")

    for field in ("potential", "electron_density", "hole_density"):
        reference = boltzmann.datasets[field].values
        candidate = fermi.datasets[field].values
        scale = max(max(abs(value) for value in reference), 1.0)
        assert (
            max(abs(left - right) for left, right in zip(reference, candidate, strict=True)) / scale
            < 0.03
        )


@pytest.mark.integration
def test_fermi_degenerate_equilibrium_is_neutral_and_has_zero_terminal_current(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    payload["profiles"][0]["value"] = "5e19 cm^-3"
    payload["profiles"][1]["value"] = "5e19 cm^-3"
    payload["physics"]["models"][0] = "fermi"
    payload["study"] = {"kind": "equilibrium"}
    payload["observables"] = [
        "terminal_current",
        "charge_density",
        "electron_density",
        "hole_density",
        "electron_quasi_fermi_level",
        "hole_quasi_fermi_level",
    ]
    result = _run(ExperimentSpec.model_validate(payload), tmp_path / "degenerate")

    charge = result.datasets["charge_density"].values
    carrier_scale = 1.602176634e-19 * 1e26
    assert abs(charge[0]) / carrier_scale < 2e-3
    assert abs(charge[-1]) / carrier_scale < 2e-3
    currents = result.bias_points[0].terminal_currents_a_per_m2.values()
    assert max(abs(value) for value in currents) < 1e-3


@pytest.mark.integration
def test_fermi_biased_transport_conserves_current(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    result = _run(_with_statistics(valid_spec, "fermi"), tmp_path / "biased")

    for point in result.bias_points:
        currents = tuple(point.terminal_currents_a_per_m2.values())
        scale = max(max(abs(value) for value in currents), 1e-12)
        assert abs(sum(currents)) / scale < 5e-3
    assert max(result.datasets["electron_density"].values) > 0
    assert max(result.datasets["hole_density"].values) > 0
    statistics_source = result.metadata["parameter_sources"]["carrier_statistics"]
    assert "Joyce-Dixon/Sommerfeld" in statistics_source["source"]
    assert "kronig.joyce-dixon.matched" in statistics_source["version"]
