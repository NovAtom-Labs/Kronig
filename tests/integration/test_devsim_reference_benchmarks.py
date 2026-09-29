from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.results.derive import DerivationRegistry
from tcad_agent.runners.local import LocalRunner
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[2]


@pytest.mark.integration
def test_abrupt_equilibrium_reference_passes_canonical_physics_checks(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "equilibrium-reference"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    report = ValidationEngine().validate(result, spec=spec)

    assert result.status == "completed", native.stderr_path.read_text()
    assert report.checks_by_id["electric-field-potential-gradient"].status == "passed"
    assert report.checks_by_id["built-in-potential-reference"].status == "passed"
    assert report.checks_by_id["equilibrium-terminal-current"].status == "passed"
    assert report.overall == "passed"


@pytest.mark.integration
def test_equilibrium_accepts_hyphenated_contact_identifiers(tmp_path: Path) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    payload["contacts"][0]["id"] = "p-contact"
    payload["contacts"][1]["id"] = "n-contact"
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "hyphenated-contact-identifiers"),
        RunBudget(seconds=120),
    )
    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert result.terminals == ("p-contact", "n-contact")
    assert set(result.bias_points[0].terminal_currents_a_per_m2) == {
        "p-contact",
        "n-contact",
    }


@pytest.mark.integration
def test_abrupt_equilibrium_derived_metrics_are_stable_under_mesh_refinement(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(
        (ROOT / "examples" / "al-pn-al-equilibrium-devsim.yaml").read_text()
    )
    payload["observables"] = ["potential", "electric_field"]
    adapter = DevsimAdapter.from_defaults()
    results = []
    for label, spacing in (("coarse", "20 nm"), ("refined", "10 nm")):
        candidate = yaml.safe_load(yaml.safe_dump(payload))
        for region in candidate["regions"]:
            region["mesh_spacing"] = spacing
        spec = ExperimentSpec.model_validate(candidate)
        native = LocalRunner(resolve_devsim_python(ROOT)).run(
            adapter.compile(spec, tmp_path / label), RunBudget(seconds=120)
        )
        result = adapter.normalize(native)
        assert result.status == "completed", native.stderr_path.read_text()
        results.append(result)

    registry = DerivationRegistry.default()
    metrics = []
    for result in results:
        built_in = registry.scalar(
            "built_in_potential", result.datasets["potential"], result.axes
        ).value
        peak = registry.scalar(
            "peak_magnitude", result.datasets["electric_field"], result.axes
        ).value
        metrics.append((built_in, peak))

    assert metrics[0][0] == pytest.approx(metrics[1][0], rel=0.01)
    assert metrics[0][1] == pytest.approx(metrics[1][1], rel=0.08)


@pytest.mark.integration
def test_terminal_current_is_stable_under_bias_step_refinement(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    payload["observables"] = ["terminal_current"]
    adapter = DevsimAdapter.from_defaults()
    currents = []
    for label, step in (("coarse-bias", "0.1 V"), ("refined-bias", "0.05 V")):
        candidate = yaml.safe_load(yaml.safe_dump(payload))
        candidate["study"].update({"start": "0 V", "stop": "0.2 V", "step": step})
        spec = ExperimentSpec.model_validate(candidate)
        native = LocalRunner(resolve_devsim_python(ROOT)).run(
            adapter.compile(spec, tmp_path / label), RunBudget(seconds=120)
        )
        result = adapter.normalize(native)
        assert result.status == "completed", native.stderr_path.read_text()
        currents.append(result.bias_points[-1].terminal_currents_a_per_m2["anode"])

    scale = max(abs(currents[1]), 1e-20)
    assert abs(currents[0] - currents[1]) / scale < 0.01
