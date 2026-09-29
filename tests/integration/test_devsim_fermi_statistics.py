from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import ExperimentSpec


def test_fermi_statistics_remain_a_visible_research_gate(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    physics = valid_spec.physics.model_copy(
        update={"models": (*valid_spec.physics.models, "fermi")}
    )
    requested = valid_spec.model_copy(update={"physics": physics})
    workspace = tmp_path / "fermi-gated"

    with pytest.raises(CapabilityError, match="fermi"):
        DevsimAdapter.from_defaults().compile(requested, workspace)

    assert not workspace.exists()
