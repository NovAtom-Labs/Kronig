"""Agent-facing quantity schemas must describe the actual accepted input."""

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.units import QuantityValue


def test_validation_schema_advertises_unit_strings_and_canonical_quantities():
    schema = ExperimentSpec.model_json_schema(mode="validation")["$defs"]["QuantityValue"]
    assert any(item.get("type") == "string" for item in schema["anyOf"])
    canonical = next(item for item in schema["anyOf"] if item.get("type") == "object")
    assert set(canonical["required"]) == {"magnitude_si", "si_unit", "dimensionality"}
    assert QuantityValue.model_validate("4.1 eV").is_compatible_with("J")
    assert not QuantityValue.model_validate("4.1 V").is_compatible_with("J")


def test_serialization_schema_and_result_units_remain_canonical():
    schema = QuantityValue.model_json_schema(mode="serialization")
    assert schema["type"] == "object"
    assert "anyOf" not in schema
    quantity = QuantityValue.model_validate("4.1 eV")
    assert quantity.model_dump()["si_unit"] == "kilogram * meter ** 2 / second ** 2"
