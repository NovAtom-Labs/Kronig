"""Generated unit-slab mesh, remote pipeline script and local TDR export.

The TDR here is a synthetic file with the documented structure, not licensed output.
"""

from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from tcad_agent.adapters.sentaurus.compiler import SentaurusAdapter
from tcad_agent.adapters.sentaurus.mesh import build_run_script, build_sde_script
from tcad_agent.adapters.sentaurus.native_export import NativeExportError, build_export
from tcad_agent.adapters.sentaurus.normalizer import SentaurusNormalizer
from tcad_agent.adapters.sentaurus.runtime import SentaurusJobManifest, validate_bundle
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.models import NativeRunResult

VERSION = "O-2018.06-SP2"


def pn_spec() -> ExperimentSpec:
    data = yaml.safe_load(Path("examples/pn-junction.yaml").read_text(encoding="utf-8"))
    data["study"] = {
        "kind": "dc",
        "contact": "anode",
        "start": "0 V",
        "stop": "0.1 V",
        "step": "0.1 V",
    }
    return ExperimentSpec.model_validate(data)


def test_structure_script_encodes_regions_doping_contacts_and_mesh() -> None:
    script = build_sde_script(pn_spec())
    assert '"Silicon" "p_region")' in script and '"Silicon" "n_region")' in script
    assert '"BoronActiveConcentration" 1e+17' in script
    assert '"ArsenicActiveConcentration" 1e+16' in script
    assert '(position 0 0.5 0)) "anode")' in script
    assert '(position 1 0.5 0)) "cathode")' in script
    assert '"ref_p_region" 0.01 1 0.01 1' in script
    assert script.rstrip().endswith('(sde:build-mesh "snmesh" "" "n1")')


def test_run_script_uses_only_sentaurus_and_posix_tools() -> None:
    script = build_run_script()
    assert script.startswith("#!/bin/sh")
    for forbidden in ("python", "h5", "tclsh", "perl", "svisual", "tdx"):
        assert forbidden not in script
    assert "sde -e -l mesh.scm" in script
    # The device simulator runs the default deck, then the prepared escalation decks if needed.
    assert "for deck in sdevice.cmd sdevice.r1.cmd sdevice.r2.cmd" in script
    assert 'sdevice "$deck"' in script and "KRONIG numerics level" in script


