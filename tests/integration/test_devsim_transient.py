from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_voltage_step_produces_time_indexed_charge_current_and_fields(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "dielectric transient step",
            "dimension": 1,
            "regions": [
                {
                    "id": "dielectric",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "10 nm",
                    "mesh_spacing": "0.5 nm",
                }
            ],
            "profiles": [],
            "contacts": [
                {"id": "control", "location": "x_min", "kind": "ideal_gate"},
                {"id": "reference", "location": "x_max", "kind": "ideal_gate"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {
                "kind": "transient",
                "contact": "control",
                "waveform": "step",
                "initial_voltage": "0 V",
                "final_voltage": "0.1 V",
                "start": "0 s",
                "stop": "5 ns",
                "initial_step": "1 ns",
                "maximum_step": "1 ns",
            },
            "observables": ["potential", "electric_field", "terminal_charge"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "transient"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.axes["time"].values == pytest.approx(
        (1e-9, 2e-9, 3e-9, 4e-9, 5e-9)
    )
    assert result.datasets["potential"].axes[0] == "time"
    assert result.datasets["terminal_charge__control"].axes == ("time",)
    assert result.datasets["terminal_current__control"].values[0] != 0.0
    final_charge = result.datasets["terminal_charge__control"].values[-1]
    expected = (3.9 * 8.85e-12 / 10e-9) * 0.1
    assert abs(final_charge) == pytest.approx(expected, rel=0.02)


@pytest.mark.integration
def test_transient_step_grows_after_success_without_exceeding_maximum(
    tmp_path: Path,
) -> None:
    payload = {
        "schema_version": "1.0",
        "name": "adaptive transient schedule",
        "dimension": 1,
        "regions": [
            {
                "id": "dielectric",
                "material": "silicon_dioxide",
                "x0": "0 nm",
                "x1": "10 nm",
                "mesh_spacing": "0.5 nm",
            }
        ],
        "profiles": [],
        "contacts": [
            {"id": "control", "location": "x_min", "kind": "ideal_gate"},
            {"id": "reference", "location": "x_max", "kind": "ideal_gate"},
        ],
        "physics": {"equations": ["poisson"]},
        "study": {
            "kind": "transient",
            "contact": "control",
            "waveform": "ramp",
            "initial_voltage": "0 V",
            "final_voltage": "0.1 V",
            "start": "0 ns",
            "stop": "5 ns",
            "initial_step": "0.5 ns",
            "maximum_step": "2 ns",
        },
        "observables": ["potential", "terminal_charge"],
    }
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "transient-growth"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    times = result.axes["time"].values
    steps = tuple(right - left for left, right in zip((0.0, *times[:-1]), times, strict=True))
    assert steps[1] > steps[0]
    assert max(steps) <= 2e-9 * (1 + 1e-12)
    assert times[-1] == pytest.approx(5e-9)


@pytest.mark.integration
def test_voltage_pulse_returns_to_initial_charge_state(tmp_path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "name": "dielectric transient pulse",
        "dimension": 1,
        "regions": [
            {
                "id": "dielectric",
                "material": "silicon_dioxide",
                "x0": "0 nm",
                "x1": "10 nm",
                "mesh_spacing": "0.5 nm",
            }
        ],
        "profiles": [],
        "contacts": [
            {"id": "control", "location": "x_min", "kind": "ideal_gate"},
            {"id": "reference", "location": "x_max", "kind": "ideal_gate"},
        ],
        "physics": {"equations": ["poisson"]},
        "study": {
            "kind": "transient",
            "contact": "control",
            "waveform": "pulse",
            "initial_voltage": "0 V",
            "final_voltage": "0.1 V",
            "start": "0 ns",
            "stop": "8 ns",
            "initial_step": "0.25 ns",
            "minimum_step": "0.01 ns",
            "maximum_step": "0.5 ns",
            "pulse_delay": "1 ns",
            "rise_time": "1 ns",
            "pulse_width": "3 ns",
            "fall_time": "1 ns",
        },
        "observables": ["potential", "terminal_charge"],
    }
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "transient-pulse"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    charge = result.datasets["terminal_charge__control"]
    assert max(abs(value) for value in charge.values) > 1e-6
    assert abs(charge.values[-1]) < max(abs(value) for value in charge.values) * 1e-6
    assert any(
        event.get("phase") == "transient_step"
        for event in result.metadata["solver_events"]
    )
