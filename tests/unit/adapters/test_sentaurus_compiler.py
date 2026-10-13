import hashlib
import json
from pathlib import Path

import pytest

from tcad_agent.adapters.sentaurus.compiler import (
    SentaurusAdapter,
    SentaurusCompilerSafetyError,
)
from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import ExperimentSpec


@pytest.mark.parametrize("precision", ["standard", "extended"])
def test_explicit_unmapped_numerical_precision_is_not_silently_ignored(tmp_path, precision):
    spec = equilibrium_spec()
    spec = spec.model_copy(
        update={"solver": spec.solver.model_copy(update={"precision": precision})}
    )
    with pytest.raises(CapabilityError, match="precision"):
        SentaurusAdapter.from_defaults().compile(spec, tmp_path / "unmapped-precision")


def equilibrium_spec() -> ExperimentSpec:
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "al-pn-al-equilibrium",
            "dimension": 1,
            "regions": [
                {
                    "id": "p_region",
                    "material": "silicon",
                    "x0": "0 um",
                    "x1": "1 um",
                    "mesh_spacing": "0.02 um",
                },
                {
                    "id": "n_region",
                    "material": "silicon",
                    "x0": "1 um",
                    "x1": "2 um",
                    "mesh_spacing": "0.02 um",
                },
            ],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "p_region",
                    "species": "acceptor",
                    "value": "1e17 cm^-3",
                },
                {
                    "kind": "constant",
                    "region": "n_region",
                    "species": "donor",
                    "value": "1e17 cm^-3",
                },
            ],
            "contacts": [
                {
                    "id": "anode",
                    "location": "x_min",
                    "kind": "metal_work_function",
                    "work_function": "4.10 eV",
                },
                {
                    "id": "cathode",
                    "location": "x_max",
                    "kind": "metal_work_function",
                    "work_function": "4.10 eV",
                },
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": [
                    "fermi",
                    "constant_mobility",
                    "srh",
                    "auger",
                    "band_gap_narrowing",
                ],
                "temperature": "300 K",
            },
            "study": {"kind": "equilibrium"},
            "observables": [
                "terminal_current",
                "terminal_charge",
                "potential",
                "electric_field",
                "electron_density",
                "hole_density",
                "charge_density",
                "conduction_band",
                "valence_band",
                "fermi_level",
                "electron_current_density",
                "hole_current_density",
                "electron_mobility",
                "hole_mobility",
                "recombination_rate",
            ],
        }
    )


def test_compile_equilibrium_matches_reviewed_fixture(tmp_path: Path) -> None:
    job = SentaurusAdapter.from_defaults().compile(equilibrium_spec(), tmp_path / "job")

    generated = (tmp_path / "job" / "sdevice.cmd").read_text()
    expected = Path("tests/fixtures/sentaurus/equilibrium_1d/expected_sdevice.cmd").read_text()
    assert generated == expected
    assert job.entrypoint.name == "sdevice.cmd"
    assert job.arguments == ()
    assert {path.name for path in job.input_files} == {
        "experiment.json",
        "job-manifest.json",
        "sdevice.cmd",
    }

    manifest = json.loads((tmp_path / "job" / "job-manifest.json").read_text())
    assert manifest["expected_outputs"] == [
        "sdevice.log",
        "sdevice.plt",
        "sdevice.tdr",
    ]
    assert manifest["inputs"]["sdevice.cmd"] == hashlib.sha256(generated.encode()).hexdigest()
    assert manifest["source_map"]["contacts[0]"]["file"] == "sdevice.cmd"


def test_compile_is_byte_deterministic(tmp_path: Path) -> None:
    adapter = SentaurusAdapter.from_defaults()
    first = adapter.compile(equilibrium_spec(), tmp_path / "first")
    second = adapter.compile(equilibrium_spec(), tmp_path / "second")

    first_files = {path.name: path.read_bytes() for path in first.input_files}
    second_files = {path.name: path.read_bytes() for path in second.input_files}
    assert first_files == second_files
    assert first.input_digest == second.input_digest
    assert first.runtime_digest == second.runtime_digest


@pytest.mark.parametrize("unsafe_name", ["bad\nname", "../../escape", "bad;name", "/tmp/x"])
def test_unsafe_identifier_is_rejected(tmp_path: Path, unsafe_name: str) -> None:
    spec = equilibrium_spec().model_copy(update={"name": unsafe_name})
    with pytest.raises(SentaurusCompilerSafetyError):
        SentaurusAdapter.from_defaults().compile(spec, tmp_path / "job")


def test_unsupported_model_is_refused(tmp_path: Path) -> None:
    spec = equilibrium_spec()
    physics = spec.physics.model_copy(update={"models": (*spec.physics.models, "hydrodynamic")})
    spec = spec.model_copy(update={"physics": physics})
    with pytest.raises(CapabilityError, match="hydrodynamic"):
        SentaurusAdapter.from_defaults().compile(spec, tmp_path / "job")


def test_unsupported_observable_is_refused(tmp_path: Path) -> None:
    manifest = CapabilityManifest.from_backend("sentaurus")
    manifest = manifest.model_copy(
        update={"observables": tuple(item for item in manifest.observables if item != "potential")}
    )
    with pytest.raises(CapabilityError, match="potential"):
        SentaurusAdapter(manifest).compile(equilibrium_spec(), tmp_path / "job")


def test_metal_work_function_contacts_are_explicit(tmp_path: Path) -> None:
    SentaurusAdapter.from_defaults().compile(equilibrium_spec(), tmp_path / "job")
    deck = (tmp_path / "job" / "sdevice.cmd").read_text()
    assert '{ Name="anode" Voltage=0 WorkFunction=4.1 }' in deck
    assert '{ Name="cathode" Voltage=0 WorkFunction=4.1 }' in deck
    assert "Barrier" not in deck
