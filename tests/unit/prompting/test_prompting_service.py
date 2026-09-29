from __future__ import annotations

from pathlib import Path

from tcad_agent.prompting.compiler import PromptCompiler
from tcad_agent.prompting.context import LocalEvidenceCollector, WorkspaceContextCollector
from tcad_agent.prompting.models import (
    ClarificationAnswer,
    ClarificationQuestion,
    IntentField,
    IntentOrigin,
    PreparationDecision,
    ResolvedResearchIntent,
)
from tcad_agent.prompting.service import PromptPreparationService, ScriptedPreparationModel


class EmptyKnowledgeIndex:
    def search(self, query: str, filters=None, limit: int = 5):
        del query, filters, limit
        return ()


def test_service_returns_questions_without_compiling(tmp_path: Path) -> None:
    model = ScriptedPreparationModel(
        [
            PreparationDecision(
                status="clarification",
                summary="The temperature is required.",
                questions=(
                    ClarificationQuestion(
                        id="temperature",
                        field_path="study.temperature",
                        prompt="What temperature should be used?",
                        reason="Material properties and carrier statistics depend on it.",
                    ),
                ),
                unresolved_critical=("study.temperature",),
            )
        ]
    )
    service = PromptPreparationService(
        model=model,
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "d" * 64},
    )

    outcome = service.prepare(
        root=tmp_path, original_prompt="Simulate the requested structure", answers=()
    )

    assert outcome.decision.status == "clarification"
    assert outcome.compiled_request is None


def test_service_compiles_after_structured_answers(tmp_path: Path) -> None:
    ready = PreparationDecision(
        status="ready",
        summary="The researcher supplied the missing condition.",
        intent=ResolvedResearchIntent(
            task_kind="simulation",
            objective="Run the requested study at the confirmed temperature.",
            fields=(
                IntentField(
                    path="study.temperature",
                    value="300 K",
                    origin=IntentOrigin.RESEARCHER,
                ),
            ),
        ),
    )
    service = PromptPreparationService(
        model=ScriptedPreparationModel([ready]),
        workspace_collector=WorkspaceContextCollector(),
        evidence_collector=LocalEvidenceCollector(EmptyKnowledgeIndex()),
        compiler=PromptCompiler(),
        capability_hashes={"devsim": "d" * 64},
    )

    outcome = service.prepare(
        root=tmp_path,
        original_prompt="Simulate the requested structure",
        answers=(ClarificationAnswer(question_id="temperature", answer="300 K"),),
    )

    assert outcome.compiled_request is not None
    assert outcome.compiled_request.answers[0].answer == "300 K"
