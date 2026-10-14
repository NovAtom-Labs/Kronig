import json
import subprocess
import sys

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import ExperimentSpec, Observable
from tcad_agent.domain.profiles import GaussianProfile


def test_compiled_workspace_carries_its_statistical_kernel_without_project_install(
    valid_spec, tmp_path
):
    job = DevsimAdapter.from_defaults().compile(valid_spec, tmp_path / "standalone")
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys,runpy;sys.path.insert(0,sys.argv[1]);"
                "m=runpy.run_path(sys.argv[1]+'/run_devsim.py');"
                "print(m['_fermi_ratio'](0))"
            ),
            str(job.entrypoint.parent),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert float(completed.stdout) == pytest.approx(0.765162841, rel=0.001)
    assert "devsim_statistics.py" in {path.name for path in job.input_files}


def test_compiler_is_deterministic_and_name_agnostic(valid_spec: ExperimentSpec, tmp_path) -> None:
    adapter = DevsimAdapter.from_defaults()
    first = adapter.compile(valid_spec, tmp_path / "first")
    renamed = valid_spec.model_copy(update={"name": "arbitrary-research-structure"})
    second = adapter.compile(renamed, tmp_path / "second")
    assert first.runtime_digest == second.runtime_digest
    assert first.input_digest != second.input_digest
    assert first.entrypoint.name == "run_devsim.py"
    compiled_input = json.loads(first.input_files[0].read_text())
    assert compiled_input["sign_convention"]["terminal_current"] == ("positive_into_device")
    assert compiled_input["solver"] == {
        "precision": "extended",
        "requested_precision": "backend_default",
        "maximum_iterations": 80,
        "relative_error": 1e-06,
        "electrostatic_absolute_error": 1.0,
        "carrier_absolute_error": 1e10,
        "transient_initial_relative_error": 1e-08,
        "transient_step_relative_error": 0.0001,
    }


def test_compiler_rejects_without_writing_files(unsupported_spec: ExperimentSpec, tmp_path) -> None:
    workspace = tmp_path / "rejected"
    with pytest.raises(CapabilityError):
        DevsimAdapter.from_defaults().compile(unsupported_spec, workspace)
    assert not workspace.exists()


def test_compiler_accepts_reviewed_band_observable(valid_spec: ExperimentSpec, tmp_path) -> None:
    workspace = tmp_path / "band-observable"
    spec = valid_spec.model_copy(
        update={"observables": (*valid_spec.observables, Observable.CONDUCTION_BAND)}
    )

    compiled = DevsimAdapter.from_defaults().compile(spec, workspace)

    assert compiled.entrypoint.exists()


def test_compiler_adds_profile_landmark_mesh_anchors_without_device_names(
    valid_spec: ExperimentSpec, tmp_path
) -> None:
    first_region = valid_spec.regions[0].model_copy(
        update={
            "mesh_spacing": valid_spec.regions[0].x1.model_validate("20 nm"),
            "minimum_mesh_spacing": valid_spec.regions[0].x1.model_validate("2 nm"),
            "maximum_mesh_spacing": valid_spec.regions[0].x1.model_validate("40 nm"),
        }
    )
    profile = GaussianProfile.model_validate(
        {
            "kind": "gaussian",
            "region": first_region.id,
            "species": "acceptor",
            "peak": "1e18 cm^-3",
            "center": "0.25 um",
            "standard_deviation": "20 nm",
        }
    )
    spec = valid_spec.model_copy(
        update={
            "name": "profile-landmark-study",
            "regions": (first_region, *valid_spec.regions[1:]),
            "profiles": (profile, *valid_spec.profiles[1:]),
        }
    )

    job = DevsimAdapter.from_defaults().compile(spec, tmp_path / "compiled")
    payload = json.loads(job.input_files[0].read_text())

    automatic = [
        anchor
        for anchor in payload["mesh_anchors"]
        if anchor.get("source") == "profile:gaussian:center"
    ]
    assert len(automatic) == 1
    assert automatic[0]["position_cm"] == pytest.approx(2.5e-05)
    assert automatic[0]["spacing_cm"] == pytest.approx(5e-07)
