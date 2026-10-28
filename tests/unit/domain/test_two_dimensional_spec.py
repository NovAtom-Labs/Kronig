"""Two-dimensional structures: additive to the 1D contract, with strict geometry validation."""

import copy

import pytest
from pydantic import ValidationError

from tcad_agent.domain.models import ExperimentSpec


def planar_device() -> dict:
    """Generic rectangles, doping windows and contacts; x is depth and y is lateral."""
    return {
        "schema_version": "1.0",
        "name": "planar-device",
        "dimension": 2,
        "regions": [
            {
                "id": "insulator",
                "material": "silicon_dioxide",
                "x0": "0 um",
                "x1": "0.005 um",
                "y0": "0.1 um",
                "y1": "0.2 um",
            },
            {
                "id": "body",
                "material": "silicon",
                "x0": "0.005 um",
                "x1": "0.205 um",
                "y0": "0 um",
                "y1": "0.3 um",
            },
        ],
        "profiles": [
            {"kind": "constant", "region": "body", "species": "acceptor", "value": "1e17 cm^-3"},
            {
                "kind": "box",
                "region": "body",
                "species": "donor",
                "value": "1e20 cm^-3",
                "x0": "0.005 um",
                "x1": "0.055 um",
                "y0": "0 um",
                "y1": "0.1 um",
            },
        ],
        "contacts": [
            {
                "id": "gate",
                "region": "insulator",
                "location": "x_min",
                "kind": "metal_work_function",
                "work_function": "4.1 eV",
            },
            {
                "id": "left",
                "region": "body",
                "location": "x_min",
                "span": ["0 um", "0.1 um"],
                "kind": "ohmic",
            },
            {"id": "back", "region": "body", "location": "x_max", "kind": "ohmic"},
        ],
        "physics": {
            "equations": ["poisson", "electron_continuity", "hole_continuity"],
            "models": ["fermi", "constant_mobility", "srh"],
            "temperature": "300 K",
        },
        "study": {"kind": "dc", "contact": "gate", "start": "0 V", "stop": "1 V", "step": "0.5 V"},
        "profile_cuts": [{"id": "cut", "at": "0.006 um"}],
        "observables": ["potential", "terminal_charge"],
    }


def build(mutator=None) -> ExperimentSpec:
    data = copy.deepcopy(planar_device())
    if mutator:
        mutator(data)
    return ExperimentSpec.model_validate(data)


def test_a_two_dimensional_structure_is_accepted_and_keeps_every_input() -> None:
    spec = build()
    assert spec.dimension == 2 and len(spec.regions) == 2
    assert spec.contacts[1].span is not None
    assert spec.profile_cuts[0].at.to("m") == pytest.approx(6e-9)


@pytest.mark.parametrize(
    ("label", "mutator", "message"),
    [
        ("overlap", lambda d: d["regions"][1].update(x0="0 um"), "overlap"),
        ("box outside", lambda d: d["profiles"][1].update(y1="0.5 um"), "inside its region"),
        ("span outside", lambda d: d["contacts"][1].update(span=["0 um", "0.5 um"]), "outside"),
        ("shared boundary", lambda d: d["contacts"][0].update(location="x_max"), "shared"),
        ("unknown region", lambda d: d["contacts"][2].update(region="nowhere"), "needs a region"),
        ("cut outside", lambda d: d["profile_cuts"][0].update(at="5 um"), "inside the structure"),
        (
            # A depth below the interface written as if it were a coordinate from the top.
            "cut in the insulator",
            lambda d: d["profile_cuts"][0].update(at="0.001 um"),
            "outside every doped region",
        ),
        (
            "duplicate cut",
            lambda d: d["profile_cuts"].append({"id": "cut", "at": "0.1 um"}),
            "unique",
        ),
        (
            "interfaces",
            lambda d: d.update(
                interfaces=[{"id": "i", "left_region": "insulator", "right_region": "body"}]
            ),
            "interfaces",
        ),
    ],
)
def test_bad_two_dimensional_geometry_is_refused_with_a_reason(label, mutator, message) -> None:
    with pytest.raises(ValidationError, match=message):
        build(mutator)


def test_one_dimensional_specifications_cannot_carry_two_dimensional_fields() -> None:
    with pytest.raises(ValidationError, match="require dimension 2"):
        build(lambda d: d.update(dimension=1))


def test_a_stack_without_lateral_extent_is_still_a_valid_one_dimensional_spec() -> None:
    spec = ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "stack",
            "dimension": 1,
            "regions": [
                {"id": "a", "material": "silicon", "x0": "0 um", "x1": "1 um"},
            ],
            "profiles": [
                {"kind": "constant", "region": "a", "species": "donor", "value": "1e16 cm^-3"}
            ],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {
                "equations": ["poisson"],
                "models": [],
                "temperature": "300 K",
            },
            "study": {"kind": "equilibrium"},
            "observables": ["potential"],
        }
    )
    assert spec.dimension == 1 and spec.profile_cuts == ()


def test_electrodes_that_touch_are_refused_with_a_remedy():
    import copy

    import pytest

    from tcad_agent.domain.models import ExperimentSpec

    data = copy.deepcopy(planar_device())
    first, second = data["contacts"][0], data["contacts"][1]
    second.update(region=first["region"], location=first["location"])
    first["span"], second["span"] = ["0.1 um", "0.15 um"], ["0.15 um", "0.2 um"]
    with pytest.raises(ValueError, match="touch or overlap.*span"):
        ExperimentSpec.model_validate(data)
