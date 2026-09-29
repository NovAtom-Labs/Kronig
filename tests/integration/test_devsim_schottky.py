from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import Contact, ExperimentSpec
from tcad_agent.domain.studies import DCStudy, EquilibriumStudy
from tcad_agent.domain.units import QuantityValue
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


def _with_left_schottky(
    spec: ExperimentSpec, work_function: str = "4.10 eV"
) -> ExperimentSpec:
    contact = Contact.model_validate(
        {
            "id": spec.contacts[0].id,
            "location": spec.contacts[0].location,
            "kind": "metal_work_function",
            "work_function": work_function,
        }
    )
    return spec.model_copy(update={"contacts": (contact, *spec.contacts[1:])})


def _run(spec: ExperimentSpec, workspace: Path):
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, workspace), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    return result


@pytest.mark.integration
def test_schottky_equilibrium_has_negligible_terminal_current(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    requested = _with_left_schottky(valid_spec).model_copy(
        update={"study": EquilibriumStudy(kind="equilibrium")}
    )
    result = _run(requested, tmp_path / "equilibrium")

    currents = result.bias_points[0].terminal_currents_a_per_m2.values()
    assert max(abs(value) for value in currents) < 1e-3
    source = result.metadata["parameter_sources"]["schottky_transport"]
    assert "thermionic" in source["source"].lower()


@pytest.mark.integration
def test_schottky_barrier_increases_with_metal_work_function(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    equilibrium = valid_spec.model_copy(
        update={"study": EquilibriumStudy(kind="equilibrium")}
    )
    low = _run(_with_left_schottky(equilibrium, "4.10 eV"), tmp_path / "low")
    high = _run(_with_left_schottky(equilibrium, "4.50 eV"), tmp_path / "high")

    low_band = low.datasets["potential"].values[0]
    high_band = high.datasets["potential"].values[0]
    assert low_band - high_band == pytest.approx(0.40, rel=2e-3)


@pytest.mark.integration
def test_schottky_bias_has_opposite_current_polarities_and_conserves_current(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    study = DCStudy.model_validate(
        {
            "kind": "dc",
            "contact": valid_spec.contacts[0].id,
            "start": "-0.1 V",
            "stop": "0.1 V",
            "step": "0.1 V",
        }
    )
    result = _run(
        _with_left_schottky(valid_spec).model_copy(update={"study": study}),
        tmp_path / "biased",
    )

    driven = valid_spec.contacts[0].id
    currents = [point.terminal_currents_a_per_m2[driven] for point in result.bias_points]
    assert currents[0] * currents[-1] < 0
    for point in result.bias_points:
        values = tuple(point.terminal_currents_a_per_m2.values())
        scale = max(max(abs(value) for value in values), 1e-12)
        assert abs(sum(values)) < 1e-6 or abs(sum(values)) / scale < 5e-3


@pytest.mark.integration
def test_schottky_thermionic_current_responds_to_temperature(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    study = DCStudy.model_validate(
        {
            "kind": "dc",
            "contact": valid_spec.contacts[0].id,
            "start": "0.1 V",
            "stop": "0.1 V",
            "step": "0.1 V",
        }
    )
    base = _with_left_schottky(valid_spec).model_copy(update={"study": study})
    low = base.model_copy(
        update={
            "physics": base.physics.model_copy(
                update={"temperature": QuantityValue.model_validate("280 K")}
            )
        }
    )
    high = base.model_copy(
        update={
            "physics": base.physics.model_copy(
                update={"temperature": QuantityValue.model_validate("340 K")}
            )
        }
    )

    low_result = _run(low, tmp_path / "low-temperature")
    high_result = _run(high, tmp_path / "high-temperature")
    terminal = valid_spec.contacts[0].id
    low_current = abs(low_result.bias_points[0].terminal_currents_a_per_m2[terminal])
    high_current = abs(high_result.bias_points[0].terminal_currents_a_per_m2[terminal])

    assert high_current > low_current
