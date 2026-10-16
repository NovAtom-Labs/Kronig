"""Dimension-checked display transformations; canonical evidence remains SI."""

import math

from tcad_agent.domain.units import UNIT_REGISTRY
from tcad_agent.results.models import CanonicalResult


def display_projection(
    result: CanonicalResult, requested: dict[str, str], *, allow_missing: bool = False
) -> dict[str, dict]:
    projections = {}
    matched = set()
    for name, dataset in result.datasets.items():
        selector = name if name in requested else name.split("__", 1)[0]
        if selector not in requested:
            continue
        target = requested[selector]
        try:
            zero = float(UNIT_REGISTRY.Quantity(0, dataset.unit).to(target).magnitude)
            one = float(UNIT_REGISTRY.Quantity(1, dataset.unit).to(target).magnitude)
        except Exception as exc:
            raise ValueError(
                f"Display unit {target!r} is incompatible with {name} ({dataset.unit}); "
                "unit conversion cannot supply physical area."
            ) from exc
        if not all(math.isfinite(v) for v in (zero, one)):
            raise ValueError("Display conversion must be finite")
        if dataset.imaginary_values is not None and zero != 0:
            raise ValueError("Complex responses require multiplicative display units")
        matched.add(selector)
        projections[name] = {
            "unit": target,
            "canonical_unit": dataset.unit,
            "scale": one - zero,
            "offset": zero,
            "source": "dimension_checked:pint",
        }
    if (missing := requested.keys() - matched) and not allow_missing:
        raise ValueError(f"Requested display quantities are unavailable: {sorted(missing)}")
    return projections


def display_values(dataset, projection: dict | None):
    if projection is None:
        return dataset.values, dataset.unit
    return tuple(
        v * projection["scale"] + projection["offset"] for v in dataset.values
    ), projection["unit"]
