import pytest

from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult
from tcad_agent.results.query import DatasetQueryError, query_dataset


def test_rank_one_query_downsamples_axes_values_and_validity_together() -> None:
    values = tuple(100.0 if index == 50 else float(index % 7) for index in range(101))
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        axes={
            "bias": ScientificAxis(
                id="bias",
                kind="bias",
                label="Bias",
                unit="V",
                values=tuple(float(index) for index in range(101)),
            )
        },
        datasets={
            "current": Dataset(
                id="current",
                label="Current density",
                unit="A/m^2",
                axes=("bias",),
                shape=(101,),
                values=values,
                validity=tuple(index != 25 for index in range(101)),
            )
        },
    )

    queried = query_dataset(result, "current", max_points=20)

    assert queried.shape == (len(queried.values),)
    assert queried.axes[0].values[0] == 0.0
    assert queried.axes[0].values[-1] == 100.0
    assert 100.0 in queried.values
    assert len(queried.values) <= 20
    assert len(queried.validity or ()) == len(queried.values)


def test_rank_two_query_returns_one_explicit_scientific_slice() -> None:
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        axes={
            "bias": ScientificAxis(
                id="bias", kind="bias", label="Bias", unit="V", values=(-1.0, 0.0, 1.0)
            ),
            "x": ScientificAxis(
                id="x", kind="position", label="Position", unit="m", values=(0.0, 1.0)
            ),
        },
        datasets={
            "potential": Dataset(
                id="potential",
                label="Potential",
                unit="V",
                axes=("bias", "x"),
                shape=(3, 2),
                values=(0.0, 0.1, 1.0, 1.1, 2.0, 2.1),
            )
        },
    )

    queried = query_dataset(
        result,
        "potential",
        slice_axis="bias",
        slice_index=1,
        max_points=10,
    )

    assert queried.axes[0].id == "x"
    assert queried.shape == (2,)
    assert queried.values == (1.0, 1.1)
    assert queried.selection == {"bias": 0.0}


def test_rank_two_query_requires_an_explicit_valid_slice() -> None:
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        axes={
            "a": ScientificAxis(id="a", kind="index", label="A", unit="1", values=(0.0, 1.0)),
            "b": ScientificAxis(id="b", kind="index", label="B", unit="1", values=(0.0, 1.0)),
        },
        datasets={
            "matrix": Dataset(
                id="matrix",
                label="Matrix",
                unit="1",
                axes=("a", "b"),
                shape=(2, 2),
                values=(0.0, 1.0, 2.0, 3.0),
            )
        },
    )

    with pytest.raises(DatasetQueryError, match="explicit slice"):
        query_dataset(result, "matrix", max_points=10)
