from tcad_agent.domain.models import ExperimentSpec
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


def test_band_ordering_is_checked_from_canonical_energy_fields() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        axes={
            "x": ScientificAxis(
                id="x", kind="position", label="Position", unit="m", values=(0.0, 1.0)
            )
        },
        datasets={
            "conduction_band": Dataset(
                id="conduction_band",
                label="Conduction band",
                unit="eV",
                axes=("x",),
                shape=(2,),
                values=(0.5, -0.5),
            ),
            "valence_band": Dataset(
                id="valence_band",
                label="Valence band",
                unit="eV",
                axes=("x",),
                shape=(2,),
                values=(-0.5, 0.0),
            ),
        },
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["band-ordering"].status == "failed"


def test_recombination_components_and_generation_are_checked() -> None:
    axis = ScientificAxis(
        id="x", kind="position", label="Position", unit="m", values=(0.0, 1.0)
    )

    def rate(identifier: str, values: tuple[float, float]) -> Dataset:
        return Dataset(
            id=identifier,
            label=identifier,
            unit="m^-3/s",
            axes=("x",),
            shape=(2,),
            values=values,
        )

    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        axes={"x": axis},
        datasets={
            "srh_recombination_rate": rate("srh_recombination_rate", (2.0, 3.0)),
            "auger_recombination_rate": rate("auger_recombination_rate", (1.0, 1.0)),
            "total_recombination_rate": rate("total_recombination_rate", (3.0, 9.0)),
            "electron_generation_rate": rate("electron_generation_rate", (-3.0, -4.0)),
            "hole_generation_rate": rate("hole_generation_rate", (-3.0, -4.0)),
        },
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["recombination-component-balance"].status == "failed"
    assert report.checks_by_id["generation-recombination-sign"].status == "failed"


def test_requested_bidirectional_bias_order_is_checked_without_forcing_monotonicity() -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "ordered points",
            "dimension": 1,
            "regions": [
                {
                    "id": "bulk",
                    "material": "silicon",
                    "x0": "0 um",
                    "x1": "1 um",
                }
            ],
            "profiles": [],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {
                "kind": "dc_points",
                "contact": "right",
                "values": ["0 V", "1 V", "-1 V"],
            },
            "observables": ["potential"],
        }
    )
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("left", "right"),
        bias_points=tuple(
            BiasPoint(
                bias_v=value,
                converged=True,
                terminal_currents_a_per_m2={"left": 0.0, "right": 0.0},
            )
            for value in (0.0, 1.0, -1.0)
        ),
    )

    report = ValidationEngine().validate(result, spec=spec)

    assert report.checks_by_id["requested-study-order"].status == "passed"

    reordered = result.model_copy(
        update={
            "bias_points": (
                result.bias_points[0],
                result.bias_points[2],
                result.bias_points[1],
            )
        }
    )
    failed = ValidationEngine().validate(reordered, spec=spec)
    assert failed.checks_by_id["requested-study-order"].status == "failed"
