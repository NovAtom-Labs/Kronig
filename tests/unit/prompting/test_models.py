from __future__ import annotations

from pydantic import ValidationError

from tcad_agent.prompting.models import (
    ClarificationQuestion,
    EvidenceExcerpt,
    IntentField,
    IntentOrigin,
    PreparationDecision,
    ResolvedResearchIntent,
)


def question(index: int) -> ClarificationQuestion:
    return ClarificationQuestion(
        id=f"q{index}",
        field_path=f"intent.field_{index}",
        prompt=f"What value should field {index} use?",
        reason="This controls whether the requested work can be reproduced.",
    )


def test_clarification_batches_are_bounded() -> None:
    with __import__("pytest").raises(ValidationError, match="at most 7"):
        PreparationDecision(
            status="clarification",
            summary="The request needs essential researcher choices.",
            questions=tuple(question(index) for index in range(8)),
            unresolved_critical=("intent.scope",),
        )


def test_ready_decision_rejects_unresolved_critical_intent() -> None:
    with __import__("pytest").raises(ValidationError, match="unresolved"):
        PreparationDecision(
            status="ready",
            summary="Ready",
            intent=ResolvedResearchIntent(
                task_kind="simulation",
                objective="Run the requested study.",
                fields=(
                    IntentField(
                        path="study.temperature",
                        value="300 K",
                        origin=IntentOrigin.RESEARCHER,
                    ),
                ),
                unresolved_critical=("geometry.extent",),
            ),
        )


def test_evidence_origin_requires_a_known_reference_and_rationale() -> None:
    with __import__("pytest").raises(ValidationError, match="evidence"):
        IntentField(
            path="physics.mobility_model",
            value="field_dependent",
            origin=IntentOrigin.EVIDENCE,
        )


def test_contract_is_generic_and_has_no_device_discriminator() -> None:
    intent = ResolvedResearchIntent(
        task_kind="mixed",
        objective="Inspect a repository and run the scientifically requested work.",
        fields=(
            IntentField(
                path="research.objective",
                value="Compare equilibrium fields",
                origin=IntentOrigin.RESEARCHER,
            ),
        ),
        deliverables=("canonical simulation result",),
    )

    assert "device" not in ResolvedResearchIntent.model_fields
    assert intent.task_kind == "mixed"


def test_evidence_excerpt_is_hash_and_version_bearing() -> None:
    excerpt = EvidenceExcerpt(
        id="portable-equilibrium:1",
        title="Equilibrium semiconductor equations",
        url="https://example.invalid/equilibrium",
        version="1.0",
        content_hash="a" * 64,
        reviewed=True,
        content="At equilibrium, net terminal current should vanish.",
    )

    assert excerpt.content_hash == "a" * 64


def test_existing_unresolved_metadata_can_be_loaded_before_model_reconciliation():
    from tcad_agent.prompting.models import PreparationDecision

    decision = PreparationDecision.model_validate(
        {
            "status": "clarification",
            "summary": "Resolve the thickness unit",
            "questions": [
                {
                    "id": "thickness",
                    "field_path": "regions.geometry.thickness",
                    "prompt": "What thickness and unit?",
                    "reason": "Physical dimension",
                }
            ],
            "unresolved_critical": ["regions.geometry.thickness"],
            "intent": {
                "task_kind": "simulation",
                "objective": "Analyze a layered structure",
                "unresolved_critical": ["Thickness unit ('original unit is ambiguous')"],
            },
        }
    )
    assert decision.questions[0].field_path == "regions.geometry.thickness"
    assert decision.intent.unresolved_critical == ("Thickness unit ('original unit is ambiguous')",)
