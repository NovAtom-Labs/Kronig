from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import BiasPoint, CanonicalResult
from tcad_agent.validation.engine import ValidationEngine


def test_electric_field_must_equal_negative_potential_gradient() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("left", "right"),
        bias_points=(
            BiasPoint(
                bias_v=0.0,
                converged=True,
                terminal_currents_a_per_m2={"left": 0.0, "right": 0.0},
            ),
        ),
        axes={
            "x_node": ScientificAxis(
                id="x_node", kind="position", label="Position", unit="m", values=(0.0, 1.0, 2.0)
            ),
            "x_edge": ScientificAxis(
                id="x_edge", kind="position", label="Position", unit="m", values=(0.5, 1.5)
            ),
        },
        datasets={
            "potential": Dataset(
                id="potential",
                label="Potential",
                unit="V",
                axes=("x_node",),
                shape=(3,),
                values=(0.0, 1.0, 3.0),
            ),
            "electric_field": Dataset(
                id="electric_field",
                label="Electric field",
                unit="V/m",
                axes=("x_edge",),
                shape=(2,),
                centering="edge",
                values=(-1.0, -2.0),
            ),
        },
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["electric-field-potential-gradient"].status == "passed"


def test_inconsistent_electric_field_fails_physics_validation() -> None:
    consistent = test_result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("left", "right"),
        bias_points=(
            BiasPoint(
                bias_v=0.0,
                converged=True,
                terminal_currents_a_per_m2={"left": 0.0, "right": 0.0},
            ),
        ),
        axes={
            "x_node": ScientificAxis(
                id="x_node", kind="position", label="Position", unit="m", values=(0.0, 1.0)
            ),
            "x_edge": ScientificAxis(
                id="x_edge", kind="position", label="Position", unit="m", values=(0.5,)
            ),
        },
        datasets={
            "potential": Dataset(
                id="potential",
                label="Potential",
                unit="V",
                axes=("x_node",),
                shape=(2,),
                values=(0.0, 1.0),
            ),
            "electric_field": Dataset(
                id="electric_field",
                label="Field",
                unit="V/m",
                axes=("x_edge",),
                shape=(1,),
                centering="edge",
                values=(4.0,),
            ),
        },
    )
    del consistent

    report = ValidationEngine().validate(test_result)

    assert report.checks_by_id["electric-field-potential-gradient"].status == "failed"


def test_bias_indexed_fields_validate_each_converged_profile() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        axes={
            "bias": ScientificAxis(
                id="bias", kind="bias", label="Bias", unit="V", values=(0.0, 1.0)
            ),
            "x_node": ScientificAxis(
                id="x_node", kind="position", label="Position", unit="m", values=(0.0, 1.0, 2.0)
            ),
            "x_edge": ScientificAxis(
                id="x_edge", kind="position", label="Position", unit="m", values=(0.5, 1.5)
            ),
        },
        datasets={
            "potential": Dataset(
                id="potential",
                label="Potential",
                unit="V",
                axes=("bias", "x_node"),
                shape=(2, 3),
                values=(0.0, 1.0, 3.0, 0.0, 9.0, 9.0),
                validity=(True, True, True, False, False, False),
            ),
            "electric_field": Dataset(
                id="electric_field",
                label="Electric field",
                unit="V/m",
                axes=("bias", "x_edge"),
                shape=(2, 2),
                centering="edge",
                values=(-1.0, -2.0, 8.0, 8.0),
                validity=(True, True, False, False),
            ),
        },
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["electric-field-potential-gradient"].status == "passed"
