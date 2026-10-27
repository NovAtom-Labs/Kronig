"""Compare typed researcher inputs to simulator-neutral plan fields.

This checks schema-addressable inputs, not the truth of arbitrary free text.
Unmapped intent remains available for model reasoning and researcher plan review.
"""

import math
import re
from enum import Enum
from typing import Annotated, Literal, get_args, get_origin

from pydantic import BaseModel

from tcad_agent.domain.models import PhysicsParameters, PhysicsSelection
from tcad_agent.domain.units import QuantityValue
from tcad_agent.prompting.completeness import canonical_path

_UNMAPPED = object()


def _schema_quantity_path(annotation, parts):
    """Follow the actual portable schema, including structured profile inputs."""
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Annotated:
        return _schema_quantity_path(arguments[0], parts)
    if origin in {tuple, list, dict}:
        item = arguments[1] if origin is dict else arguments[0]
        return bool(parts) and _schema_quantity_path(item, parts[1:])
    if origin is not None:
        return any(_schema_quantity_path(item, parts) for item in arguments)
    if not parts:
        return annotation in {QuantityValue, float, int}
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        field = annotation.model_fields.get(parts[0])
        return field is not None and _schema_quantity_path(field.annotation, parts[1:])
    return False


def _schema_input_path(annotation, parts):
    """Recognize typed intent even when its selected plan entity is absent."""
    if not parts:
        return True
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Annotated:
        return _schema_input_path(arguments[0], parts)
    if origin in {tuple, list, dict}:
        item = arguments[1] if origin is dict else arguments[0]
        # A collection needs an entity selector and a property. Unqualified
        # prose such as contacts.boundary_conditions is not a typed path.
        return len(parts) > 1 and _schema_input_path(item, parts[1:])
    if origin is not None:
        return any(_schema_input_path(item, parts) for item in arguments)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        fields = annotation.model_fields
        if parts == ["thickness"] and {"x0", "x1"} <= fields.keys():
            return True
        if field := fields.get(parts[0]):
            return _schema_input_path(field.annotation, parts[1:])
        if parameters := fields.get("parameters"):
            return _schema_input_path(parameters.annotation, parts)
    return False


