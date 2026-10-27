import pytest

from tcad_agent.prompting.completeness import _matches_scope


@pytest.mark.parametrize(
    "field_path",
    ["regions.oxide.material", "regions.material.oxide", "regions.material"],
)
def test_an_entitys_value_may_name_the_entity_before_or_after_the_property(field_path):
    assert _matches_scope(field_path, "regions.material")


@pytest.mark.parametrize(
    "field_path",
    ["regions.oxide.thickness", "regions.parameters.oxide_thickness", "contacts.material.gate"],
)
def test_another_property_or_collection_is_not_a_match(field_path):
    assert not _matches_scope(field_path, "regions.material")
