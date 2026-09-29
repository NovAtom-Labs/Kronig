from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_user_parameterized_generic_dielectric_matches_parallel_plate_reference(
    tmp_path: Path,
) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "registered generic dielectric",
            "dimension": 1,
            "regions": [
                {
                    "id": "film",
                    "material": "generic_dielectric",
                    "relative_permittivity": 7.5,
                    "x0": "0 nm",
                    "x1": "20 nm",
                    "mesh_spacing": "1 nm",
                }
            ],
            "profiles": [],
            "contacts": [
                {
                    "id": "control",
                    "location": "x_min",
                    "kind": "ideal_gate",
                    "area": "100 um^2",
                },
                {"id": "reference", "location": "x_max", "kind": "ideal_gate"},
            ],
            "physics": {"equations": ["poisson"]},
            "study": {
                "kind": "ac",
                "contact": "control",
                "frequency": "10 kHz",
                "amplitude": "5 mV",
            },
            "observables": ["potential", "terminal_charge"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "generic-dielectric"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    expected = 7.5 * 8.85e-12 / 20e-9
    assert result.datasets["ac_capacitance__control"].values[0] == pytest.approx(
        expected, rel=0.02
    )
    assert result.datasets["absolute_ac_capacitance__control"].values[0] == pytest.approx(
        expected * 1e-10, rel=0.02
    )


def test_generic_dielectric_refuses_missing_researcher_permittivity() -> None:
    with pytest.raises(ValueError, match="relative_permittivity"):
        ExperimentSpec.model_validate(
            {
                "schema_version": "1.0",
                "name": "incomplete dielectric",
                "dimension": 1,
                "regions": [
                    {
                        "id": "film",
                        "material": "generic_dielectric",
                        "x0": "0 nm",
                        "x1": "10 nm",
                    }
                ],
                "profiles": [],
                "contacts": [
                    {"id": "left", "location": "x_min", "kind": "ideal_gate"},
                    {"id": "right", "location": "x_max", "kind": "ideal_gate"},
                ],
                "physics": {"equations": ["poisson"]},
                "study": {"kind": "equilibrium"},
                "observables": ["potential"],
            }
        )


@pytest.mark.integration
def test_uncontacted_endpoint_is_an_insulating_zero_flux_boundary(tmp_path: Path) -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "single-contact dielectric boundary",
            "dimension": 1,
            "regions": [
                {
                    "id": "film",
                    "material": "generic_dielectric",
                    "relative_permittivity": 5.0,
                    "x0": "0 nm",
                    "x1": "20 nm",
                    "mesh_spacing": "1 nm",
                }
            ],
            "profiles": [],
            "contacts": [
                {
                    "id": "reference",
                    "location": "x_min",
                    "kind": "ideal_gate",
                    "voltage_offset": "0 V",
                },
                {
                    "id": "insulated",
                    "location": "x_max",
                    "kind": "insulating",
                },
            ],
            "physics": {"equations": ["poisson"]},
            "study": {"kind": "equilibrium"},
            "observables": ["potential", "electric_field"],
        }
    )
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "insulating-boundary"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert max(abs(value) for value in result.datasets["electric_field"].values) < 1e-8
