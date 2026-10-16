"""Compare typed researcher inputs to simulator-neutral plan fields.

This checks schema-addressable inputs, not the truth of arbitrary free text.
Unmapped intent remains available for model reasoning and researcher plan review.
"""

import math
import re
from typing import Annotated, get_args, get_origin

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
                if getattr(item, "id", None) == key
                or (boundary and getattr(item, "location", None) == boundary)
            ]
            selected = matches[0] if len(matches) == 1 else _UNMAPPED
        return _resolve(selected, remaining)
    if key == "thickness" and hasattr(value, "x0") and hasattr(value, "x1"):
        return QuantityValue.model_validate(f"{value.x1.to('m') - value.x0.to('m'):.15g} m")
    if isinstance(value, BaseModel) and key in type(value).model_fields:
        return _resolve(getattr(value, key), remaining)
    parameters = getattr(value, "parameters", None)
    if isinstance(parameters, BaseModel) and key in type(parameters).model_fields:
        return _resolve(getattr(parameters, key), remaining)
    if isinstance(value, dict) and key in value:
        return _resolve(value[key], remaining)
    return _UNMAPPED


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


def plan_authority_issues(spec, intent):
    """Refuse changed typed inputs; never invent a mapping for free-text records."""
    issues = []
    unsupported = set(unsupported_physics_inputs(intent))
    for field in intent.fields:
        if field.origin not in {"researcher", "repository"}:
            continue
        parts = canonical_path(field.path, preserve_indices=True).split(".")
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
        # Physics/output set coverage and display/profile policies already have
        # their dedicated checks; order there is not scientific identity.
        if (
            actual is _UNMAPPED
            or field.path in {"physics.models", "physics.equations", "observables", "display_units"}
            or field.path.startswith(("display_units.", "profile_sampling."))
        ):
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
