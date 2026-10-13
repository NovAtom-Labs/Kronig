"""Capability-driven input checks, independent of device names and prompt examples."""

import re

from tcad_agent.capabilities.descriptors import CapabilityCatalogView, InputAuthority
from tcad_agent.domain.units import QuantityValue
from tcad_agent.prompting.models import ClarificationQuestion, PreparationDecision


def readable_questions(decision: PreparationDecision, catalog: CapabilityCatalogView | None):
    """Keep diagnostic schema paths out of both prompts and rationale disclosures."""
    labels = {
        canonical_path(item.path): item.description.lower()
        for cap in (catalog.capabilities if catalog else ())
        for item in (*cap.required_inputs, *cap.optional_inputs)
    }
    labels.update(
        {
            "study.ac": "small-signal analysis",
            "study.dc": "voltage sweep",
            "study.dc_points": "specified voltage points",
        }
    )
    pattern = re.compile(
        r"\b(?:study|studies|physics|contacts|regions|profiles|interfaces|observables|profile_sampling)(?:\.[a-zA-Z0-9_]+)+"
    )

    def replace(match):
        path = canonical_path(match.group())
        return labels.get(path, " ".join(path.split(".")[1:]).replace("_", " "))

    def readable(text):
        return re.sub(r"\bdc_points\b", "specified voltage points", pattern.sub(replace, text))

    return decision.model_copy(
        update={
            "questions": tuple(
                question.model_copy(
                    update={
                        "prompt": readable(question.prompt),
                        "reason": readable(question.reason),
                    }
                )
                for question in decision.questions
            )
        }
    )


def canonical_path(path: str) -> str:
    parts = [part for part in path.split(".") if not part.isdigit()]
    aliases = {
        "studies": "study",
        "type": "kind",
        "values_v": "values",
        "start_v": "start",
        "stop_v": "stop",
        "step_v": "step",
        "frequency_hz": "frequency",
        "amplitude_v": "amplitude",
    }
    parts = [aliases.get(part, part) for part in parts]
    if parts[:2] == ["study", "dc_points"]:
        parts.pop(1)
    return ".".join(parts)


def covers(path: str, requirement: str) -> bool:
    """Match semantic path segments while allowing named regions or list indices."""
    segments = iter(canonical_path(path).split("."))
    return all(
        any(segment == expected for segment in segments)
        for expected in canonical_path(requirement).split(".")
    )


def question_for_path(
    path: str, catalog: CapabilityCatalogView | None = None, *, selected: tuple[str, ...] = ()
) -> ClarificationQuestion:
    descriptor = descriptor_for_path(path, catalog, selected)
    labels = {
        "study.kind": "analysis type (for example equilibrium, voltage sweep, or small-signal)",
        "study.values": "voltage operating points",
        "study.step": "voltage increment",
        "study.frequency": "small-signal frequency",
        "study.amplitude": "small-signal voltage amplitude",
    }
    label = descriptor.description if descriptor else labels.get(canonical_path(path))
    if label is None:
        label = re.sub(r"[_.-]+", " ", canonical_path(path))
    unit = f" in {descriptor.unit}" if descriptor and descriptor.unit else ""
    return ClarificationQuestion(
        id="input_" + re.sub(r"[^a-z0-9_]", "_", path)[:65],
        field_path=path,
        prompt=(
            descriptor.question_hint
            if descriptor and descriptor.question_hint
            else f"What should be used for the {label.lower()}{unit}?"
        ),
        reason=(
            f"This determines the {label.lower()}; it must not be chosen without your instruction."
        ),
    )


def requirement_path(capability_id: str, path: str, selected: tuple[str, ...]) -> str:
    """Separate nested voltage schedules from frequency/time study parameters."""
    if (
        capability_id in {"study.dc", "study.dc_points"}
        and any(item in selected for item in ("study.ac", "study.frequency"))
        and path.startswith("study.")
    ):
        return path.replace("study.", "study.bias_schedule.", 1)
    return path


