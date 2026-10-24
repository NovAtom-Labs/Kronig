"""Synthetic export interoperability, not licensed Sentaurus reference physics."""

import hashlib
import json

import pytest
from test_sentaurus_normalizer import native

from tcad_agent.adapters.sentaurus.normalizer import (
    SentaurusNormalizationError,
    SentaurusNormalizer,
)
from tcad_agent.results.query import query_dataset


def export(tmp_path):
    csv_path = tmp_path / "profiles.csv"
    csv_path.write_text(
        "potential,density\n0,1e16\n0.2,2e16\n0.4,3e16\n0,1e16\n0.3,4e16\n0.8,5e16\n"
    )
    return {
        "schema_version": "2.0",
        "simulator_version": "synthetic-not-a-native-benchmark",
        "status": "completed",
        "terminals": ["left", "right"],
        "provenance": {
            "compiler_version": "synthetic-compiler",
            "experiment_sha256": "a" * 64,
            "mesh_sha256": "b" * 64,
        },
        "sign_convention": {
            "terminal_current": "positive_into_device",
            "terminal_charge": "outward_displacement_flux",
        },
        "axes": {
            "bias": {
                "id": "bias",
                "kind": "bias",
                "label": "Drive",
                "unit": "V",
                "values": [-1, 0.6],
            },
            "position": {
                "id": "position",
                "kind": "position",
                "label": "Position",
                "unit": "um",
                "values": [0, 0.4, 1.7],
            },
        },
        "datasets": {
            "potential": {
                "id": "potential",
                "quantity": "potential",
                "label": "Potential",
                "unit": "V",
                "axes": ["bias", "position"],
                "shape": [2, 3],
                "centering": "node",
                "table": {
                    "file": "profiles.csv",
                    "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                    "column": "potential",
                },
            },
            "density": {
                "id": "density",
                "quantity": "electron_density",
                "label": "Electrons",
                "unit": "cm^-3",
                "axes": ["bias", "position"],
                "shape": [2, 3],
                "centering": "node",
                "table": {
                    "file": "profiles.csv",
                    "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                    "column": "density",
                },
            },
            "capacitance": {
                "id": "capacitance",
                "quantity": "capacitance_density",
                "label": "Capacitance density",
                "unit": "F/cm^2",
                "axes": ["bias"],
                "shape": [2],
                "centering": "operating_point",
                "values": [1e-8, 2e-8],
            },
        },
        "operating_points": [
            {
                "index": 0,
                "state": "converged",
                "coordinates": {"bias": -1},
                "terminal_currents_a_per_m2": {"left": 2e-7, "right": -2e-7},
            },
            {
                "index": 1,
                "state": "converged",
                "coordinates": {"bias": 0.6},
                "terminal_currents_a_per_m2": {"left": 3e-2, "right": -3e-2},
            },
        ],
    }


def normalize(tmp_path, data):
    path = tmp_path / "sentaurus-result.json"
    path.write_text(json.dumps(data))
    return SentaurusNormalizer().normalize(native(path))


def test_exported_tables_preserve_bias_profiles_and_workbench_queries(tmp_path):
    result = normalize(tmp_path, export(tmp_path))
    assert result.axes["position"].values == pytest.approx((0, 4e-7, 1.7e-6))
    assert result.datasets["density"].values[-1] == pytest.approx(5e22)
    curve = query_dataset(result, "capacitance", max_points=100)
    assert curve.unit == "F/m^2"
    assert curve.values == pytest.approx((1e-4, 2e-4))
    profile = query_dataset(result, "potential", max_points=100, slice_axis="bias", slice_index=1)
    assert profile.selection == {"bias": 0.6}
    assert profile.values == (0, 0.3, 0.8)
    assert result.bias_points[1].terminal_currents_a_per_m2["left"] == 0.03
    assert result.metadata["native_export_sha256"]
    assert result.metadata["source_hashes"]["profiles.csv"]
    assert result.metadata["declared_provenance"]["compiler_version"] == "synthetic-compiler"
    assert not result.fields  # Never invent a single bias-free profile from a family.


@pytest.mark.parametrize(
    "unit,quantity",
    [("V", "electron_density"), ("A", "terminal_current_density"), ("F", "capacitance_density")],
)
def test_semantically_wrong_units_cannot_masquerade_as_density(tmp_path, unit, quantity):
    data = export(tmp_path)
    data["datasets"]["capacitance"].update(unit=unit, quantity=quantity)
    with pytest.raises(SentaurusNormalizationError, match="unit"):
        normalize(tmp_path, data)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda d: d["datasets"]["potential"]["table"].update(file="../profiles.csv"), "file"),
        (lambda d: d["datasets"]["potential"]["table"].update(sha256="0" * 64), "hash"),
        (lambda d: d["datasets"]["potential"].update(shape=[3, 3]), "shape"),
        (lambda d: d.update(terminals=["left", "left"]), "terminal"),
        (
            lambda d: d["operating_points"][0]["terminal_currents_a_per_m2"].update(unknown=1),
            "terminal",
        ),
        (lambda d: d["axes"]["position"].update(values=[0, 1, 1]), "position"),
        (lambda d: d["operating_points"][0]["coordinates"].update(bias=float("nan")), "finite"),
    ],
)
def test_invalid_exports_fail_closed(tmp_path, mutation, message):
    data = export(tmp_path)
    mutation(data)
    with pytest.raises(SentaurusNormalizationError, match=message):
        normalize(tmp_path, data)


