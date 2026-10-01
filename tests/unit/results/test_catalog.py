from tcad_agent.results.catalog import ResultViewKind, build_dataset_catalog
from tcad_agent.results.datasets import Dataset, DatasetCentering, ScientificAxis
from tcad_agent.results.models import CanonicalResult


def test_catalog_selects_views_from_dataset_structure_not_device_names() -> None:
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        axes={
            "x": ScientificAxis(
                id="x", kind="position", label="Position", unit="m", values=(0.0, 1.0)
            ),
            "bias": ScientificAxis(
                id="bias", kind="bias", label="Bias", unit="V", values=(0.0, 1.0)
            ),
        },
        datasets={
            "scalar": Dataset(
                id="scalar",
                label="Scalar",
                unit="V",
                axes=(),
                shape=(),
                centering=DatasetCentering.SCALAR,
                values=(1.0,),
            ),
            "curve": Dataset(
                id="curve",
                label="Curve",
                unit="A/m^2",
                axes=("bias",),
                shape=(2,),
                values=(0.0, 1.0),
            ),
            "family": Dataset(
                id="family",
                label="Family",
                unit="V",
                axes=("bias", "x"),
                shape=(2, 2),
                values=(0.0, 1.0, 2.0, 3.0),
            ),
        },
    )

    catalog = {entry.id: entry for entry in build_dataset_catalog(result)}

    assert catalog["scalar"].view is ResultViewKind.SCALAR
    assert catalog["curve"].view is ResultViewKind.CURVE
    assert catalog["family"].view is ResultViewKind.PROFILE_FAMILY
