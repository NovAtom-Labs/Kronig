"""Offline bundle tests. The opaque mesh bytes are not a native benchmark."""

import json

import pytest
from test_sentaurus_compiler import equilibrium_spec

from tcad_agent.adapters.sentaurus import runtime
from tcad_agent.adapters.sentaurus.compiler import SentaurusAdapter
from tcad_agent.runners.models import RunBudget
from tcad_agent.runners.ssh import SSHSentaurusRunner


def compiled(tmp_path):
    return SentaurusAdapter.from_defaults().compile(equilibrium_spec(), tmp_path / "candidate")


def bound(tmp_path):
    job = compiled(tmp_path)
    mesh = tmp_path / "synthetic.tdr"
    mesh.write_bytes(b"synthetic test artifact, not a Sentaurus mesh")
    return runtime.bind_mesh(
        job,
        mesh,
        tmp_path / "prepared",
        simulator_version="synthetic-release",
        review_reference="offline-test-only",
    )


def test_binding_does_not_mutate_original_and_hashes_mesh(tmp_path):
    job = bound(tmp_path)
    runtime.validate_bundle(job)
    data = json.loads((job.entrypoint.parent / "job-manifest.json").read_text())
    assert "device.tdr" in data["inputs"]
    assert data["native_review"]["simulator_version"] == "synthetic-release"
    assert not (tmp_path / "candidate" / "device.tdr").exists()
    assert job.input_digest != compiled(tmp_path / "another").input_digest


@pytest.mark.parametrize(
    "filename", ["sdevice.cmd", "device.tdr", "experiment.json", "job-manifest.json"]
)
def test_tampering_is_rejected(tmp_path, filename):
    job = bound(tmp_path)
    with (job.entrypoint.parent / filename).open("ab") as stream:
        stream.write(b"\ntampered")
    with pytest.raises(ValueError):
        runtime.validate_bundle(job)


def test_missing_mesh_blocks_ssh_before_connection(tmp_path, monkeypatch):
    job = compiled(tmp_path)
    runner = SSHSentaurusRunner(host="must-not-connect.invalid", user="test")

    def forbidden():
        pytest.fail("an incomplete generated bundle reached SSH")

    monkeypatch.setattr(runner, "_connect", forbidden)
    result = runner.run(job, RunBudget(seconds=1))
    assert result.status == "execution_failed"
    assert "mesh" in result.error.lower()


def test_symlink_input_is_rejected(tmp_path):
    job = bound(tmp_path)
    mesh = job.entrypoint.parent / "device.tdr"
    outside = tmp_path / "outside.tdr"
    outside.write_bytes(mesh.read_bytes())
    mesh.unlink()
    mesh.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        runtime.validate_bundle(job)


def test_review_release_mismatch_is_rejected(tmp_path):
    job = bound(tmp_path)
    with pytest.raises(ValueError, match="release"):
        runtime.validate_bundle(job, simulator_version="different-release")


def test_native_bias_includes_contact_offset(tmp_path):
    data = equilibrium_spec().model_dump(mode="json")
    data["contacts"][0]["voltage_offset"] = "0.2 V"
    data["observables"].remove("fermi_level")
    data["study"] = {"kind": "dc_points", "contact": "anode", "values": ["0.3 V"]}
    spec = type(equilibrium_spec()).model_validate(data)
    job = SentaurusAdapter.from_defaults().compile(spec, tmp_path / "job")
    assert 'Goal { Name="anode" Voltage=0.5 }' in job.entrypoint.read_text()


@pytest.mark.parametrize(
    "field, value",
    [
        ("solver", {"relative_error": 3e-5}),
        ("solver", {"carrier_absolute_error": 17}),
    ],
)
def test_unmapped_numerics_are_not_dropped(tmp_path, field, value):
    data = equilibrium_spec().model_dump(mode="json")
    data[field].update(value)
    from tcad_agent.adapters.sentaurus.compiler import SentaurusCompilerSafetyError

    with pytest.raises(SentaurusCompilerSafetyError):
        SentaurusAdapter.from_defaults().compile(
            type(equilibrium_spec()).model_validate(data), tmp_path / "job"
        )
