from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult, OperatingPoint
from tcad_agent.validation.engine import ValidationEngine


def test_axis_aware_result_records_dataset_and_operating_point_checks() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("left", "right"),
        axes={
            "bias": ScientificAxis(
                id="bias", kind="bias", label="Bias", unit="V", values=(0.0, 1.0)
            )
        },
        datasets={
            "terminal_current__left": Dataset(
                id="terminal_current__left",
                label="Left current",
                unit="A/m^2",
                axes=("bias",),
                shape=(2,),
                centering="operating_point",
                values=(0.0, 1.0),
            )
        },
        operating_points=(
            OperatingPoint(
                index=0,
                state="converged",
                coordinates={"bias": 0.0},
                terminal_currents_a_per_m2={"left": 0.0, "right": 0.0},
            ),
            OperatingPoint(
                index=1,
                state="converged",
                coordinates={"bias": 1.0},
                terminal_currents_a_per_m2={"left": 1.0, "right": -1.0},
            ),
        ),
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["canonical-datasets-structural"].status == "passed"
    assert report.checks_by_id["operating-points-converged"].status == "passed"


def test_failed_operating_point_is_not_hidden_by_completed_process_status() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("left",),
        bias_points=(),
        operating_points=(
            OperatingPoint(
                index=0,
                state="failed",
                coordinates={"bias": 2.0},
                message="nonlinear solve did not converge",
            ),
        ),
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["operating-points-converged"].status == "failed"
    assert report.overall == "failed"
