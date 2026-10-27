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


# Intent vocabulary that names a typed field differently (a profile cut is "at" a depth).
_FIELD_ALIASES = {"depth": "at"}


def _resolve(value, parts):
    if not parts:
        return value
    key, *remaining = parts
    if isinstance(value, BaseModel):
        fields = type(value).model_fields
        if key not in fields and _FIELD_ALIASES.get(key) in fields:
            key = _FIELD_ALIASES[key]
        elif key == "extents" and "x0" in fields and "x1" in fields:
            if not remaining:
                return value
            extents = {"x_min": value.x0, "x_max": value.x1}
            return _resolve(extents, remaining)
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
                is_field = key in fields or _FIELD_ALIASES.get(key) in fields or key in {"extents", "thickness"} or (
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
    if isinstance(actual, dict) and isinstance(expected, dict):
        return all(key in actual and _equal(actual[key], value) for key, value in expected.items())
    if isinstance(actual, BaseModel) and isinstance(expected, dict):
        return all(
            _record_field_equal(actual, key, value)
            for key, value in expected.items()
            if key != "id"  # a record's label names it; it carries no scientific value
        )
    return actual == expected


# Intent vocabulary for a record's fields, where the spec stores them under another name.
_RECORD_ALIASES = {
    "profile": "kind",
    "concentration": "value",
    "x_min": "x0",
    "x_max": "x1",
    "x_depth_min": "x0",
    "x_depth_max": "x1",
    "y_min": "y0",
    "y_max": "y1",
    "y_lateral_min": "y0",
    "y_lateral_max": "y1",
}


# A dopant named by element fixes the doping type, so "boron" confirms an acceptor profile.
_DOPANT_TYPES = {
    **dict.fromkeys(("boron", "aluminum", "aluminium", "gallium", "indium"), "acceptor"),
    **dict.fromkeys(("phosphorus", "arsenic", "antimony", "bismuth"), "donor"),
}


def _strip_owner(key):
    """A key like "region_thickness" names that field of the record's owner."""
    for prefix in ("region_", "profile_"):
        if key.startswith(prefix) and key != prefix:
            return key.removeprefix(prefix)
    return key


def _record_field_equal(record, key, expected):
    fields = type(record).model_fields
    if key not in fields:
        key = _strip_owner(key)
    if key == "thickness" and "x0" in fields and "x1" in fields:
        return _equal(_resolve(record, ["thickness"]), expected)
    if key == "type" and "type" not in fields:
        # "constant" names the profile kind, "donor"/"acceptor" its species.
        target = "kind" if str(expected) in {"constant", "box", "gaussian"} else "species"
        return target in fields and _equal(getattr(record, target), expected)
    if key == "species" and isinstance(expected, str):
        expected = _DOPANT_TYPES.get(expected.lower(), expected)
    key = key if key in fields else _RECORD_ALIASES.get(key, key)
    return key in fields and _equal(getattr(record, key), expected)


def _holds_records(records, value, label=None):
    """True when the spec's records hold every record (or one id-keyed record set) in value."""
    if not isinstance(records, tuple | list):
        return False
    if isinstance(value, dict) and value and all(isinstance(v, dict) for v in value.values()):
        # {"silicon": {...}}: each key labels one record, a lone record being unambiguous.
        def held(label, wanted):
            matches = [r for r in records if getattr(r, "id", None) == label]
            return any(_equal(r, wanted) for r in (matches or records if len(records) == 1 else matches))

        return all(held(label, wanted) for label, wanted in value.items())
    if isinstance(value, dict):
        # A bare record only speaks for the collection when the path names a field, not an
        # entity ("profiles.parameters", never "contacts.gate"): a missing entity stays refused.
        names = {"parameters", "extents", *(type(records[0]).model_fields if records else ())}
        return label in names and any(_equal(record, value) for record in records)
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) for item in value)
        and all(any(_equal(record, item) for record in records) for item in value)
    )


def _holds_records_composite(regions, profiles, value):
    """Verify a confirmed dict that bundles region geometry and profile doping keys.

    A composite confirmed input such as ``regions.parameters = {concentration, profile,
    species, thickness}`` mixes fields from two spec collections.  Neither a Region1D
    alone nor a doping profile alone carries all four keys, so a single
    ``_holds_records`` call against one collection always fails.  This helper partitions
    the dict keys by which collection model recognises them and verifies each partition
    against the appropriate collection independently.
    """
    if not isinstance(value, dict) or not regions or not profiles:
        return False
    value = {_strip_owner(key): item for key, item in value.items()}
    r_model = type(regions[0])
    r_direct = set(r_model.model_fields) | {"thickness", "extents"}
    r_aliased = {k for k, v in _RECORD_ALIASES.items() if v in r_model.model_fields}
    r_keys = {k: v for k, v in value.items() if k != "id" and k in r_direct | r_aliased}
    s_keys = {k: v for k, v in value.items() if k != "id" and k not in r_keys}
    if not s_keys:
        # Nothing to split; the primary _holds_records call already handled this.
        return False
    r_ok = not r_keys or any(
        all(_record_field_equal(r, k, v) for k, v in r_keys.items()) for r in regions
    )
    s_ok = any(
        all(_record_field_equal(p, k, v) for k, v in s_keys.items()) for p in profiles
    )
    return r_ok and s_ok


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
            primary_col = getattr(spec, parts[0], None)
            label = parts[1] if len(parts) == 2 else None
            if _holds_records(primary_col, field.value, label) or (
                # A composite confirmed record (e.g. regions.parameters) may bundle
                # region geometry (thickness) with doping profile properties
                # (concentration, species, profile kind).  Verify each partition
                # against its own collection.
                parts[0] in {"regions", "profiles"}
                and isinstance(field.value, dict)
                and label is not None
                and _holds_records_composite(spec.regions, spec.profiles, field.value)
            ):
                # Confirmed records are honored when the spec's own records hold every one.
                continue
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
