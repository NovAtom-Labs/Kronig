import pytest
from pydantic import TypeAdapter, ValidationError

from tcad_agent.domain.profiles import Profile1D

PROFILE = TypeAdapter(Profile1D)


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        (
            {
                "kind": "constant",
                "region": "bulk",
                "species": "acceptor",
                "value": "1e16 cm^-3",
            },
            "constant",
        ),
        (
            {
                "kind": "linear",
                "region": "bulk",
                "species": "donor",
                "start_value": "1e15 cm^-3",
                "end_value": "1e17 cm^-3",
            },
            "linear",
        ),
        (
            {
                "kind": "gaussian",
                "region": "bulk",
                "species": "donor",
                "peak": "1e19 cm^-3",
                "center": "0.2 um",
                "standard_deviation": "30 nm",
            },
            "gaussian",
        ),
        (
            {
                "kind": "error_function",
                "region": "bulk",
                "species": "acceptor",
                "surface_value": "1e18 cm^-3",
                "junction_position": "0.3 um",
                "characteristic_length": "40 nm",
                "orientation": "decreasing_x",
            },
            "error_function",
        ),
        (
            {
                "kind": "tabulated",
                "region": "bulk",
                "species": "donor",
                "positions": ["0 um", "0.5 um", "1 um"],
                "values": ["1e15 cm^-3", "2e15 cm^-3", "3e15 cm^-3"],
                "interpolation": "linear",
            },
            "tabulated",
        ),
    ],
)
def test_profiles_are_typed_and_unit_checked(payload: dict, kind: str) -> None:
    assert PROFILE.validate_python(payload).kind == kind


def test_gaussian_rejects_nonpositive_width() -> None:
    with pytest.raises(ValidationError, match="positive"):
        PROFILE.validate_python(
            {
                "kind": "gaussian",
                "region": "bulk",
                "species": "donor",
                "peak": "1e19 cm^-3",
                "center": "0.2 um",
                "standard_deviation": "0 nm",
            }
        )


def test_tabulated_profile_rejects_unsorted_or_mismatched_points() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        PROFILE.validate_python(
            {
                "kind": "tabulated",
                "region": "bulk",
                "species": "donor",
                "positions": ["1 um", "0 um"],
                "values": ["1e15 cm^-3", "2e15 cm^-3"],
            }
        )
