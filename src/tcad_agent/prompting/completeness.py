"""Capability-driven input checks, independent of device names and prompt examples."""

import math
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


def canonical_path(path: str, *, preserve_indices: bool = False) -> str:
    parts = [part for part in path.split(".") if preserve_indices or not part.isdigit()]
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
    if parts in (["physics", "statistics"], ["physics", "contact_statistics_choice"]):
        parts = ["physics", "models"]
    if parts[:2] == ["study", "dc_points"]:
        parts.pop(1)
    return ".".join(parts)


def _scoped_path(path: str) -> str:
    return canonical_path(
        path,
        preserve_indices=path.split(".", 1)[0] in {"contacts", "regions", "profiles", "interfaces"},
    )


def _matches_scope(field_path: str, requirement: str) -> bool:
    """Allow entity-qualified inputs, not unrelated nested study schedules."""
    actual = _scoped_path(field_path).split(".")
    expected = _scoped_path(requirement).split(".")
    if actual == expected:
        return True
    return (
        len(expected) == 2
        and len(actual) == 3
        and expected[0] in {"contacts", "regions", "profiles", "interfaces"}
        and actual[0] == expected[0]
        # The entity may come before the property ("regions.oxide.material") or after it
        # ("regions.material.oxide"); both name one entity's value of that property.
        and expected[1] in {actual[1], actual[2]}
    )


def _entity_key_matches(key: str, identity: str) -> bool:
    if key == identity:
        return True
    prefix = identity + "_"
    if not key.startswith(prefix):
        return False
    try:
        # A suffix must itself be a unit, not another entity's name. For
        # example a left_aux quantity must never be assigned to entity left.
        QuantityValue.model_validate("1 " + key[len(prefix) :])
        return True
    except ValueError:
        return False


def _record_identity(value, collection: str):
    return value.get(collection.removesuffix("s"), value.get("id", value.get("label")))


def _entity_values(value, collection: str, identity: str):
    """Project only the requested entity from an explicitly scoped record."""

    if isinstance(value, list | tuple):
        if identity.isdigit():
            index = int(identity)
            return [value[index]] if index < len(value) else []
        return [
            item
            for item in value
            if isinstance(item, dict) and _record_identity(item, collection) == identity
        ]
    if isinstance(value, dict):
        if _record_identity(value, collection) == identity:
            return [value]
        if identity in value:
            return [value[identity]]
        scoped = {key: item for key, item in value.items() if _entity_key_matches(key, identity)}
        if scoped:
            return [scoped]
        return [
            item
            for item in value.values()
            if isinstance(item, dict) and _record_identity(item, collection) == identity
        ]
    return []


def _without_entity(value, collection: str, identity: str):
    """Remove an explicitly answered entity without changing other quantities."""
    if isinstance(value, list | tuple):
        # Preserve original positions when removing an answered entity.
        return {
            str(index): item
            for index, item in enumerate(value)
            if str(index) != identity
            and not (isinstance(item, dict) and _record_identity(item, collection) == identity)
        }
    if isinstance(value, dict):
        if _record_identity(value, collection) == identity:
            return {}
        return {
            key: item
            for key, item in value.items()
            if not _entity_key_matches(key, identity)
            and not (isinstance(item, dict) and _record_identity(item, collection) == identity)
        }
    return value


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
        reason_kind="missing",
    )


_SWEEP_PARTS = ("start", "stop", "step")


