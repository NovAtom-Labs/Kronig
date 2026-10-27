"""Mesh refinement halves what was specified and never invents a conflicting target."""

import pytest

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.validation.refinement import refined_spec


def stack(region_extra: dict) -> ExperimentSpec:
    region = {"id": "a", "material": "silicon", "x0": "0 um", "x1": "0.005 um"} | region_extra
    return ExperimentSpec.model_validate(
        {
            "schema_version": "1.0",
            "name": "stack",
            "dimension": 1,
            "regions": [region],
            "profiles": [
                {"kind": "constant", "region": "a", "species": "donor", "value": "1e16 cm^-3"}
            ],
            "contacts": [
                {"id": "left", "location": "x_min", "kind": "ohmic"},
                {"id": "right", "location": "x_max", "kind": "ohmic"},
            ],
            "physics": {"equations": ["poisson"], "models": [], "temperature": "300 K"},
            "study": {"kind": "equilibrium"},
            "observables": ["potential"],
        }
    )


def nm(value) -> float:
    return value.to("m") * 1e9


def test_graded_bounds_without_a_target_are_halved_without_inventing_one() -> None:
    # A 5 nm region has a 0.1 nm default target, far below its 1 nm minimum; refinement used
    # to halve that invented target and produce an invalid spec.
    refined = refined_spec(
        stack({"minimum_mesh_spacing": "1 nm", "maximum_mesh_spacing": "2 nm"})
    ).regions[0]
    assert refined.mesh_spacing is None
    assert nm(refined.minimum_mesh_spacing) == pytest.approx(0.5)
    assert nm(refined.maximum_mesh_spacing) == pytest.approx(1.0)


def test_a_stated_target_is_halved_with_its_bounds() -> None:
    refined = refined_spec(
        stack(
            {"mesh_spacing": "2 nm", "minimum_mesh_spacing": "1 nm", "maximum_mesh_spacing": "4 nm"}
        )
    ).regions[0]
    assert [nm(refined.mesh_spacing), nm(refined.minimum_mesh_spacing)] == pytest.approx([1, 0.5])


def test_with_nothing_specified_the_default_target_is_halved() -> None:
    refined = refined_spec(stack({})).regions[0]
    assert nm(refined.mesh_spacing) == pytest.approx(0.05)
