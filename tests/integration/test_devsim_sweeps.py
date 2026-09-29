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
def test_exact_bidirectional_bias_order_is_preserved(tmp_path: Path) -> None:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    payload["study"] = {
        "kind": "dc_points",
        "contact": "anode",
        "values": ["0 V", "2 V", "0 V", "-2 V"],
        "strategy": "adaptive",
        "minimum_step": "1 mV",
        "maximum_retries": 20,
    }
    spec = ExperimentSpec.model_validate(payload)
    adapter = DevsimAdapter.from_defaults()
    native = LocalRunner(resolve_devsim_python(ROOT)).run(
        adapter.compile(spec, tmp_path / "bidirectional"), RunBudget(seconds=120)
    )

    result = adapter.normalize(native)

    assert result.status == "completed", native.stderr_path.read_text()
    assert [point.bias_v for point in result.bias_points] == [0.0, 2.0, 0.0, -2.0]
    assert all(point.converged for point in result.bias_points)
    potential = result.datasets["potential"]
    assert potential.axes[0] == "bias"
    assert potential.shape[0] == 4
    assert potential.validity == (True,) * len(potential.values)
    assert len(potential.values) == potential.shape[0] * potential.shape[1]
    assert potential.values[: potential.shape[1]] != potential.values[-potential.shape[1] :]
