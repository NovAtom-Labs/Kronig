import pytest

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import BiasPoint, CanonicalResult
from tcad_agent.validation.engine import ValidationEngine
from tcad_agent.validation.models import ValidationReport


def result_with_currents(*maps: dict[str, float]) -> CanonicalResult:
    return CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("left", "right"),
        bias_points=tuple(
            BiasPoint(bias_v=float(index), converged=True, terminal_currents_a_per_m2=currents)
            for index, currents in enumerate(maps)
        ),
    )


def test_absent_current_and_carrier_evidence_is_not_applicable() -> None:
    report = ValidationEngine().validate(result_with_currents({}))
    for identifier in ("terminal-current-conservation", "nonnegative-carrier-density"):
        check = report.checks_by_id[identifier]
        assert check.status == "not_applicable"
        assert check.applicability_reason
        assert check.measured_value is None


def test_partial_terminal_evidence_cannot_pass_conservation() -> None:
    check = (
        ValidationEngine()
        .validate(result_with_currents({"left": 0.0}))
        .checks_by_id["terminal-current-conservation"]
    )
    assert check.status == "failed"


def test_conservation_reports_units_scale_and_unchanged_tolerances() -> None:
    check = (
        ValidationEngine()
        .validate(result_with_currents({"left": 2.0e-6, "right": 0.0}))
        .checks_by_id["terminal-current-conservation"]
    )
    assert check.status == "failed"
    assert check.unit == "A/m^2"
    assert check.absolute_tolerance == 1e-6
    assert check.relative_tolerance == 1e-4
    assert check.scale == 2e-6
    assert check.limit == pytest.approx(1.0002e-6)


def test_small_residual_failure_is_not_hidden_by_large_current_scale() -> None:
    check = (
        ValidationEngine()
        .validate(
            result_with_currents(
                {"left": 100.0, "right": -99.9},
                {"left": 1e6, "right": -1e6 + 1.0},
            )
        )
        .checks_by_id["terminal-current-conservation"]
    )
    assert check.status == "failed"
    assert check.measured_value == pytest.approx(0.1)
    assert check.scale == 100.0


def test_masked_negative_carriers_are_not_used_as_physical_evidence() -> None:
    result = result_with_currents({}).model_copy(
        update={
            "axes": {
                "x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=(0.0, 1.0))
            },
            "datasets": {
                "electron_density": Dataset(
                    id="electron_density",
                    label="Electrons",
                    unit="m^-3",
                    axes=("x",),
                    shape=(2,),
                    values=(-1.0, -2.0),
                    validity=(False, False),
                )
            },
        }
    )
    check = ValidationEngine().validate(result).checks_by_id["nonnegative-carrier-density"]
    assert check.status == "not_applicable"


def test_valid_canonical_negative_carriers_fail_without_legacy_fields() -> None:
    result = result_with_currents({}).model_copy(
        update={
            "axes": {
                "x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=(0.0, 1.0))
            },
            "datasets": {
                "electron_density": Dataset(
                    id="electron_density",
                    label="Electrons",
                    unit="m^-3",
                    axes=("x",),
                    shape=(2,),
                    values=(-1.0, 2.0),
                )
            },
        }
    )
    check = ValidationEngine().validate(result).checks_by_id["nonnegative-carrier-density"]
    assert check.status == "failed"


def test_recombination_checks_require_valid_rate_evidence() -> None:
    datasets = {
        name: Dataset(
            id=name,
            label=name,
            unit="m^-3/s",
            axes=("x",),
            shape=(2,),
            values=(0.0, 0.0),
            validity=(False, False),
        )
        for name in (
            "total_recombination_rate",
            "srh_recombination_rate",
            "auger_recombination_rate",
            "electron_generation_rate",
            "hole_generation_rate",
        )
    }
    result = result_with_currents({}).model_copy(
        update={
            "axes": {
                "x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=(0.0, 1.0))
            },
            "datasets": datasets,
        }
    )
    report = ValidationEngine().validate(result)
    assert report.checks_by_id["recombination-component-balance"].status == "not_applicable"
    assert report.checks_by_id["generation-recombination-sign"].status == "not_applicable"


def test_nonfinite_currents_produce_failed_evidence_not_schema_crash() -> None:
    report = ValidationEngine().validate(result_with_currents({"left": float("inf"), "right": 0.0}))
    assert report.checks_by_id["finite-values"].status == "failed"
    assert report.checks_by_id["terminal-current-conservation"].status == "failed"


def test_acceptance_limits_preserve_customized_engine_configuration() -> None:
    limits = ValidationEngine(current_atol=5e-9).acceptance_limits()
    assert limits["current_atol"] == 5e-9
    assert limits["current_rtol"] == 1e-4
    assert limits["equilibrium_current_atol"] == 1e-6


def test_reports_record_actual_acceptance_and_legacy_reports_do_not_infer_it() -> None:
    engine = ValidationEngine(current_atol=5e-9, current_rtol=2e-5)
    report = engine.validate(result_with_currents({"left": 0.0, "right": 0.0}))
    assert report.acceptance_limits == engine.acceptance_limits()
    legacy = ValidationReport.model_validate({"overall": "passed", "checks": []})
    assert legacy.acceptance_limits is None


def dielectric_spec() -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "dielectric",
            "dimension": 1,
            "regions": [
                {
                    "id": "medium",
                    "material": "silicon_dioxide",
                    "x0": "0 m",
                    "x1": "1 um",
                    "mesh_spacing": "10 nm",
                }
            ],
            "profiles": [],
            "contacts": [
                {"id": "left", "kind": "ideal_gate", "location": "x_min"},
                {"id": "right", "kind": "ideal_gate", "location": "x_max"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {"kind": "equilibrium"},
            "observables": ["potential"],
        }
    )


def test_equilibrium_without_currents_has_no_current_check_applicability() -> None:
    report = ValidationEngine().validate(result_with_currents({}), spec=dielectric_spec())
    assert report.checks_by_id["equilibrium-terminal-current"].status == "not_applicable"


def test_partial_terminal_charge_evidence_cannot_pass() -> None:
    from tcad_agent.results.models import OperatingPoint

    result = result_with_currents({}).model_copy(
        update={
            "operating_points": (
                OperatingPoint(index=0, state="converged", terminal_charges_c_per_m2={"left": 0.0}),
            )
        }
    )
    report = ValidationEngine().validate(result, spec=dielectric_spec())
    assert report.checks_by_id["contact-charge-balance"].status == "failed"


@pytest.mark.parametrize(
    "names,units,identifier",
    [
        (("conduction_band", "valence_band"), ("eV", "eV"), "band-ordering"),
        (("potential", "electric_field"), ("V", "V/m"), "electric-field-potential-gradient"),
        (
            ("electrostatic_flux", "charge_density"),
            ("C/m^2", "C/m^3"),
            "poisson-residual-consistency",
        ),
    ],
)
def test_masked_physical_datasets_are_not_applicable(names, units, identifier) -> None:
    result = result_with_currents({}).model_copy(
        update={
            "axes": {
                "x": ScientificAxis(
                    id="x", kind="position", label="x", unit="m", values=(0.0, 1.0, 2.0)
                )
            },
            "datasets": {
                name: Dataset(
                    id=name,
                    label=name,
                    unit=unit,
                    axes=("x",),
                    shape=(3,),
                    values=(0.0, 0.0, 0.0),
                    validity=(False, False, False),
                )
                for name, unit in zip(names, units, strict=True)
            },
        }
    )
    check = ValidationEngine().validate(result).checks_by_id[identifier]
    assert check.status == "not_applicable"
    assert check.measured_value is None
