"""Run-local clarification identity and researcher answer provenance."""

import hashlib
import json
from collections.abc import Sequence

from tcad_agent.domain.units import UNIT_REGISTRY, QuantityValue
from tcad_agent.prompting.completeness import _matches_scope, canonical_path, complete_input
from tcad_agent.prompting.models import ClarificationAnswer, ClarificationQuestion


def bind_answers(
    answers: Sequence[ClarificationAnswer],
    questions: Sequence[ClarificationQuestion],
    revision: int,
) -> tuple[ClarificationAnswer, ...]:
    """Only the server can bind an answer to the currently displayed question."""
    by_id = {question.id: question for question in questions}
    bound = []
    for answer in answers:
        question = by_id[answer.question_id]
        expected = {
            "field_path": question.field_path,
            "question_prompt": question.prompt,
            "question_revision": revision,
        }
        if any(
            getattr(answer, key) is not None and getattr(answer, key) != value
            for key, value in expected.items()
        ):
            raise ValueError("clarification answer binding does not match the active question")
        bound.append(answer.model_copy(update=expected))
    return tuple(bound)


def current_answers(answers):
    """Historical IDs cannot authorize changes to a different current field."""
    revisions = [
        answer.question_revision for answer in answers if answer.question_revision is not None
    ]
    if not revisions:
        return answers
    latest = max(revisions)
    return tuple(answer for answer in answers if answer.question_revision == latest)


def validate_questions(decision, original_prompt, answers, catalog, previous=None):
    """A model's claim of ambiguity is not authority to re-ask known inputs."""
    if not decision.intent:
        return
    old_fields = (
        {field.path: field.value for field in previous.intent.fields}
        if (previous and previous.intent)
        else {}
    )
    fields = {field.path: field.value for field in decision.intent.fields}
    for question in decision.questions:
        bound = [
            answer
            for answer in answers
            if answer.field_path
            and (
                _matches_scope(question.field_path, answer.field_path)
                or _matches_scope(answer.field_path, question.field_path)
                or question.field_path.startswith(answer.field_path + ".")
            )
        ]
        if bound and complete_input(decision.intent, question.field_path, catalog):
            # Keep obsolete text for provenance, not as an objection to a correction.
            source_text = [answer.answer for answer in current_answers(bound)]
        else:
            source_text = [original_prompt, *(answer.answer for answer in answers)]
        sources = [" ".join(value.split()).casefold() for value in source_text]
        kind = question.reason_kind
        if kind in {"conflict", "invalid", "ambiguous"}:
            quotes = {" ".join(value.split()).casefold() for value in question.evidence_quotes}
            minimum = 2 if kind == "conflict" else 1
            if len(quotes) < minimum or any(
                not quote or not any(quote in source for source in sources) for quote in quotes
            ):
                raise ValueError(
                    "Clarification must cite the actual conflicting or invalid researcher input."
                )
        elif kind == "dependency_changed":
            if not question.dependency_fields or not any(
                path in fields
                and path in old_fields
                and _normalized(fields[path]) != _normalized(old_fields[path])
                for path in question.dependency_fields
            ):
                raise ValueError("Clarification must identify an actual changed input dependency.")
        elif kind == "unspecified" and complete_input(
            decision.intent, question.field_path, catalog
        ):
            raise ValueError(
                "This input is already confirmed; a specific scientific reason "
                "is needed to ask again."
            )


def _normalized(value):
    try:
        quantity = QuantityValue.model_validate(value)
        dimensions = UNIT_REGISTRY.get_dimensionality(quantity.dimensionality)
        return {"si": quantity.magnitude_si, "dimension": sorted(dimensions.items())}
    except (ValueError, TypeError):
        if isinstance(value, dict):
            return {key: _normalized(item) for key, item in value.items()}
        if isinstance(value, list | tuple):
            return [_normalized(item) for item in value]
        return value


def state_fingerprint(decision):
    """Ignore wording, source ordering and equivalent unit spelling when detecting loops."""

    intent = decision.intent
    payload = {
        "fields": {
            canonical_path(field.path, preserve_indices=True): _normalized(field.value)
            for field in intent.fields
        }
        if intent
        else {},
        "capabilities": sorted(intent.selected_capabilities) if intent else [],
        "unresolved": sorted(
            {
                canonical_path(path, preserve_indices=True)
                for path in (
                    *decision.unresolved_critical,
                    *(intent.unresolved_critical if intent else ()),
                )
            }
        ),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
