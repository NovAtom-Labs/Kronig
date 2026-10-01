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


def test_band_ordering_accepts_semantically_equal_axes_with_different_ids() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        axes={
            "conduction_position": ScientificAxis(
                id="conduction_position",
                kind="position",
                label="Position",
                unit="m",
                values=(0.0, 1.0),
            ),
            "valence_position": ScientificAxis(
                id="valence_position",
                kind="position",
                label="Position",
                unit="m",
                values=(0.0, 1.0),
            ),
        },
        datasets={
            "conduction_band": Dataset(
                id="conduction_band",
                label="Conduction band",
                unit="eV",
                axes=("conduction_position",),
                shape=(2,),
                values=(0.6, 0.7),
            ),
            "valence_band": Dataset(
                id="valence_band",
                label="Valence band",
                unit="eV",
                axes=("valence_position",),
                shape=(2,),
                values=(-0.5, -0.4),
            ),
        },
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["band-ordering"].status == "passed"


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


def test_recombination_balance_accepts_semantically_equal_axes_with_different_ids() -> None:
    axes = {
        identifier: ScientificAxis(
            id=identifier,
            kind="position",
            label="Position",
            unit="m",
            values=(0.0, 1.0),
        )
        for identifier in ("total_position", "srh_position", "auger_position")
    }

    def rate(identifier: str, axis: str, values: tuple[float, float]) -> Dataset:
        return Dataset(
            id=identifier,
            label=identifier,
            unit="m^-3/s",
            axes=(axis,),
            shape=(2,),
            values=values,
        )

    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        axes=axes,
        datasets={
            "srh_recombination_rate": rate(
                "srh_recombination_rate", "srh_position", (2.0, 3.0)
            ),
            "auger_recombination_rate": rate(
                "auger_recombination_rate", "auger_position", (1.0, 1.0)
            ),
            "total_recombination_rate": rate(
                "total_recombination_rate", "total_position", (3.0, 4.0)
            ),
        },
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["recombination-component-balance"].status == "passed"


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


def test_poisson_residual_uses_canonical_flux_and_charge() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        axes={
            "x_node": ScientificAxis(
                id="x_node",
                kind="position",
                label="Position",
                unit="m",
                values=(0.0, 1.0, 2.0, 3.0),
            ),
            "x_edge": ScientificAxis(
                id="x_edge",
                kind="position",
                label="Position",
                unit="m",
                values=(0.5, 1.5, 2.5),
            ),
        },
        datasets={
            "electrostatic_flux": Dataset(
                id="electrostatic_flux",
                label="Electric displacement flux",
                unit="C/m^2",
                axes=("x_edge",),
                shape=(3,),
                centering="edge",
                values=(0.0, 2.0, 5.0),
            ),
            "charge_density": Dataset(
                id="charge_density",
                label="Charge density",
                unit="C/m^3",
                axes=("x_node",),
                shape=(4,),
                centering="node",
                values=(99.0, 2.0, 3.0, 99.0),
            ),
        },
    )

    report = ValidationEngine().validate(result)

    assert report.checks_by_id["poisson-residual-consistency"].status == "passed"
    inconsistent = result.model_copy(
        update={
            "datasets": {
                **result.datasets,
                "charge_density": result.datasets["charge_density"].model_copy(
                    update={"values": (99.0, 8.0, 3.0, 99.0)}
                ),
            }
        }
    )
    failed = ValidationEngine().validate(inconsistent)
    assert failed.checks_by_id["poisson-residual-consistency"].status == "failed"


def test_sweep_continuity_detects_isolated_canonical_outlier() -> None:
    axis = ScientificAxis(
        id="bias",
        kind="bias",
        label="Bias",
        unit="V",
        values=(-2.0, -1.0, 0.0, 1.0, 2.0),
    )

    def result_with(values: tuple[float, ...]) -> CanonicalResult:
        return CanonicalResult(
            backend="devsim",
            simulator_version="2.9.1",
            status="completed",
            axes={"bias": axis},
            datasets={
                "terminal_current__right": Dataset(
                    id="terminal_current__right",
                    label="Terminal current",
                    unit="A/m^2",
                    axes=("bias",),
                    shape=(5,),
                    centering="operating_point",
                    values=values,
                )
            },
        )

    continuous = ValidationEngine().validate(result_with((-2.0, -1.0, 0.0, 1.0, 2.0)))
    discontinuous = ValidationEngine().validate(
        result_with((-2.0, -1.0, 10000.0, 1.0, 2.0))
    )

    assert continuous.checks_by_id["sweep-continuity"].status == "passed"
    assert discontinuous.checks_by_id["sweep-continuity"].status == "failed"


def test_ac_and_quasistatic_capacitance_are_compared_when_pair_is_present() -> None:
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        axes={
            "frequency": ScientificAxis(
                id="frequency",
                kind="frequency",
                label="Frequency",
                unit="Hz",
                values=(1.0, 10.0),
            ),
            "bias": ScientificAxis(
                id="bias",
                kind="bias",
                label="Bias",
                unit="V",
                values=(-0.1, 0.0, 0.1),
            ),
        },
        datasets={
            "ac_capacitance__gate": Dataset(
                id="ac_capacitance__gate",
                label="AC capacitance",
                unit="F/m^2",
                axes=("frequency",),
                shape=(2,),
                centering="contact",
                values=(2.02e-3, 1.9e-3),
                metadata={"dc_operating_point_v": "0.0"},
            ),
            "capacitance__gate": Dataset(
                id="capacitance__gate",
                label="Quasi-static capacitance",
                unit="F/m^2",
                axes=("bias",),
                shape=(3,),
                centering="operating_point",
                values=(2.1e-3, 2.0e-3, 1.9e-3),
            ),
        },
    )

    passed = ValidationEngine().validate(result)
    failed_result = result.model_copy(
        update={
            "datasets": {
                **result.datasets,
                "ac_capacitance__gate": result.datasets[
                    "ac_capacitance__gate"
                ].model_copy(update={"values": (4.0e-3, 3.8e-3)}),
            }
        }
    )
    failed = ValidationEngine().validate(failed_result)

    assert passed.checks_by_id["ac-quasistatic-capacitance-consistency"].status == "passed"
    assert failed.checks_by_id["ac-quasistatic-capacitance-consistency"].status == "failed"
