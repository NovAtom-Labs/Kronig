import math

import pytest

from tcad_agent.adapters.devsim.models.profiles import evaluate_profile
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
        "profiles": [],
        "contacts": [
            {"id": "left", "location": "x_min", "kind": "ohmic"},
            {"id": "right", "location": "x_max", "kind": "ohmic"},
        ],
        "physics": {
            "equations": ["poisson"],
            "models": ["boltzmann"],
            "temperature_k": 300.0,
        },
        "study": {"kind": "equilibrium"},
        "observables": ["potential"],
    }


@pytest.mark.parametrize(
    ("profile", "positions", "expected"),
    [
        (
            {
                "kind": "linear",
                "region": "bulk",
                "species": "donor",
                "start_value_cm3": 1.0,
                "end_value_cm3": 3.0,
            },
            (0.0, 0.5e-4, 1e-4),
            (1.0, 2.0, 3.0),
        ),
        (
            {
                "kind": "gaussian",
                "region": "bulk",
                "species": "donor",
                "peak_cm3": 10.0,
                "center_cm": 0.5e-4,
                "standard_deviation_cm": 0.1e-4,
            },
            (0.5e-4,),
            (10.0,),
        ),
        (
            {
                "kind": "tabulated",
                "region": "bulk",
                "species": "acceptor",
                "positions_cm": (0.0, 1e-4),
                "values_cm3": (1.0, 3.0),
                "interpolation": "linear",
            },
            (0.25e-4,),
            (1.5,),
        ),
    ],
)
def test_profile_models_are_evaluated_without_user_expressions(
    profile: dict, positions: tuple[float, ...], expected: tuple[float, ...]
) -> None:
    payload = minimal_payload()
    payload["profiles"] = [profile]
    typed = DevsimPayload.model_validate(payload)
    region = typed.regions[0]

    assert tuple(
        evaluate_profile(typed.profiles[0], region, x) for x in positions
    ) == pytest.approx(expected)


def test_error_function_orientation_is_explicit() -> None:
    payload = minimal_payload()
    payload["profiles"] = [
        {
            "kind": "error_function",
            "region": "bulk",
            "species": "acceptor",
            "surface_value_cm3": 1e18,
            "junction_position_cm": 0.5e-4,
            "characteristic_length_cm": 0.1e-4,
            "orientation": "decreasing_x",
        }
    ]
    profile = DevsimPayload.model_validate(payload).profiles[0]
    region = DevsimPayload.model_validate(payload).regions[0]

    assert evaluate_profile(profile, region, 0.0) > evaluate_profile(profile, region, 1e-4)
    assert math.isfinite(evaluate_profile(profile, region, 0.5e-4))
