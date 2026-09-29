from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


def dielectric_ac_spec(study: dict[str, object]) -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "dielectric small signal response",
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
            "study": study,
            "observables": ["potential", "terminal_charge"],
        }
    )


def run(spec: ExperimentSpec, path: Path):
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, path), RunBudget(seconds=120)
    )
    return adapter.normalize(native), native


@pytest.mark.integration
def test_single_frequency_ac_matches_parallel_plate_capacitance(tmp_path: Path) -> None:
    spec = dielectric_ac_spec(
        {
            "kind": "ac",
            "contact": "control",
            "frequency": "1 kHz",
            "amplitude": "10 mV",
        }
    )
    result, native = run(spec, tmp_path / "single-ac")

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.axes["frequency"].values == pytest.approx((1000.0,))
    capacitance = result.datasets["ac_capacitance__control"].values[0]
    expected = 3.9 * 8.85e-12 / 10e-9
    assert capacitance == pytest.approx(expected, rel=0.02)
    admittance = result.datasets["complex_admittance__control"]
    current_response = result.datasets["complex_current_response__control"]
    assert admittance.imaginary_values is not None
    assert current_response.imaginary_values is not None
    assert current_response.imaginary_values[0] == pytest.approx(
        admittance.imaginary_values[0] * 0.01,
        rel=1e-10,
    )
    assert admittance.imaginary_values[0] == pytest.approx(
        2 * 3.141592653589793 * 1000.0 * expected,
        rel=0.02,
    )


@pytest.mark.integration
def test_frequency_sweep_preserves_complex_response_on_frequency_axis(
    tmp_path: Path,
) -> None:
    spec = dielectric_ac_spec(
        {
            "kind": "frequency",
            "contact": "control",
            "start": "100 Hz",
            "stop": "100 kHz",
            "points": 4,
            "spacing": "log",
            "amplitude": "5 mV",
        }
    )
    result, native = run(spec, tmp_path / "frequency-ac")

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.axes["frequency"].values == pytest.approx(
        (100.0, 1000.0, 10000.0, 100000.0)
    )
    dataset = result.datasets["complex_admittance__control"]
    assert dataset.axes == ("frequency",)
    assert dataset.imaginary_values is not None
    ratios = tuple(
        value / frequency
        for value, frequency in zip(
            dataset.imaginary_values,
            result.axes["frequency"].values,
            strict=True,
        )
    )
    assert max(ratios) == pytest.approx(min(ratios), rel=1e-5)


@pytest.mark.integration
def test_low_frequency_ac_matches_charge_derived_capacitance(tmp_path: Path) -> None:
    dc, dc_native = run(
        dielectric_ac_spec(
            {
                "kind": "dc_points",
                "contact": "control",
                "values": ["-20 mV", "-10 mV", "0 V", "10 mV", "20 mV"],
            }
        ),
        tmp_path / "quasistatic",
    )
    ac, ac_native = run(
        dielectric_ac_spec(
            {
                "kind": "ac",
                "contact": "control",
                "frequency": "100 Hz",
                "amplitude": "1 mV",
            }
        ),
        tmp_path / "small-signal",
    )

    assert dc.status == "completed", dc_native.stderr_path.read_text()
    assert ac.status == "completed", ac_native.stderr_path.read_text()
    charge_derived = dc.datasets["capacitance__control"].values[2]
    small_signal = ac.datasets["ac_capacitance__control"].values[0]
    assert small_signal == pytest.approx(charge_derived, rel=0.02)
