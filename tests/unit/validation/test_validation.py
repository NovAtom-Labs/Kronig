import math
from pathlib import Path

import pytest
import yaml

from tcad_agent.domain.models import ExperimentSpec, Observable
from tcad_agent.recovery.models import FailureKind
from tcad_agent.results.models import BiasPoint, CanonicalResult, FieldSeries
from tcad_agent.validation.engine import ValidationEngine


def test_canonical_temperature_points_are_validated_without_legacy_bias_records(valid_spec):
    from tcad_agent.results.models import OperatingPoint

    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("left", "right"),
        operating_points=tuple(
            OperatingPoint(
                index=i,
                state="converged",
                coordinates={"temperature": t},
                terminal_currents_a_per_m2={"left": 1e-8, "right": -1e-8},
            )
            for i, t in enumerate((280, 300, 320))
        ),
    )
    spec = valid_spec.model_copy(update={"observables": (Observable.TERMINAL_CURRENT_DENSITY,)})
    report = ValidationEngine().validate(result, expected_bias_points=3, spec=spec)
    for check in (
        "bias-points-present",
        "expected-point-count",
        "all-points-converged",
        "terminal-current-conservation",
        "requested-observables-present",
    ):
        assert report.checks_by_id[check].status == "passed"


def canonical_result(
    *,
    anode_current: float = 1.0,
    cathode_current: float = -1.0,
    converged: bool = True,
    status: str = "completed",
    bias_points: tuple[BiasPoint, ...] | None = None,
) -> CanonicalResult:
    points = bias_points
    if points is None:
        points = (
            BiasPoint(
                bias_v=0.1,
                converged=converged,
                terminal_currents_a_per_m2={
                    "anode": anode_current,
                    "cathode": cathode_current,
                },
            ),
        )
    return CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status=status,
        terminals=("anode", "cathode"),
        bias_points=points,
    )


def test_non_voltage_failed_point_is_classified_as_nonconvergence():
    from tcad_agent.results.models import OperatingPoint

    result = CanonicalResult(
        backend="devsim",
        status="completed",
        simulator_version="2.9.1",
        terminals=("left", "right"),
        operating_points=(
            OperatingPoint(index=0, state="failed", coordinates={"temperature": 300}),
        ),
    )
    assert FailureKind.NON_CONVERGENCE in {
        failure.kind for failure in ValidationEngine().classify_failures(result)
    }


def test_converged_but_nonconserving_result_fails_physical_validation() -> None:
    result = canonical_result(anode_current=1.0, cathode_current=-0.7, converged=True)
    report = ValidationEngine(current_rtol=1e-6).validate(result)
    assert report.overall == "failed"
    assert report.checks_by_id["terminal-current-conservation"].status == "failed"


def test_failed_process_cannot_be_validated_as_success() -> None:
    result = canonical_result(status="execution_failed", bias_points=())
    report = ValidationEngine().validate(result)
    assert report.overall == "failed"
    assert report.checks_by_id["execution-status"].status == "failed"


def test_valid_conserving_result_passes() -> None:
    report = ValidationEngine().validate(canonical_result())
    assert report.overall == "passed"


def test_classifies_execution_failure_without_secondary_noise() -> None:
    engine = ValidationEngine()
    failures = engine.classify_failures(canonical_result(status="execution_failed", bias_points=()))
    assert [failure.kind for failure in failures] == [FailureKind.EXECUTION]


def test_classifies_nonconvergence_nonfinite_and_conservation_separately() -> None:
    engine = ValidationEngine(current_rtol=1e-6)
    nonconverged = engine.classify_failures(canonical_result(converged=False))
    nonfinite = engine.classify_failures(canonical_result(anode_current=math.nan))
    nonconserving = engine.classify_failures(
        canonical_result(anode_current=1.0, cathode_current=-0.7)
    )
    assert [failure.kind for failure in nonconverged] == [FailureKind.NON_CONVERGENCE]
    assert [failure.kind for failure in nonfinite] == [FailureKind.NONFINITE_RESULT]
    assert [failure.kind for failure in nonconserving] == [FailureKind.CONSERVATION]


def test_validation_status_supports_not_applicable() -> None:
    from tcad_agent.validation.models import ValidationCheck

    check = ValidationCheck(
        id="mesh-refinement",
        level="numerical",
        status="not_applicable",
        message="No refined result was requested.",
    )
    assert check.status == "not_applicable"


def equilibrium_spec() -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        yaml.safe_load(Path("examples/al-pn-al-equilibrium-devsim.yaml").read_text())
    )


