from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import Contact, ExperimentSpec


def test_direct_metal_semiconductor_transport_remains_a_visible_research_gate(
    valid_spec: ExperimentSpec, tmp_path: Path
) -> None:
    contact = Contact.model_validate(
        {
            "id": valid_spec.contacts[0].id,
            "location": valid_spec.contacts[0].location,
            "kind": "metal_work_function",
            "work_function": "4.10 eV",
        }
    )
    requested = valid_spec.model_copy(
        update={"contacts": (contact, *valid_spec.contacts[1:])}
    )
    workspace = tmp_path / "schottky-gated"

    with pytest.raises(CapabilityError, match="Schottky"):
        DevsimAdapter.from_defaults().compile(requested, workspace)

    assert not workspace.exists()
