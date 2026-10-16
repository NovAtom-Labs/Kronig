import pytest

from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult, OperatingPoint
from tcad_agent.validation.charge import integrated_charge_check


def test_contact_flux_uses_recorded_control_volume_weights_not_boundary_nodes_twice():
    result = evidence(-1, (2.0, 1.0, 2.0))
    datasets = {
        **result.datasets,
        "validation_charge_weight": Dataset(
            id="validation_charge_weight",
            label="Poisson integration weight",
            unit="m",
            axes=("x",),
            shape=(3,),
            values=(0.0, 1.0, 0.0),
        ),
    }
    result = result.model_copy(update={"datasets": datasets})
    assert (
        integrated_charge_check(result, relative_tolerance=0.03, absolute_tolerance=1e-10).status
        == "passed"
    )


def evidence(terminal_charge=-2.0, values=(1.0, 1.0, 1.0)):
    return CanonicalResult(
        backend="devsim",
        status="completed",
        terminals=("a", "b"),
        axes={"x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=(0, 1, 2))},
        datasets={
            "charge_density": Dataset(
                id="charge_density",
                label="rho",
                unit="C/m^3",
                axes=("x",),
                shape=(3,),
                values=values,
            )
        },
        operating_points=(
            OperatingPoint(
                index=0,
                state="converged",
                coordinates={"bias": 0},
                terminal_charges_c_per_m2={"a": terminal_charge, "b": 0},
            ),
        ),
        metadata={},
    )


def test_bulk_charge_is_integrated_before_terminal_balance():
    check = integrated_charge_check(evidence(), relative_tolerance=0.03, absolute_tolerance=1e-10)
    assert check.status == "passed"
    assert check.measured_value == 0


def test_wrong_terminal_charge_fails_despite_convergence():
    assert (
        integrated_charge_check(
            evidence(-1), relative_tolerance=0.03, absolute_tolerance=1e-10
        ).status
        == "failed"
    )


def test_region_interfaces_do_not_add_spurious_integrals():
    result = evidence(-4)
    # Two contiguous regions of length one, with a discontinuity at x=1.
    result = result.model_copy(
        update={
            "axes": {
                "x": ScientificAxis(
                    id="x", kind="position", label="x", unit="m", values=(0, 1, 1, 2)
                )
            },
            "datasets": {
                "charge_density": Dataset(
                    id="charge_density",
                    label="rho",
                    unit="C/m^3",
                    axes=("x",),
                    shape=(4,),
                    values=(1, 1, 3, 3),
                )
            },
        }
    )
    assert (
        integrated_charge_check(result, relative_tolerance=0.03, absolute_tolerance=1e-10).status
        == "passed"
    )


def test_one_terminal_with_a_zero_flux_boundary_can_balance_bulk_charge():
    result = evidence()
    point = result.operating_points[0].model_copy(update={"terminal_charges_c_per_m2": {"a": -2.0}})
    result = result.model_copy(update={"terminals": ("a",), "operating_points": (point,)})
    assert (
        integrated_charge_check(result, relative_tolerance=0.03, absolute_tolerance=1e-10).status
        == "passed"
    )


def test_zero_current_at_one_declared_terminal_does_not_require_a_second_terminal():
    from tcad_agent.validation.engine import ValidationEngine

    result = evidence()
    point = result.operating_points[0].model_copy(update={"terminal_currents_a_per_m2": {"a": 0.0}})
    result = result.model_copy(update={"terminals": ("a",), "operating_points": (point,)})
    assert (
        ValidationEngine().validate(result).checks_by_id["terminal-current-conservation"].status
        == "passed"
    )


@pytest.mark.parametrize(
    "missing", ["charge_density", "validation_charge_weight", "validation_sheet_charge"]
)
def test_native_evidence_cannot_pass_or_be_skipped_when_a_required_charge_field_is_missing(missing):
    result = evidence()
    datasets = {
        **result.datasets,
        "validation_charge_weight": Dataset(
            id="validation_charge_weight",
            label="Poisson volume",
            unit="m",
            axes=("x",),
            shape=(3,),
            values=(0, 2, 0),
        ),
        "validation_sheet_charge": Dataset(
            id="validation_sheet_charge",
            label="Sheet source",
            unit="C/m^2",
            axes=("sheet",),
            shape=(1,),
            values=(0,),
        ),
    }
    del datasets[missing]
    result = result.model_copy(
        update={
            "metadata": {"validation_evidence_version": "1"},
            "datasets": datasets,
            "axes": {
                **result.axes,
                "sheet": ScientificAxis(
                    id="sheet", kind="position", label="Sheet coordinate", unit="m", values=(0,)
                ),
            },
        }
    )
    assert (
        integrated_charge_check(result, relative_tolerance=0.03, absolute_tolerance=1e-10).status
        == "failed"
    )
