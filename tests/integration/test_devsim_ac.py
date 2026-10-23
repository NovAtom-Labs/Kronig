import json
import subprocess
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_ac_failure_retains_native_error_without_claiming_valid_results(tmp_path):
    spec = dielectric_ac_spec(
        {"kind": "ac", "contact": "control", "frequency": "1 kHz", "amplitude": "10 mV"}
    )
    adapter = DevsimAdapter.from_defaults()
    job = adapter.compile(spec, tmp_path / "failed-ac")
    program = """
import devsim as d,runpy,sys
native=d.solve
def solve(**options):
    if options.get('type')=='ac':
        raise RuntimeError('synthetic native sparse-factorization error')
    return native(**options)
d.solve=solve
sys.argv=['run_devsim.py','input.json']
assert runpy.run_path('run_devsim.py')['main']()==0
"""
    completed = subprocess.run(
        [str(resolve_devsim_python(ROOT)), "-c", program],
        cwd=job.entrypoint.parent,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads((job.entrypoint.parent / "native_result.json").read_text())
    assert not any(point["valid"] for point in result["frequency_points"])
    failures = [event for event in result["solver_events"] if event["phase"] == "small_signal_ac"]
    assert failures[0]["error"] == "synthetic native sparse-factorization error"


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
def test_ac_at_each_bias_has_bias_frequency_axes_and_reference_values(tmp_path: Path):
    spec = dielectric_ac_spec(
        {
            "kind": "ac",
            "contact": "control",
            "frequency": "1 kHz",
            "amplitude": "10 mV",
            "bias_schedule": {
                "kind": "dc_points",
                "contact": "control",
                "values": ["-0.1 V", "0 V", "0.2 V"],
            },
        }
    )
    result, native = run(spec, tmp_path / "bias-ac")
    assert result.status == "completed", native.stderr_path.read_text()
    assert [point.bias_v for point in result.bias_points] == pytest.approx([-0.1, 0, 0.2])
    dataset = result.datasets["ac_capacitance__control"]
    assert dataset.axes == ("bias", "frequency")
    assert dataset.shape == (3, 1)
    assert dataset.validity == (True, True, True)
    expected = 3.9 * 8.85e-12 / 10e-9
    assert dataset.values == pytest.approx([expected] * 3, rel=0.02)
    from tcad_agent.validation.engine import ValidationEngine

    report = ValidationEngine().validate(result, spec=spec)
    checks = {check.id: check.status for check in report.checks}
    assert checks["small-signal-grid-complete"] == "passed"
    assert checks["requested-study-order"] == "passed"
    invalid = result.model_copy(
        update={
            "datasets": result.datasets
            | {
                "ac_capacitance__control": dataset.model_copy(
                    update={"validity": (True, False, True)}
                )
            }
        }
    )
    failed = ValidationEngine().validate(invalid, spec=spec)
    assert (
        next(check for check in failed.checks if check.id == "small-signal-grid-complete").status
        == "failed"
    )


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
    assert result.axes["frequency"].values == pytest.approx((100.0, 1000.0, 10000.0, 100000.0))
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
    from tcad_agent.experiments.planning import expected_bias_points
    from tcad_agent.validation.engine import ValidationEngine

    assert expected_bias_points(spec) == 1
    report = ValidationEngine().validate(
        result, spec=spec, expected_bias_points=expected_bias_points(spec)
    )
    checks = {check.id: check.status for check in report.checks}
    assert checks["expected-point-count"] == "passed"
    assert checks["small-signal-grid-complete"] == "passed"


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
