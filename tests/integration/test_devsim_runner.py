from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec, Observable
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]
EXAMPLES = ROOT / "examples"
DEVSIM_PYTHON = resolve_devsim_python(ROOT)


@pytest.mark.integration
@pytest.mark.parametrize(
    "fixture_name",
    ["pn-junction.yaml", "pin-diode.yaml", "multiregion-equilibrium.yaml"],
)
def test_two_structures_run_through_one_backend_path(fixture_name: str, tmp_path) -> None:
    payload = yaml.safe_load((EXAMPLES / fixture_name).read_text())
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    job = adapter.compile(spec, tmp_path / fixture_name.removesuffix(".yaml"))
    native = LocalRunner(devsim_python=DEVSIM_PYTHON).run(job, RunBudget(seconds=120))
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    assert result.bias_points
    assert all(point.converged for point in result.bias_points)
    assert set(result.terminals) == {"anode", "cathode"}


@pytest.mark.integration
def test_requested_electric_field_is_normalized_to_si(tmp_path) -> None:
    payload = yaml.safe_load((EXAMPLES / "pn-junction.yaml").read_text())
    spec = ExperimentSpec.model_validate(payload)
    requested = spec.model_copy(
        update={"observables": (*spec.observables, Observable.ELECTRIC_FIELD)}
    )
    adapter = DevsimAdapter.from_defaults()
    job = adapter.compile(requested, tmp_path / "electric-field")

    native = LocalRunner(devsim_python=DEVSIM_PYTHON).run(job, RunBudget(seconds=120))
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    field = result.fields["electric_field"]
    assert field.unit == "V/m"
    assert len(field.positions_m) == len(field.values)
    assert field.values


@pytest.mark.integration
def test_relative_workspace_executes_from_runner_working_directory(
    tmp_path, monkeypatch
) -> None:
    payload = yaml.safe_load((EXAMPLES / "pn-junction.yaml").read_text())
    spec = ExperimentSpec.model_validate(payload)
    monkeypatch.chdir(tmp_path)
    adapter = DevsimAdapter.from_defaults()

    job = adapter.compile(spec, Path("runs") / "relative-workspace")
    native = LocalRunner(devsim_python=DEVSIM_PYTHON).run(job, RunBudget(seconds=120))

    assert job.entrypoint.is_absolute()
    assert native.status == "completed", native.stderr_path.read_text()


@pytest.mark.integration
def test_reviewed_transport_observables_normalize_with_centering(tmp_path) -> None:
    payload = yaml.safe_load((EXAMPLES / "pn-junction.yaml").read_text())
    spec = ExperimentSpec.model_validate(payload)
    requested = spec.model_copy(
        update={
            "observables": (
                *spec.observables,
                Observable.ELECTRIC_FIELD,
                Observable.CHARGE_DENSITY,
                Observable.ELECTRON_CURRENT_DENSITY,
                Observable.HOLE_CURRENT_DENSITY,
                Observable.ELECTRON_MOBILITY,
                Observable.HOLE_MOBILITY,
                Observable.RECOMBINATION_RATE,
            )
        }
    )
    adapter = DevsimAdapter.from_defaults()
    job = adapter.compile(requested, tmp_path / "transport-observables")

    native = LocalRunner(devsim_python=DEVSIM_PYTHON).run(job, RunBudget(seconds=120))
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    for name in (
        "charge_density",
        "electron_current_density",
        "hole_current_density",
        "electron_mobility",
        "hole_mobility",
        "recombination_rate",
    ):
        assert result.datasets[name].values
    assert result.datasets["electric_field"].centering == "edge"
    assert result.datasets["electron_density"].centering == "node"
