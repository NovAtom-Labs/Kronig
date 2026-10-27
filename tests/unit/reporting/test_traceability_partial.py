from tcad_agent.reporting.traceability import _valid_dataset
from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult, OperatingPoint


def _result(validity, state="converged"):
    x = (0.0, 1.0, 2.0)
    return CanonicalResult(
        backend="sentaurus",
        status="completed",
        axes={
            "bias": ScientificAxis(id="bias", kind="bias", label="V", unit="V", values=(0.0,)),
            "x": ScientificAxis(id="x", kind="position", label="x", unit="m", values=x),
        },
        datasets={
            "electron_density": Dataset(
                id="electron_density",
                label="n",
                unit="m^-3",
                axes=("bias", "x"),
                shape=(1, 3),
                centering="node",
                values=(0.0, 5.0, 7.0),
                validity=validity,
            )
        },
        operating_points=(OperatingPoint(index=0, state=state, coordinates={"bias": 0.0}),),
    )


def test_carriers_that_do_not_exist_in_an_oxide_do_not_make_the_output_incomplete() -> None:
    assert _valid_dataset(_result((False, True, True)), "electron_density")


def test_a_mask_left_by_a_failed_solve_still_makes_the_output_incomplete() -> None:
    assert not _valid_dataset(_result((False, True, True), state="failed"), "electron_density")
    assert not _valid_dataset(_result((False, False, False)), "electron_density")
    assert not _valid_dataset(_result(None), "missing")