def equilibrium_result(
    *,
    potential_range_v: float = 0.8345,
    terminal_current_a_per_m2: float = 1.0e-19,
) -> CanonicalResult:
    return CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("anode", "cathode"),
        bias_points=(
            BiasPoint(
                bias_v=0.0,
                converged=True,
                terminal_currents_a_per_m2={
                    "anode": terminal_current_a_per_m2,
                    "cathode": -terminal_current_a_per_m2,
                },
            ),
        ),
        fields={
            "potential": FieldSeries(
                positions_m=(0.0, 1.0e-6, 2.0e-6),
                values=(0.0, potential_range_v / 2.0, potential_range_v),
                unit="V",
            ),
            "electric_field": FieldSeries(
                positions_m=(0.5e-6, 1.5e-6),
                values=(1.0e5, 1.0e5),
                unit="V/m",
            ),
            "electron_density": FieldSeries(
                positions_m=(0.0, 1.0e-6, 2.0e-6),
                values=(1.0e16, 1.0e19, 1.0e23),
                unit="m^-3",
            ),
            "hole_density": FieldSeries(
                positions_m=(0.0, 1.0e-6, 2.0e-6),
                values=(1.0e23, 1.0e19, 1.0e16),
                unit="m^-3",
            ),
        },
    )


def test_equilibrium_checks_pass_for_physical_pn_result() -> None:
    report = ValidationEngine().validate(
        equilibrium_result(),
        spec=equilibrium_spec(),
    )
    current = report.checks_by_id["equilibrium-terminal-current"]
    built_in = report.checks_by_id["built-in-potential-reference"]
    assert current.status == "passed"
    assert current.evidence_origin == "derived"
    assert built_in.status == "passed"
    assert built_in.measured_value == pytest.approx(0.8345)
    assert "0.833" in str(built_in.limit)


def test_equal_and_opposite_nonzero_equilibrium_currents_fail() -> None:
    report = ValidationEngine().validate(
        equilibrium_result(terminal_current_a_per_m2=1.868e3),
        spec=equilibrium_spec(),
    )
    assert report.checks_by_id["terminal-current-conservation"].status == "passed"
    assert report.checks_by_id["equilibrium-terminal-current"].status == "failed"


def test_converged_equilibrium_with_wrong_built_in_potential_fails() -> None:
    result = equilibrium_result(potential_range_v=0.00501)
    engine = ValidationEngine()
    report = engine.validate(result, spec=equilibrium_spec())
    failures = engine.classify_failures(result, spec=equilibrium_spec())
    assert report.checks_by_id["built-in-potential-reference"].status == "failed"
    assert FailureKind.PHYSICAL_SANITY in {failure.kind for failure in failures}


def test_validation_checks_record_evidence_origin() -> None:
    report = ValidationEngine().validate(canonical_result())
    assert all(check.evidence_origin for check in report.checks)
    assert report.checks_by_id["simulator-version-recorded"].evidence_origin == (
        "simulator_observed"
    )


def test_missing_requested_observable_fails_validation() -> None:
    result = equilibrium_result()
    incomplete = result.model_copy(
        update={
            "fields": {
                name: field for name, field in result.fields.items() if name != "electron_density"
            }
        }
    )
    engine = ValidationEngine()
    report = engine.validate(incomplete, spec=equilibrium_spec())
    failures = engine.classify_failures(incomplete, spec=equilibrium_spec())
    check = report.checks_by_id["requested-observables-present"]
    assert check.status == "failed"
    assert check.measured_value == "missing: electron_density"
    assert FailureKind.MALFORMED_OUTPUT in {failure.kind for failure in failures}


def test_terminal_current_density_is_satisfied_by_canonical_terminal_currents() -> None:
    spec = equilibrium_spec().model_copy(
        update={"observables": (Observable.TERMINAL_CURRENT_DENSITY,)}
    )

    report = ValidationEngine().validate(equilibrium_result(), spec=spec)

    assert report.checks_by_id["requested-observables-present"].status == "passed"


def test_absolute_terminal_current_requires_area_scaled_canonical_datasets() -> None:
    spec = equilibrium_spec().model_copy(
        update={"observables": (Observable.ABSOLUTE_TERMINAL_CURRENT,)}
    )

    report = ValidationEngine().validate(equilibrium_result(), spec=spec)

    check = report.checks_by_id["requested-observables-present"]
    assert check.status == "failed"
    assert check.measured_value == "missing: absolute_terminal_current"