def _merge_sweep_questions(missing, existing, catalog, selected):
    """Ask for a voltage sweep once, not as a separate question for each of its parts.

    One answer states all of start, stop and step, so three questions about one sweep make the
    researcher repeat themselves. When the model's own question already asks for all three, the
    separate ones are dropped; otherwise a single clear question stands in for them.
    """
    parts = {f"study.{part}" for part in _SWEEP_PARTS}
    sweep = [path for path in missing if canonical_path(path) in parts]
    if len(sweep) < 2:
        return missing, {}
    covering = [
        question
        for path, question in existing.items()
        if canonical_path(path) not in parts
        and all(word in question.prompt.lower() for word in _SWEEP_PARTS)
        and any(_scoped_path(item) == path for item in missing)
    ]
    kept = [path for path in missing if path not in sweep]
    if covering:
        return kept, {}
    first = sweep[0]
    base = question_for_path(first, catalog, selected=selected)
    combined = base.model_copy(
        update={
            "prompt": (
                "What voltage sweep should be applied? Give the start voltage, stop voltage and "
                "step size, all in V."
            ),
            "reason": "These define the bias points of the sweep; they must not be chosen "
            "without your instruction.",
        }
    )
    index = sum(1 for path in missing[: missing.index(first)] if path in kept)
    return [*kept[:index], first, *kept[index:]], {first: combined}


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
    normalized = canonical_path(path)
    parts = normalized.split(".")
    if len(parts) == 3 and parts[0] in {"contacts", "regions", "profiles", "interfaces"}:
        normalized = parts[0] + "." + parts[2]
    candidates = [
        item
        for cap in (catalog.capabilities if catalog else ())
        if not selected or cap.id in selected
        for item in (*cap.required_inputs, *cap.optional_inputs)
        if canonical_path(requirement_path(cap.id, item.path, selected)) == normalized
    ]
    if not candidates or len({item.unit for item in candidates}) > 1:
        return None
    return candidates[0]


def _dimension_matches(value, unit, *, ambiguous, path=""):
    """Check scalar quantities and scoped records without inventing physical values.

    The model may group values by contact/region or include units in a quantity
    key. Those are representations of the same input, not absent inputs. Every
    record must contain a valid quantity; labels alone never supply one.
    """
    if not unit:
        return True
    if isinstance(value, list | tuple):
        return bool(value) and all(
            _dimension_matches(item, unit, ambiguous=ambiguous, path=path) for item in value
        )
    if isinstance(value, int | float):
        # A numeric intent has descriptor units only if those units are unique.
        return not isinstance(value, bool) and math.isfinite(value) and not ambiguous
    if isinstance(value, dict):
        quantity_key = "value" if "value" in value else "magnitude"
        if "value" in value and "magnitude" in value and value["value"] != value["magnitude"]:
            return False
        if quantity_key in value and "unit" in value:
            # An explicit but wrong unit must not fall back to descriptor units.
            return (
                not isinstance(value[quantity_key], bool)
                and isinstance(value["unit"], str)
                and _dimension_matches(
                    f"{value[quantity_key]} {value['unit']}", unit, ambiguous=ambiguous, path=path
                )
            )
        if {"magnitude_si", "si_unit", "dimensionality"} <= value.keys():
            try:
                return QuantityValue.model_validate(value).is_compatible_with(unit)
            except ValueError:
                return False
        metadata = {"region", "contact", "id", "name", "label", "source_reference", "rationale"}
        quantities = [(key, item) for key, item in value.items() if key not in metadata]
        if not quantities:
            return False
        leaf = canonical_path(path).rsplit(".", 1)[-1]
        for key, item in quantities:
            if key in {leaf, "value"} or key.isdigit() or isinstance(item, dict | list | tuple):
                valid = _dimension_matches(item, unit, ambiguous=ambiguous, path=path)
            elif isinstance(item, str):
                valid = _dimension_matches(item, unit, ambiguous=ambiguous, path=path)
            elif isinstance(item, int | float) and not isinstance(item, bool) and "_" in key:
                # For example a role-qualified energy or a temperature_K entry.
                # Parse the explicit suffix with the same unit registry as scalars.
                valid = _dimension_matches(
                    f"{item} {key.rsplit('_', 1)[-1]}", unit, ambiguous=ambiguous, path=path
                )
            else:
                valid = False
            if not valid:
                return False
        return True
    try:
        return QuantityValue.model_validate(value).is_compatible_with(unit)
    except ValueError:
        return False


