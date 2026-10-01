"""Bounded scientific downsampling that retains endpoints, extrema, and mask edges."""

from __future__ import annotations

import math


def extrema_preserving_indices(
    values: tuple[float, ...],
    *,
    max_points: int,
    validity: tuple[bool, ...] | None = None,
) -> tuple[int, ...]:
    if max_points < 4:
        raise ValueError("downsampling requires at least four output points")
    if validity is not None and len(validity) != len(values):
        raise ValueError("validity must match values")
    if not all(math.isfinite(value) for value in values):
        raise ValueError("downsampling accepts finite canonical values only")
    count = len(values)
    if count <= max_points:
        return tuple(range(count))

    required = {0, count - 1}
    if validity is not None:
        for index in range(1, count):
            if validity[index] != validity[index - 1]:
                required.update((index - 1, index))
    if len(required) > max_points:
        raise ValueError("point budget cannot preserve all validity transitions")

    remaining = max_points - len(required)
    candidates = [index for index in range(1, count - 1) if index not in required]
    if not candidates or remaining == 0:
        return tuple(sorted(required))
    bucket_count = max(1, remaining // 2)
    selected: set[int] = set(required)
    for bucket in range(bucket_count):
        start = bucket * len(candidates) // bucket_count
        stop = (bucket + 1) * len(candidates) // bucket_count
        chunk = candidates[start:stop]
        if not chunk:
            continue
        selected.add(min(chunk, key=lambda index: (values[index], index)))
        if len(selected) < max_points:
            selected.add(max(chunk, key=lambda index: (values[index], -index)))
    if len(selected) < max_points:
        for index in candidates:
            if index not in selected:
                selected.add(index)
                if len(selected) == max_points:
                    break
    return tuple(sorted(selected))
