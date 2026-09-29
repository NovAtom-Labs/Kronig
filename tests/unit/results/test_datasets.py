import pytest
from pydantic import ValidationError

from tcad_agent.results.datasets import (
    Dataset,
    DatasetCentering,
    ScientificAxis,
)
from tcad_agent.results.models import CanonicalResult, FieldSeries


def test_position_dataset_preserves_node_centering_and_shape() -> None:
    axis = ScientificAxis(
        id="position",
        kind="position",
        label="Position",
        unit="m",
        values=(0.0, 0.5e-6, 1e-6),
    )
    dataset = Dataset(
        id="potential",
        label="Electrostatic potential",
        unit="V",
        axes=("position",),
        shape=(3,),
        centering=DatasetCentering.NODE,
        values=(0.0, 0.3, 0.7),
    )
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        axes={axis.id: axis},
        datasets={dataset.id: dataset},
    )

    assert result.datasets["potential"].shape == (3,)
    assert result.datasets["potential"].centering == "node"


def test_dataset_rejects_shape_value_count_mismatch() -> None:
    with pytest.raises(ValidationError, match="shape"):
        Dataset(
            id="field",
            label="Field",
            unit="V/m",
            axes=("position",),
            shape=(3,),
            values=(1.0, 2.0),
        )


def test_complex_dataset_requires_matching_imaginary_values() -> None:
    with pytest.raises(ValidationError, match="imaginary"):
        Dataset(
            id="admittance",
            label="Admittance",
            unit="S/m^2",
            axes=("frequency",),
            shape=(2,),
            values=(1.0, 2.0),
            imaginary_values=(0.1,),
        )


def test_dataset_validity_mask_matches_storage_shape() -> None:
    dataset = Dataset(
        id="potential_sweep",
        label="Potential sweep",
        unit="V",
        axes=("bias", "position"),
        shape=(2, 2),
        centering=DatasetCentering.NODE,
        values=(0.0, 0.1, 0.2, 0.3),
        validity=(True, True, False, False),
    )

    assert dataset.validity == (True, True, False, False)

    with pytest.raises(ValidationError, match="validity mask"):
        Dataset(
            id="bad_mask",
            label="Bad mask",
            unit="V",
            axes=("bias", "position"),
            shape=(2, 2),
            centering=DatasetCentering.NODE,
            values=(0.0, 0.1, 0.2, 0.3),
            validity=(True, False),
        )


def test_result_rejects_unknown_axis_and_axis_length_mismatch() -> None:
    with pytest.raises(ValidationError, match="unknown axes"):
        CanonicalResult(
            backend="devsim",
            status="completed",
            datasets={
                "potential": Dataset(
                    id="potential",
                    label="Potential",
                    unit="V",
                    axes=("position",),
                    shape=(2,),
                    values=(0.0, 1.0),
                )
            },
        )


def test_legacy_fields_are_migrated_to_axis_aware_datasets() -> None:
    result = CanonicalResult(
        schema_version="1.0",
        backend="devsim",
        status="completed",
        fields={
            "potential": FieldSeries(
                positions_m=(0.0, 1e-6), values=(0.0, 0.8), unit="V"
            )
        },
    )

    assert result.datasets["potential"].axes == ("position__potential",)
    assert result.axes["position__potential"].values == (0.0, 1e-6)