def test_generated_mesh_bundle_is_hash_bound_and_needs_a_release(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TCAD_SENTAURUS_VERSION", raising=False)
    with pytest.raises(CapabilityError, match="TCAD_SENTAURUS_VERSION"):
        SentaurusAdapter.from_defaults("sde").compile(pn_spec(), tmp_path / "missing")
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    job = SentaurusAdapter.from_defaults("sde").compile(pn_spec(), tmp_path / "job")
    manifest = validate_bundle(job, simulator_version=VERSION)
    assert manifest.mesh_generation == "sde_unit_slab"
    assert {path.name for path in job.input_files} >= {"mesh.scm", "run.sh", "sdevice.cmd"}
    assert manifest.expected_outputs == ("point_0000_des.tdr", "point_0001_des.tdr")
    assert manifest.native_review is not None
    assert "not human-reviewed" in manifest.native_review.reference


def _write_tdr(path: Path, bias: float) -> None:
    """Two bulk regions (p: x 0-0.5, n: x 0.5-1 um) plus two contacts on a 2-high slab."""
    xs = [0.0, 0.5, 1.0]
    points = [(x, y) for x in xs for y in (0.0, 1.0)]
    vertices = np.array(points, dtype=[("x", "<f8"), ("y", "<f8")])
    with h5py.File(path, "w") as handle:
        geometry = handle.create_group("collection/geometry_0")
        geometry.create_dataset("vertex", data=vertices)
        regions = {
            0: ("p_region", 0, [2, 0, 1, 2, 2, 1, 3, 2]),
            1: ("n_region", 0, [2, 2, 3, 4, 2, 3, 5, 4]),
            2: ("anode", 1, [1, 0, 1]),
            3: ("cathode", 1, [1, 4, 5]),
        }
        for index, (name, kind, elements) in regions.items():
            group = geometry.create_group(f"region_{index}")
            group.attrs["name"] = np.bytes_(name)
            group.attrs["type"] = np.int32(kind)
            group.create_dataset("elements_0", data=np.array(elements, dtype=np.int32))
        state = geometry.create_group("state_0")
        entries = []

        def add(name, region, values, unit):
            entries.append((name, region, np.asarray(values, dtype=float), unit))

        add("ElectrostaticPotential", 0, [0.0, 0.0, 0.3, 0.3], "V")
        add("ElectrostaticPotential", 1, [0.3, 0.3, 0.5, 0.5], "V")
        add("eDensity", 0, [1e5, 1e5, 1e9, 1e9], "cm^-3")
        add("eDensity", 1, [1e9, 1e9, 1e16, 1e16], "cm^-3")
        add("hDensity", 0, [1e17, 1e17, 1e12, 1e12], "cm^-3")
        add("hDensity", 1, [1e12, 1e12, 1e4, 1e4], "cm^-3")
        add("ElectricField", 0, [0, 0, 0, 0, 5e4, 0, 5e4, 0], "V*cm^-1")
        add("ElectricField", 1, [5e4, 0, 5e4, 0, 0, 0, 0, 0], "V*cm^-1")
        add("ContactExternalVoltage", 2, [bias], "V")
        add("ContactExternalVoltage", 3, [0.0], "V")
        add("ContactCurrentFlux", 2, [2e-13], "A")
        add("ContactCurrentFlux", 3, [-2e-13], "A")
        add("ContactCharge", 2, [1e-15], "C")
        add("ContactCharge", 3, [-1e-15], "C")
        for number, (name, region, values, unit) in enumerate(entries):
            node = state.create_group(f"dataset_{number}")
            node.attrs["name"] = np.bytes_(name)
            node.attrs["region"] = np.int32(region)
            node.attrs["unit:name"] = np.bytes_(unit)
            node.create_dataset("values", data=values)


@pytest.fixture
def raw_job(tmp_path, monkeypatch):
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    job = SentaurusAdapter.from_defaults("sde").compile(pn_spec(), tmp_path / "job")
    root = job.entrypoint.parent
    raw = tmp_path / "raw"
    raw.mkdir()
    for index in range(2):
        _write_tdr(raw / f"point_{index:04d}_des.tdr", 0.1 * index)
    (raw / "sdevice.stdout.log").write_text(
        "*** Sentaurus Device ***\n***   Version O-2018.06-SP2   ***\n"
    )
    manifest = SentaurusJobManifest.model_validate_json((root / "job-manifest.json").read_bytes())
    return raw, pn_spec(), manifest


def test_local_export_normalizes_units_terminals_and_area(raw_job) -> None:
    raw, spec, manifest = raw_job
    path = build_export(raw, spec, manifest)
    result = SentaurusNormalizer().normalize(
        NativeRunResult(
            backend="sentaurus",
            status="completed",
            return_code=0,
            stdout_path=raw / "sdevice.stdout.log",
            stderr_path=raw / "sdevice.stdout.log",
            result_path=path,
            elapsed_seconds=1.0,
        )
    )
    assert result.simulator_version == VERSION
    assert result.terminals == ("anode", "cathode")
    # 2e-13 A over a 1 um high slab with the native 1 um depth: area 1e-12 m^2.
    assert result.bias_points[0].terminal_currents_a_per_m2["anode"] == pytest.approx(0.2)
    assert result.bias_points[0].terminal_currents_a_per_m2["cathode"] == pytest.approx(-0.2)
    assert result.datasets["electron_density"].unit == "m^-3"
    # Junction value converted from V/cm to V/m.
    assert result.datasets["electric_field"].values[1] == pytest.approx(5e6)
    assert result.datasets["potential"].shape == (2, 4)  # the p-n boundary keeps both sides
    assert result.metadata["declared_provenance"]["mesh_sha256"] == manifest.inputs["mesh.scm"]


def _sampled(spec: ExperimentSpec, volts: str) -> ExperimentSpec:
    data = spec.model_dump(mode="json")
    data["profile_sampling"] = {"mode": "explicit", "bias_values": [volts]}
    return ExperimentSpec.model_validate(data)


def _normalize(raw: Path, path: Path):
    return SentaurusNormalizer().normalize(
        NativeRunResult(
            backend="sentaurus",
            status="completed",
            return_code=0,
            stdout_path=raw / "sdevice.stdout.log",
            stderr_path=raw / "sdevice.stdout.log",
            result_path=path,
            elapsed_seconds=1.0,
        )
    )


def test_profile_sampling_exports_every_solved_bias_including_the_requested_one(raw_job) -> None:
    raw, spec, manifest = raw_job
    result = _normalize(raw, build_export(raw, _sampled(spec, "0.1 V"), manifest))
    assert len(result.bias_points) == 2
    assert result.datasets["potential"].shape == (2, 4)  # the p-n boundary keeps both sides
    assert 0.1 in result.axes["bias"].values


def test_profile_sampling_outside_the_schedule_is_refused_by_the_domain_model(raw_job) -> None:
    _, spec, _ = raw_job
    with pytest.raises(ValueError):
        _sampled(spec, "0.05 V")


def test_generated_mesh_compile_accepts_profile_sampling_but_external_refuses(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    sampled = _sampled(pn_spec(), "0.1 V")
    SentaurusAdapter.from_defaults("sde").compile(sampled, tmp_path / "generated")
    with pytest.raises(ValueError, match="profile_sampling"):
        SentaurusAdapter.from_defaults("external").compile(sampled, tmp_path / "external")


def _set_native_voltage(path: Path, region: int, volts: float) -> None:
    with h5py.File(path, "r+") as handle:
        state = handle["collection/geometry_0/state_0"]
        for key in state:
            node = state[key]
            if (
                key.startswith("dataset_")
                and node.attrs["name"] == b"ContactExternalVoltage"
                and int(node.attrs["region"]) == region
            ):
                node["values"][...] = [volts]


def test_a_point_the_solver_did_not_reach_is_failed_not_relabelled(raw_job) -> None:
    raw, spec, manifest = raw_job
    _set_native_voltage(raw / "point_0001_des.tdr", 2, 0.05)  # asked for 0.1 V
    result = _normalize(raw, build_export(raw, spec, manifest))
    points = {point.index: point for point in result.operating_points}
    assert points[0].state == "converged"
    assert points[1].state == "failed"
    assert "anode reached 0.05 V instead of 0.1 V" in (points[1].message or "")
    # The failed point is masked everywhere, never presented as the requested bias.
    assert result.datasets["potential"].validity[4:] == (False,) * 4
    assert result.datasets["terminal_current__anode"].validity == (True, False)


def test_an_undriven_contact_that_moved_is_also_caught(raw_job) -> None:
    raw, spec, manifest = raw_job
    _set_native_voltage(raw / "point_0000_des.tdr", 3, 0.3)  # the cathode must stay at 0 V
    result = _normalize(raw, build_export(raw, spec, manifest))
    assert result.operating_points[0].state == "failed"
    assert "cathode reached 0.3 V" in (result.operating_points[0].message or "")


def test_local_export_rejects_laterally_nonuniform_slab(raw_job) -> None:
    raw, spec, manifest = raw_job
    with h5py.File(raw / "point_0001_des.tdr", "r+") as handle:
        node = handle["collection/geometry_0/state_0/dataset_0/values"]
        values = node[()]
        values[1] += 0.2
        node[...] = values
    with pytest.raises(NativeExportError, match="laterally uniform"):
        build_export(raw, spec, manifest)


def test_local_export_requires_every_point_and_the_release_banner(raw_job) -> None:
    raw, spec, manifest = raw_job
    (raw / "sdevice.stdout.log").write_text("no banner")
    with pytest.raises(NativeExportError, match="release"):
        build_export(raw, spec, manifest)
    (raw / "sdevice.stdout.log").write_text("*** Version O-2018.06-SP2 ***")
    (raw / "point_0001_des.tdr").unlink()
    with pytest.raises(NativeExportError, match="missing native output"):
        build_export(raw, spec, manifest)


def test_a_descriptive_experiment_name_with_spaces_and_punctuation_still_compiles(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    spec = ExperimentSpec.model_validate(
        {**pn_spec().model_dump(mode="json"), "name": "MOS Capacitor \u2014 n-type Si, 300 K"}
    )
    job = SentaurusAdapter.from_defaults("sde").compile(spec, tmp_path / "job")
    deck = (job.entrypoint.parent / "sdevice.cmd").read_text(encoding="utf-8")
    assert "MOS Capacitor" not in deck  # a label, never part of the native input

def test_escalation_decks_exist_and_a_stalled_run_is_disclosed(tmp_path, monkeypatch) -> None:
    from tcad_agent.adapters.sentaurus.native_export import escalation_notes

    monkeypatch.setenv("TCAD_SENTAURUS_VERSION", VERSION)
    job = SentaurusAdapter.from_defaults("sde").compile(pn_spec(), tmp_path / "job")
    root = job.entrypoint.parent
    first = (root / "sdevice.r1.cmd").read_text(encoding="utf-8")
    second = (root / "sdevice.r2.cmd").read_text(encoding="utf-8")
    third = (root / "sdevice.r3.cmd").read_text(encoding="utf-8")
    base = (root / "sdevice.cmd").read_text(encoding="utf-8")
    assert "SubMethod=ILS" in first and "SubMethod=ILS" not in base
    assert "Iterations=300" in first and "Digits=8" in first
    assert "-DoZero" in second and "-DoZero" not in first and "Digits=8" in second
    assert "Digits=6" in third and "SubMethod=ILS" in third and "-DoZero" in third
    # Same physics: only the numerical Math block differs between the decks.
    strip = lambda text: text.split("Math {")[0]  # noqa: E731
    assert strip(base) == strip(first) == strip(second) == strip(third)

    assert escalation_notes("KRONIG numerics level 0 stalled:") == []
    note = escalation_notes("KRONIG numerics level 1 stalled: 0")[0]
    assert "iterative linear solver" in note and "level 1" in note
    assert "without re-solving" in escalation_notes("KRONIG numerics level 2 stalled: 0 1")[0]
    assert "6-digit" in escalation_notes("KRONIG numerics level 3 stalled: 0 1 2")[0]
    assert escalation_notes("no marker") == []