def test_complex_frequency_curve_and_absolute_quantity_remain_distinct(tmp_path):
    data = export(tmp_path)
    data["operating_points"].extend(
        [
            {"index": 2, "state": "converged", "coordinates": {"frequency": 1000}},
            {"index": 3, "state": "converged", "coordinates": {"frequency": 10000}},
        ]
    )
    data["axes"]["frequency"] = {
        "id": "frequency",
        "kind": "frequency",
        "label": "Frequency",
        "unit": "kHz",
        "values": [1, 10],
    }
    data["datasets"]["admittance"] = {
        "id": "admittance",
        "quantity": "admittance",
        "label": "Admittance",
        "unit": "S",
        "axes": ["frequency"],
        "shape": [2],
        "centering": "operating_point",
        "values": [1e-7, 2e-7],
        "imaginary_values": [3e-6, 5e-6],
    }
    data["datasets"]["absolute_c"] = {
        "id": "absolute_c",
        "quantity": "capacitance",
        "label": "Absolute capacitance",
        "unit": "F",
        "axes": ["bias"],
        "shape": [2],
        "centering": "operating_point",
        "values": [1e-12, 2e-12],
    }
    result = normalize(tmp_path, data)
    curve = query_dataset(result, "admittance", max_points=100)
    assert curve.axes[0].values == (1000, 10000)
    assert curve.imaginary_values == (3e-6, 5e-6)
    assert result.datasets["absolute_c"].unit == "F"
    assert result.datasets["capacitance"].unit == "F/m^2"


def test_csv_symlinks_and_modified_tables_are_rejected(tmp_path):
    data = export(tmp_path)
    path = tmp_path / "profiles.csv"
    target = tmp_path / "other.csv"
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(SentaurusNormalizationError, match="symlink"):
        normalize(tmp_path, data)
    path.unlink()
    path.write_text("potential,density\n0,9e99\n")
    with pytest.raises(SentaurusNormalizationError, match="hash"):
        normalize(tmp_path, data)


def test_csv_duplicate_columns_and_nonfinite_values_are_rejected(tmp_path):
    data = export(tmp_path)
    path = tmp_path / "profiles.csv"
    path.write_text("potential,potential\n0,nan\n")
    for dataset in (data["datasets"]["potential"], data["datasets"]["density"]):
        dataset["table"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(SentaurusNormalizationError, match="column"):
        normalize(tmp_path, data)


def test_failed_operating_point_never_looks_like_a_valid_curve_point(tmp_path):
    data = export(tmp_path)
    data["operating_points"][1]["state"] = "failed"
    result = normalize(tmp_path, data)
    assert result.operating_points[1].state == "failed"
    assert result.datasets["potential"].validity == (True, True, True, False, False, False)
    assert result.datasets["capacitance"].validity == (True, False)
    assert not result.bias_points[1].converged


def test_axis_scaling_cannot_create_infinite_coordinates(tmp_path):
    data = export(tmp_path)
    data["axes"]["frequency"] = {
        "id": "frequency",
        "kind": "frequency",
        "label": "f",
        "unit": "MHz",
        "values": [1e308],
    }
    with pytest.raises(SentaurusNormalizationError, match="finite"):
        normalize(tmp_path, data)


def test_csv_size_budget_applies_across_distinct_files(tmp_path, monkeypatch):
    from tcad_agent.adapters.sentaurus import tables

    data = export(tmp_path)
    first = tmp_path / "profiles.csv"
    second = tmp_path / "second.csv"
    second.write_bytes(first.read_bytes())
    data["datasets"]["density"]["table"]["file"] = second.name
    monkeypatch.setattr(tables, "_MAX_BYTES", first.stat().st_size + 1)
    with pytest.raises(SentaurusNormalizationError, match="total CSV"):
        normalize(tmp_path, data)


def test_declared_shapes_are_bounded_before_loading_tables(tmp_path):
    data = export(tmp_path)
    data["datasets"]["potential"]["shape"] = [2, 2_000_001]
    with pytest.raises(SentaurusNormalizationError, match="value budget"):
        normalize(tmp_path, data)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["operating_points"][1]["coordinates"].update(bias=0.7),
        lambda d: d["operating_points"][1]["coordinates"].update(typo=0.6),
        lambda d: d["axes"]["bias"].update(values=[-1, -1]),
    ],
)
def test_point_axis_mismatch_never_bypasses_failed_sample_mask(tmp_path, mutation):
    data = export(tmp_path)
    data["operating_points"][1]["state"] = "failed"
    mutation(data)
    with pytest.raises(SentaurusNormalizationError, match="coordinate"):
        normalize(tmp_path, data)


def test_bias_axis_kind_not_identifier_controls_legacy_projection(tmp_path):
    data = export(tmp_path)
    data["axes"]["voltage"] = data["axes"].pop("bias")
    data["axes"]["voltage"]["id"] = "voltage"
    for dataset in data["datasets"].values():
        dataset["axes"] = ["voltage" if axis == "bias" else axis for axis in dataset["axes"]]
    for point in data["operating_points"]:
        point["coordinates"]["voltage"] = point["coordinates"].pop("bias")
    result = normalize(tmp_path, data)
    assert tuple(point.bias_v for point in result.bias_points) == (-1, 0.6)