def descriptor_for_path(path, catalog, selected=()):
    candidates = [
        item
        for cap in (catalog.capabilities if catalog else ())
        if not selected or cap.id in selected
        for item in (*cap.required_inputs, *cap.optional_inputs)
        if canonical_path(requirement_path(cap.id, item.path, selected)) == canonical_path(path)
    ]
    if not candidates or len({item.unit for item in candidates}) > 1:
        return None
    return candidates[0]


def _dimension_matches(value, unit, *, ambiguous):
    if not unit:
        return True
    if isinstance(value, list | tuple):
        return bool(value) and all(
            _dimension_matches(item, unit, ambiguous=ambiguous) for item in value
        )
    if isinstance(value, int | float):
        # A numeric intent has descriptor units only if those units are unique.
        return not ambiguous
    try:
        return QuantityValue.model_validate(value).is_compatible_with(unit)
    except ValueError:
        return False


def enforce_completeness(
    decision: PreparationDecision, catalog: CapabilityCatalogView | None
) -> PreparationDecision:
    intent = decision.intent
    if not catalog or not intent or intent.task_kind not in {"simulation", "mixed"}:
        return decision
    values = {canonical_path(field.path): field.value for field in intent.fields}
    selected = set(intent.selected_capabilities)
    kind = values.get("study.kind")
    if isinstance(kind, str):
        selected.add("study." + kind)
    temperature_schedule = "study.temperature" in selected and any(
        covers(path, "study.values") and _dimension_matches(value, "K", ambiguous=False)
        for path, value in values.items()
    )
    if temperature_schedule:
        # The temperature schedule already supplies the physical temperatures.
        # A nominal adapter initialization value is not a new research condition.
        decision = decision.model_copy(
            update={
                "intent": intent.model_copy(
                    update={
                        "unresolved_critical": tuple(
                            p
                            for p in intent.unresolved_critical
                            if canonical_path(p) != "physics.temperature"
                        ),
                    }
                ),
                "questions": tuple(
                    q
                    for q in decision.questions
                    if canonical_path(q.field_path) != "physics.temperature"
                ),
                "unresolved_critical": tuple(
                    p
                    for p in decision.unresolved_critical
                    if canonical_path(p) != "physics.temperature"
                ),
            }
        )
        intent = decision.intent
        if (
            decision.status == "clarification"
            and not decision.questions
            and not decision.unresolved_critical
        ):
            decision = decision.model_copy(update={"status": "ready"})
    missing = list(decision.unresolved_critical)
    requirements = [
        (cap.id, item)
        for cap in catalog.capabilities
        if cap.id in selected
        for item in cap.required_inputs
    ]
    for capability in catalog.capabilities:
        if capability.id not in selected:
            continue
        for item in capability.required_inputs:
            if temperature_schedule and item.path == "physics.temperature":
                continue
            if (
                item.required
                and item.authority is InputAuthority.RESEARCHER
                and item.completeness_check == "value"
            ):
                qualified = requirement_path(capability.id, item.path, tuple(selected))
                key = canonical_path(qualified)
                ambiguous = (
                    len({other.unit for _, other in requirements if other.path == item.path}) > 1
                )
                if (
                    not any(
                        value is not None
                        and (
                            covers(path, key)
                            or (
                                qualified != item.path
                                and canonical_path(path) == canonical_path(item.path)
                            )
                        )
                        and _dimension_matches(value, item.unit, ambiguous=ambiguous)
                        for path, value in values.items()
                    )
                    and qualified not in missing
                ):
                    missing.append(qualified)
    if not missing:
        return decision
    existing = {canonical_path(question.field_path): question for question in decision.questions}
    questions = tuple(
        existing.get(canonical_path(path))
        or question_for_path(path, catalog, selected=tuple(selected))
        for path in dict.fromkeys(missing)
    )[:7]
    return decision.model_copy(
        update={
            "status": "clarification",
            "questions": questions,
            "intent": intent.model_copy(update={"unresolved_critical": tuple(missing)}),
            "unresolved_critical": tuple(missing),
        }
    )
