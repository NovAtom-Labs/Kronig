import math
from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_bands_quasi_fermi_bgn_and_auger_are_extracted_from_solved_state(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text())
    payload["physics"]["models"].extend(["auger", "slotboom_bgn"])
    payload["observables"].extend(
        [
            "conduction_band",
            "valence_band",
            "intrinsic_energy",
            "fermi_level",
            "electron_quasi_fermi_level",
            "hole_quasi_fermi_level",
            "electron_affinity",
            "band_gap",
            "band_gap_narrowing",
            "effective_intrinsic_carrier_concentration",
            "electron_generation_rate",
            "hole_generation_rate",
            "srh_recombination_rate",
            "auger_recombination_rate",
            "total_recombination_rate",
        ]
    )
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "advanced-physics"),
        RunBudget(seconds=120),
    )

    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.metadata["parameter_set_id"] == "novatom.silicon.baseline.2026-09-29.v1"
    assert result.metadata["parameter_sources"]["band_gap_ev"]["version"] == (
        "2026-09-29.v1"
    )
    assert result.metadata["parameter_sources"]["band_gap_ev"]["source"]
    assert result.metadata["solver_configuration"]["maximum_iterations"] == 80
    assert result.metadata["native_model_names"]["conduction_band"] == (
        "ConductionBandEnergy"
    )
    assert {region["id"] for region in result.metadata["regions"]} == {
        region.id for region in spec.regions
    }
    for name in (
        "conduction_band",
        "valence_band",
        "intrinsic_energy",
        "fermi_level",
        "electron_quasi_fermi_level",
        "hole_quasi_fermi_level",
        "electron_affinity",
        "band_gap",
        "band_gap_narrowing",
        "effective_intrinsic_carrier_concentration",
        "electron_generation_rate",
        "hole_generation_rate",
        "srh_recombination_rate",
        "auger_recombination_rate",
        "total_recombination_rate",
    ):
        assert name in result.datasets
    conduction = result.datasets["conduction_band"].values
    valence = result.datasets["valence_band"].values
    assert all(ec > ev for ec, ev in zip(conduction, valence, strict=True))
    electron_affinity = result.datasets["electron_affinity"].values
    assert electron_affinity == pytest.approx((4.05,) * len(electron_affinity))
    assert min(result.datasets["band_gap"].values) > 1.0
    assert min(result.datasets["band_gap_narrowing"].values) >= 0.0
    assert min(result.datasets["effective_intrinsic_carrier_concentration"].values) > 0.0
    assert result.datasets["electron_generation_rate"].values == pytest.approx(
        result.datasets["hole_generation_rate"].values
    )
    assert max(abs(value) for value in result.datasets["fermi_level"].values) < 1e-8
    assert all(
        math.isfinite(value)
        for value in result.datasets["auger_recombination_rate"].values
    )


@pytest.mark.integration
def test_terminal_carrier_currents_and_total_current_density_are_canonical(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    payload["study"] = {
        "kind": "dc_points",
        "contact": "cathode",
        "values": ["0 V", "0.1 V"],
    }
    payload["observables"].extend(
        [
            "total_current_density",
            "terminal_electron_current",
            "terminal_hole_current",
        ]
    )
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "carrier-current-components"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert "total_current_density" in result.datasets
    for terminal in result.terminals:
        electron = result.datasets[f"terminal_electron_current__{terminal}"]
        hole = result.datasets[f"terminal_hole_current__{terminal}"]
        total = result.datasets[f"terminal_current__{terminal}"]
        assert tuple(
            e + h for e, h in zip(electron.values, hole.values, strict=True)
        ) == pytest.approx(total.values)


@pytest.mark.integration
def test_klaassen_mobility_is_doping_dependent_and_extracted(tmp_path: Path) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    payload["physics"]["models"] = [
        model
        for model in payload["physics"]["models"]
        if model != "constant_mobility"
    ]
    payload["physics"]["models"].append("klaassen_mobility")
    payload["observables"].extend(["electron_mobility", "hole_mobility"])
    payload["profiles"][0]["value"] = "1e15 cm^-3"
    payload["profiles"][1]["value"] = "1e18 cm^-3"
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "klaassen-mobility"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    electron = result.datasets["electron_mobility"].values
    hole = result.datasets["hole_mobility"].values
    assert min(electron) > 0
    assert min(hole) > 0
    assert max(electron) / min(electron) > 1.2
    assert max(hole) / min(hole) > 1.2
