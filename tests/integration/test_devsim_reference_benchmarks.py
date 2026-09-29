from pathlib import Path

import pytest
import yaml

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.domain.models import ExperimentSpec
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
