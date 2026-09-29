import json

import pytest
from pydantic import ValidationError

from tcad_agent.adapters.devsim.payload import DevsimPayload


def minimal_payload() -> dict:
    return {
        "schema_version": "2.0",
        "experiment_name": "generic-stack",
        "regions": [
            {
                "id": "bulk",
                "material": "silicon",
                "x0_cm": 0.0,
                "x1_cm": 1e-4,
                "mesh_spacing_cm": 2e-6,
            }
        ],
        "interfaces": [],
        "profiles": [
            {
                "kind": "linear",
                "region": "bulk",
                "species": "acceptor",
                "start_value_cm3": 1e15,
                "end_value_cm3": 1e17,
            }
        ],
        "contacts": [
            {"id": "left", "location": "x_min", "kind": "ohmic"},
            {"id": "right", "location": "x_max", "kind": "ohmic"},
        ],
        "physics": {
            "equations": ["poisson", "electron_continuity", "hole_continuity"],
            "models": ["boltzmann", "constant_mobility", "srh"],
            "temperature_k": 300.0,
        },
        "study": {"kind": "equilibrium"},
        "observables": ["potential"],
    }


def test_payload_contains_only_typed_data_and_round_trips() -> None:
    payload = DevsimPayload.model_validate(minimal_payload())
    encoded = payload.model_dump_json()

    assert DevsimPayload.model_validate_json(encoded) == payload
    assert "equation=" not in encoded
    assert "__import__" not in encoded


def test_payload_rejects_expression_and_path_injection() -> None:
    payload = minimal_payload()
    payload["profiles"][0]["expression"] = "__import__('os').system('id')"

    with pytest.raises(ValidationError, match="expression"):
        DevsimPayload.model_validate(payload)


def test_payload_has_no_free_form_executable_string_fields() -> None:
    schema = json.dumps(DevsimPayload.model_json_schema(), sort_keys=True)

    assert '"expression"' not in schema
    assert '"entrypoint"' not in schema
    assert '"path"' not in schema