def input_values(intent, path):
    """Extract one exact entity's input, never borrow another entity's value."""
    candidates = [field.value for field in intent.fields if _matches_scope(field.path, path)]
    target = _scoped_path(path).split(".")
    if (
        not candidates
        and len(target) == 3
        and target[0] in {"contacts", "regions", "profiles", "interfaces"}
    ):
        aggregate = target[0] + "." + target[2]
        candidates = [
            value
            for field in intent.fields
            if _scoped_path(field.path) == aggregate
            for value in _entity_values(field.value, target[0], target[1])
        ]
    if (
        not candidates
        and len(target) in {2, 3}
        and target[0] in {"contacts", "regions", "profiles", "interfaces"}
    ):

        def properties(value):
            if isinstance(value, dict):
                if target[-1] in value:
                    yield value[target[-1]]
                for key, item in value.items():
                    if key != target[-1]:
                        yield from properties(item)
            elif isinstance(value, list | tuple):
                for item in value:
                    yield from properties(item)

        for field in intent.fields:
            if field.path.split(".")[0] != target[0]:
                continue
            records = (
                _entity_values(field.value, target[0], target[1])
                if len(target) == 3
                else [field.value]
            )
            candidates.extend(item for record in records for item in properties(record))
    return candidates


def complete_input(intent, path, catalog):
    descriptor = descriptor_for_path(path, catalog, intent.selected_capabilities)
    if not descriptor or descriptor.completeness_check != "value":
        return False
    values = input_values(intent, path)
    return bool(values) and all(
        value is not None
        and _dimension_matches(value, descriptor.unit, ambiguous=False, path=descriptor.path)
        for value in values
    )


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
    requirements = [
        (cap.id, item)
        for cap in catalog.capabilities
        if cap.id in selected
        for item in cap.required_inputs
    ]

    def has_value(qualified, item):
        ambiguous = len({other.unit for _, other in requirements if other.path == item.path}) > 1
        candidates = input_values(intent, qualified)
        if not candidates and qualified.startswith("study.bias_schedule."):
            candidates = [
                field.value
                for field in intent.fields
                if canonical_path(field.path) == canonical_path(item.path)
            ]
        # Keep individual region/contact records: canonical aliases remove list
        # indices, so a dict would let the last contact hide a missing first one.
        return bool(candidates) and all(
            value is not None
            and _dimension_matches(value, item.unit, ambiguous=ambiguous, path=item.path)
            for value in candidates
        )

    # Recompute unresolved value requirements from retained intent. A model can
    # repeat a previous unresolved list even after it has supplied the answer.
    # Structured ambiguities remain model-owned and are not dismissed here.
    missing = []
    existing = {_scoped_path(question.field_path): question for question in decision.questions}
    for path in dict.fromkeys((*decision.unresolved_critical, *intent.unresolved_critical)):
        question = existing.get(_scoped_path(path))
        generated = question_for_path(path, catalog, selected=tuple(selected))
        checker_owned = question is not None and all(
            getattr(question, key) == getattr(generated, key) for key in ("id", "prompt", "reason")
        )
        matching = [
            (requirement_path(cap_id, item.path, tuple(selected)), item)
            for cap_id, item in requirements
            if _matches_scope(path, requirement_path(cap_id, item.path, tuple(selected)))
            and item.completeness_check == "value"
        ]
        # A model question may concern conflicting values or ambiguous units.
        # Compatibility alone cannot resolve it. Only our own mechanically
        # generated missing-value questions are safe to dismiss here.
        explicitly_resolved = (
            question is not None
            and question.reason_kind == "missing"
            and complete_input(intent, path, catalog)
        )
        if not explicitly_resolved and (
            not checker_owned
            or not matching
            or not all(has_value(path, item) for _, item in matching)
        ):
            missing.append(path)
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
                if not has_value(key, item) and not any(
                    _matches_scope(path, key) for path in missing
                ):
                    missing.append(qualified)
    if "dimension.2" in selected:
        # A two-dimensional contact has no area: its extent is a lateral span and the device
        # width (asked for separately) is what turns current per width into amperes.
        missing = [
            path for path in missing if not re.fullmatch(r"(.*\.)?contacts(\.[^.]+)?\.area", path)
        ]
    if not missing:
        return decision.model_copy(
            update={
                "status": "ready",
                "questions": (),
                "unresolved_critical": (),
                "intent": intent.model_copy(update={"unresolved_critical": ()}),
            }
        )
    missing, merged = _merge_sweep_questions(missing, existing, catalog, tuple(selected))
    questions = tuple(
        merged.get(path)
        or existing.get(_scoped_path(path))
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
