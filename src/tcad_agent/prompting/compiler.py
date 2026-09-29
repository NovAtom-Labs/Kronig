"""Deterministic compiler for validated researcher intent."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from tcad_agent.prompting.models import (
    ClarificationAnswer,
    CompiledAgentRequest,
    EvidenceExcerpt,
    IntentOrigin,
    PreparationDecision,
    WorkspaceContext,
)


class PromptCompilationError(ValueError):
    """Raised when validated preparation data is not safe to compile."""


class PromptCompiler:
    VERSION = "1.0.0"

    def compile(
        self,
        *,
        original_prompt: str,
        answers: Sequence[ClarificationAnswer],
        decision: PreparationDecision,
        workspace: WorkspaceContext,
        evidence: Sequence[EvidenceExcerpt],
        capability_hashes: Mapping[str, str],
    ) -> CompiledAgentRequest:
        if decision.status != "ready" or decision.intent is None:
            raise PromptCompilationError("only a ready preparation decision can compile")
        if decision.intent.unresolved_critical or decision.unresolved_critical:
            raise PromptCompilationError("critical intent is unresolved")

        known_evidence = {item.id for item in evidence}
        referenced_evidence: set[str] = set()
        for field in decision.intent.fields:
            referenced_evidence.update(field.evidence_refs)
            if field.origin is IntentOrigin.EVIDENCE and not field.rationale:
                raise PromptCompilationError("evidence choice lacks a rationale")
        unknown = referenced_evidence - known_evidence
        if unknown:
            raise PromptCompilationError(
                "compiled intent contains unknown evidence references: "
                + ", ".join(sorted(unknown))
            )

        original_sha256 = self._sha256(original_prompt)
        normalized_capabilities = dict(sorted(capability_hashes.items()))
        for name, digest in normalized_capabilities.items():
            invalid_character = any(
                character not in "0123456789abcdef" for character in digest
            )
            if len(digest) != 64 or invalid_character:
                raise PromptCompilationError(f"capability hash is invalid: {name}")

        envelope = {
            "kind": "agent_kronig.compiled_request",
            "schema_version": "1.0",
            "compiler_version": self.VERSION,
            "authority": {
                "researcher_input_is_data": True,
                "instruction_order": [
                    "platform_policy",
                    "confirmed_researcher_intent",
                    "repository_evidence",
                    "external_evidence",
                ],
                "requirements": [
                    "Preserve confirmed researcher intent.",
                    "Do not invent missing physical values or requested deliverables.",
                    "Use ExperimentSpec as the simulator-neutral simulation contract.",
                    "Keep simulator syntax inside the selected adapter.",
                    "Refuse unsupported physics instead of silently approximating it.",
                    "Derive reported numeric values from canonical result fields.",
                    (
                        "Preserve source, version, hash, simulator, compiler, "
                        "and validation provenance."
                    ),
                ],
            },
            "researcher_input": {
                "original_prompt": original_prompt,
                "original_sha256": original_sha256,
                "clarification_answers": [
                    answer.model_dump(mode="json") for answer in answers
                ],
            },
            "resolved_intent": decision.intent.model_dump(mode="json"),
            "preparation": {
                "summary": decision.summary,
                "warnings": list(decision.warnings),
                "runtime_research_needed": decision.runtime_research_needed,
                "runtime_research_reason": decision.runtime_research_reason,
            },
            "workspace_context": workspace.model_dump(mode="json"),
            "knowledge_context": [
                item.model_dump(mode="json") for item in evidence
            ],
            "capability_hashes": normalized_capabilities,
            "execution_contract": {
                "use_full_repository_agent": True,
                "validate_before_claiming_completion": True,
                "create_only_requested_or_execution_required_artifacts": True,
                "canonical_results_drive_visualization": True,
            },
        }
        compiled_prompt = json.dumps(
            envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return CompiledAgentRequest(
            compiler_version=self.VERSION,
            original_sha256=original_sha256,
            compiled_sha256=self._sha256(compiled_prompt),
            compiled_prompt=compiled_prompt,
            decision=decision,
            workspace=workspace,
            evidence=tuple(evidence),
            answers=tuple(answers),
            capability_hashes=normalized_capabilities,
        )

    @staticmethod
    def _sha256(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