def _models(annotation):
    """Every portable model an annotation can hold, through unions and annotations."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _models(get_args(annotation)[0])
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    if origin is not None and origin not in {tuple, list, dict}:
        return [model for argument in get_args(annotation) for model in _models(argument)]
    return []


def _property_used_as_selector(annotation, parts):
    """Find a collection step whose selector is really a property of the items.

    ``regions.material`` selects nothing: a region is chosen by index or id (``regions.0.material``
    or ``regions.silicon.material``), and ``material`` is what that region has.
    """
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Annotated:
        return _property_used_as_selector(arguments[0], parts)
    if origin in {tuple, list}:
        if not parts:
            return None
        models = _models(arguments[0])
        selector = parts[0]
        if not selector.isdecimal() and any(selector in model.model_fields for model in models):
            return selector
        return next(
            (
                found
                for model in models
                if (found := _property_used_as_selector(model, parts[1:]))
            ),
            None,
        )
    if origin is dict:
        return _property_used_as_selector(arguments[1], parts[1:]) if parts else None
    if origin is not None:
        found = (_property_used_as_selector(argument, parts) for argument in arguments)
        return next((item for item in found if item), None)
    if parts and isinstance(annotation, type) and issubclass(annotation, BaseModel):
        field = annotation.model_fields.get(parts[0])
        return _property_used_as_selector(field.annotation, parts[1:]) if field else None
    return None

def _leaf_annotations(annotation, parts):
    """Every declared type an input path can end on, selecting one entity of each collection."""
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Annotated:
        return _leaf_annotations(arguments[0], parts)
    if not parts:
        return [annotation]
    if origin in {tuple, list}:
        return _leaf_annotations(arguments[0], parts[1:]) if len(parts) > 1 else []
    if origin is dict:
        return []
    if origin is not None:
        return [leaf for argument in arguments for leaf in _leaf_annotations(argument, parts)]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        field = annotation.model_fields.get(parts[0])
        return _leaf_annotations(field.annotation, parts[1:]) if field else []
    return []


def _allowed_values(leaves):
    """The values a field accepts when every possible type for it is an enum or a literal."""
    allowed = []
    for leaf in leaves:
        if isinstance(leaf, type) and issubclass(leaf, Enum):
            allowed.extend(str(member.value) for member in leaf)
        elif get_origin(leaf) is Literal:
            allowed.extend(str(value) for value in get_args(leaf))
        elif get_origin(leaf) is not None and not isinstance(leaf, type):
            nested = _allowed_values([a for a in get_args(leaf) if a is not type(None)])
            if nested is None:
                return None
            allowed.extend(nested)
        else:
            return None
    return list(dict.fromkeys(allowed)) or None

def enum_value_violations(intent) -> list[tuple[str, str, list[str]]]:
    """Confirmed inputs whose field only takes a fixed set of values but carry something else.

    A description such as "top of oxide" for a contact location is a fair thing to say, but the
    plan holds ``x_min``. A mismatch the plan gate cannot reconcile is better repaired up front.
    """
    from tcad_agent.domain.models import ExperimentSpec

    violations = []
    for field in intent.fields:
        if field.origin not in {"researcher", "repository"} or not isinstance(field.value, str):
            continue
        parts = canonical_path(field.path, preserve_indices=True).split(".")
        allowed = _allowed_values(_leaf_annotations(ExperimentSpec, parts))
        if allowed and field.value not in allowed:
            violations.append((field.path, field.value, allowed))
    return violations


def ambiguous_collection_paths(intent) -> list[str]:
    """Compound values filed under a path that cannot select one entity of a collection.

    A single value under an unqualified path is tolerated as prose. An object under it cannot be
    matched to the plan, so the plan gate would refuse every spec; it has to be fixed here.
    """
    from tcad_agent.domain.models import ExperimentSpec

    ambiguous = []
    for field in intent.fields:
        if field.origin not in {"researcher", "repository"} or not isinstance(field.value, dict):
            continue
        try:
            QuantityValue.model_validate(field.value)
        except ValueError:
            pass
        else:
            continue  # a quantity written as an object is one value, not a compound
        parts = canonical_path(field.path, preserve_indices=True).split(".")
        if _property_used_as_selector(ExperimentSpec, parts):
            ambiguous.append(field.path)
    return ambiguous


def _quantity_paths(value, parts):
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        yield parts
        return
    # Enum/model names can also be unit names (for example, a unit of length).
    # Only explicit numeric strings are physical input quantities here.
    if isinstance(value, str) and not re.match(r"^[+-]?(?:\d|\.\d)", value.strip()):
        return
    try:
        QuantityValue.model_validate(value)
    except ValueError:
        items = (
            value.items()
            if isinstance(value, dict)
            else (enumerate(value) if isinstance(value, list | tuple) else ())
        )
        for key, item in items:
            yield from _quantity_paths(item, [*parts, str(key)])
    else:
        yield parts


def unsupported_physics_inputs(intent):
    """Explicit quantity overrides need an actual portable contract field."""
    unsupported = []
    for field in intent.fields:
        if field.origin not in {"researcher", "repository"} or not field.path.startswith(
            "physics."
        ):
            continue
        paths = _quantity_paths(field.value, field.path.removeprefix("physics.").split("."))
        if any(
            not (
                _schema_quantity_path(PhysicsSelection, path)
                or _schema_quantity_path(PhysicsParameters, path)
            )
            for path in paths
        ):
            unsupported.append(field.path)
    return unsupported


def _resolve(value, parts):
    if not parts:
        return value
    key, *remaining = parts
    if isinstance(value, tuple | list):
        if key.isdecimal():
            selected = value[int(key)] if int(key) < len(value) else _UNMAPPED
        else:
            boundary = {"left": "x_min", "right": "x_max"}.get(key)
            matches = [
                item
                for item in value
                if getattr(item, "id", _UNMAPPED) == key
                or getattr(item, "location", _UNMAPPED) == key
                or (boundary and getattr(item, "location", _UNMAPPED) == boundary)
            ]
            if len(matches) == 1:
                selected = matches[0]
            elif not matches and len(value) == 1:
                # A lone record is unambiguous: the key is either a field of it ("parameters") or
                # a descriptive label for it ("silicon_body"), so it cannot name a different one.
                item = value[0]
                fields = type(item).model_fields if isinstance(item, BaseModel) else {}
                parameters = getattr(item, "parameters", _UNMAPPED)
                is_field = key in fields or (
                    isinstance(parameters, BaseModel) and key in type(parameters).model_fields
                )
                return _resolve(item, parts if is_field else remaining)
            else:
                selected = _UNMAPPED
        return _resolve(selected, remaining)
    if key == "thickness" and hasattr(value, "x0") and hasattr(value, "x1"):
        return QuantityValue.model_validate(f"{value.x1.to('m') - value.x0.to('m'):.15g} m")
    if isinstance(value, BaseModel) and key in type(value).model_fields:
        return _resolve(getattr(value, key), remaining)
    parameters = getattr(value, "parameters", _UNMAPPED)
    if isinstance(parameters, BaseModel) and key in type(parameters).model_fields:
        return _resolve(getattr(parameters, key), remaining)
    if isinstance(value, dict) and key in value:
        return _resolve(value[key], remaining)
    return _UNMAPPED


def _candidates(value, parts):
    """Every value `parts` can denote when a list label may name any one of its records."""
    if not parts:
        yield value
        return
    key, *remaining = parts
    if isinstance(value, tuple | list) and not key.isdecimal():
        resolved = _resolve(value, [key])
        if resolved is not _UNMAPPED:
            yield from _candidates(resolved, remaining)
            return
        for item in value:
            yield from _candidates(item, parts)
            # Only skip the selector for items that carry no explicit identifier
            # contradicting it; entities with a non-matching id or location are absent.
            if (getattr(item, "id", _UNMAPPED) is _UNMAPPED
                    and getattr(item, "location", _UNMAPPED) is _UNMAPPED):
                yield from _candidates(item, remaining)
        return
    resolved = _resolve(value, [key])
    if resolved is not _UNMAPPED:
        yield from _candidates(resolved, remaining)


def _equal(actual, expected):
    if isinstance(actual, QuantityValue):
        try:
            quantity = QuantityValue.model_validate(expected)
        except ValueError:
            return False
        return quantity.is_compatible_with(actual.si_unit) and math.isclose(
            quantity.to(actual.si_unit), actual.magnitude_si, rel_tol=1e-12, abs_tol=0.0
        )
    if isinstance(actual, tuple | list):
        return (
            isinstance(expected, tuple | list)
            and len(actual) == len(expected)
            and all(_equal(a, b) for a, b in zip(actual, expected, strict=True))
        )
    if isinstance(actual, BaseModel) and isinstance(expected, dict):
        return all(
            key in type(actual).model_fields and _equal(getattr(actual, key), value)
            for key, value in expected.items()
        )
    return actual == expected


def plan_authority_issues(spec, intent, *, structured_paths=()):
    """Refuse changed typed inputs; never invent a mapping for free-text records."""
    issues = []
    unsupported = set(unsupported_physics_inputs(intent))
    locations = {
        field.path.removeprefix("contacts.").removesuffix(".location"): field.value
        for field in intent.fields
        if field.origin in {"researcher", "repository"}
        and field.path.startswith("contacts.")
        and field.path.endswith(".location")
        and isinstance(field.value, str)
    }
    for field in intent.fields:
        if field.origin not in {"researcher", "repository"}:
            continue
        parts = canonical_path(field.path, preserve_indices=True).split(".")
        if len(parts) > 1 and parts[0] == "contacts":
            parts[1] = locations.get(parts[1], parts[1])
        if parts == ["geometry", "length"]:
            length = max(r.x1.to("m") for r in spec.regions) - min(
                r.x0.to("m") for r in spec.regions
            )
            actual = QuantityValue.model_validate(f"{length:.15g} m")
        else:
            actual = _resolve(spec, parts)
        if field.path in unsupported:
            issues.append(
                {
                    "intent_path": field.path,
                    "reason": "unrepresentable_confirmed_physics_parameter",
                    "expected": field.value,
                }
            )
            continue
        # Existing checks own output coverage, display units and sampling policy.
        if (
            field.path in {"physics.models", "physics.equations", "observables", "display_units"}
            or field.path.startswith(("display_units.", "profile_sampling."))
        ):
            continue
        if actual is _UNMAPPED:
            if canonical_path(field.path) in structured_paths:
                continue
            # The model may label a record differently from the plan ("profiles.body.species"
            # against profile id "p_body"); the confirmed value is honored when some record holds it.
            if any(
                candidate is not _UNMAPPED and _equal(candidate, field.value)
                for candidate in _candidates(spec, parts)
            ):
                continue
            paths = [parts]
            if isinstance(field.value, dict):
                paths.extend([*parts, key] for key in field.value)
            if any(_schema_input_path(type(spec), path) for path in paths):
                issues.append(
                    {
                        "intent_path": field.path,
                        "reason": "missing_confirmed_input",
                        "expected": field.value,
                    }
                )
            continue
        if not _equal(actual, field.value):
            issues.append(
                {
                    "intent_path": field.path,
                    "reason": "changed_confirmed_input",
                    "expected": field.value,
                }
            )
    return issues
