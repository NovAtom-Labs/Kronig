from tcad_agent.science.models import ModelDiscoveredRequirement
from tcad_agent.science.requirements import merge_model_discoveries


def test_model_discovery_requires_bounded_evidence() -> None:
    unsupported = ModelDiscoveredRequirement(
        id="unbounded_guess",
        path="physics.mystery_value",
        rationale="The model guessed that a value might be useful.",
        consequence="The request might change.",
        evidence_refs=(),
        confidence=0.99,
    )

    accepted, rejected = merge_model_discoveries(
        registered_paths=set(),
        discoveries=(unsupported,),
        allowed_evidence_refs={"manual:reviewed"},
    )

    assert accepted == ()
    assert rejected == (unsupported,)


def test_model_discovery_is_deduplicated_against_registered_rule() -> None:
    discovery = ModelDiscoveredRequirement(
        id="area_again",
        path="contacts.left.area",
        rationale="Absolute current requires area.",
        consequence="Amperes cannot be derived without it.",
        evidence_refs=("manual:reviewed",),
        confidence=0.9,
    )

    accepted, rejected = merge_model_discoveries(
        registered_paths={"contacts.left.area"},
        discoveries=(discovery,),
        allowed_evidence_refs={"manual:reviewed"},
    )

    assert accepted == ()
    assert rejected == (discovery,)
