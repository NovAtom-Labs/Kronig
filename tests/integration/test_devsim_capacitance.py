from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_terminal_charge_sweep_produces_generic_quasistatic_capacitance(tmp_path: Path) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "charge-voltage-stack",
            "dimension": 1,
            "regions": [
                {
                    "id": "layer_a",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "10 nm",
                    "mesh_spacing": "0.5 nm",
                },
                {
                    "id": "layer_b",
                    "material": "silicon",
                    "x0": "10 nm",
                    "x1": "1.01 um",
                    "mesh_spacing": "10 nm",
                },
            ],
            "interfaces": [{"id": "ab", "left_region": "layer_a", "right_region": "layer_b"}],
            "profiles": [
                {
                    "kind": "constant",
                    "region": "layer_b",
                    "species": "acceptor",
                    "value": "1e16 cm^-3",
                }
            ],
            "contacts": [
                {"id": "control", "location": "x_min", "kind": "ideal_gate"},
                {"id": "reference", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {"equations": ["poisson"], "models": ["boltzmann"]},
            "study": {
                "kind": "dc",
                "contact": "control",
                "start": "-1 V",
                "stop": "1 V",
                "step": "0.5 V",
                "strategy": "adaptive",
                "minimum_step": "10 mV",
                "maximum_retries": 10,
            },
            "observables": [
                "terminal_charge",
                "potential",
                "electric_field",
                "electron_density",
                "hole_density",
            ],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "charge-voltage"), RunBudget(seconds=120)
    )

    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.datasets["terminal_charge__control"].unit == "C/m^2"
    assert result.datasets["capacitance__control"].unit == "F/m^2"
    assert len(result.datasets["capacitance__control"].values) == 5
    assert min(result.datasets["electron_density"].values) > 0
    assert min(result.datasets["hole_density"].values) > 0
    assert result.datasets["electron_density"].shape == result.datasets["hole_density"].shape
    assert result.metadata["native_model_names"]["electron_density"] == "IntrinsicElectrons"
    assert result.metadata["native_model_names"]["hole_density"] == "IntrinsicHoles"


@pytest.mark.integration
def test_validation_evidence_is_retained_without_requested_spatial_outputs(tmp_path):
    from tcad_agent.validation.engine import ValidationEngine

    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "arbitrary-control-layer",
            "dimension": 1,
            "regions": [
                {
                    "id": "film",
                    "material": "silicon_dioxide",
                    "x0": "0 nm",
                    "x1": "12 nm",
                    "mesh_spacing": "1 nm",
                },
                {
                    "id": "bulk",
                    "material": "silicon",
                    "x0": "12 nm",
                    "x1": "512 nm",
                    "mesh_spacing": "5 nm",
                },
            ],
            "interfaces": [{"id": "join", "left_region": "film", "right_region": "bulk"}],
            "profiles": [
                {"kind": "constant", "region": "bulk", "species": "acceptor", "value": "2e16 cm^-3"}
            ],
            "contacts": [
                {
                    "id": "control",
                    "location": "x_min",
                    "kind": "metal_work_function",
                    "work_function": "4.2 eV",
                },
                {"id": "reference", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson", "electron_continuity", "hole_continuity"],
                "models": ["fermi", "constant_mobility", "srh"],
                "temperature": "300 K",
            },
            "study": {
                "kind": "dc",
                "contact": "control",
                "start": "-2 V",
                "stop": "2 V",
                "step": "1 V",
            },
            "observables": ["terminal_charge"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "native"), RunBudget(seconds=120)
    )
    result = adapter.normalize(native)
    assert result.status == "completed", native.stderr_path.read_text()
    assert {
        "potential",
        "electric_field",
        "electrostatic_flux",
        "charge_density",
        "electron_density",
        "hole_density",
        "effective_density_conduction",
        "effective_density_valence",
    } <= result.datasets.keys()
    report = ValidationEngine().validate(result, spec=spec)
    for name in (
        "electric-field-potential-gradient",
        "poisson-residual-consistency",
        "contact-charge-balance",
    ):
        assert report.checks_by_id[name].status == "passed", report.checks_by_id[name]
