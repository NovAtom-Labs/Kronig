"""Axis-aligned rectangle geometry shared by validation and the structure builders.

``x`` is the stack (depth) axis of the one-dimensional model and ``y`` the lateral axis. All
values are metres. Nothing here knows about devices; it only places rectangles, their edges and
contact segments on them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tcad_agent.domain.models import Contact, Region2D

EPSILON = 1e-15


def bounds(region: Region2D) -> tuple[float, float, float, float]:
    """(x0, x1, y0, y1) of a region."""
    return (region.x0.to("m"), region.x1.to("m"), region.y0.to("m"), region.y1.to("m"))


def overlap(first: Region2D, second: Region2D) -> bool:
    ax0, ax1, ay0, ay1 = bounds(first)
    bx0, bx1, by0, by1 = bounds(second)
    return (
        ax0 < bx1 - EPSILON
        and bx0 < ax1 - EPSILON
        and ay0 < by1 - EPSILON
        and by0 < ay1 - EPSILON
    )


def contains(region: Region2D, x: float, y: float) -> bool:
    x0, x1, y0, y1 = bounds(region)
    return x0 + EPSILON < x < x1 - EPSILON and y0 + EPSILON < y < y1 - EPSILON


def shared_edge_length(first: Region2D, second: Region2D) -> float:
    """Length of the boundary two non-overlapping regions share (0 when they only touch)."""
    ax0, ax1, ay0, ay1 = bounds(first)
    bx0, bx1, by0, by1 = bounds(second)
    if abs(ax1 - bx0) < EPSILON or abs(bx1 - ax0) < EPSILON:
        return max(0.0, min(ay1, by1) - max(ay0, by0))
    if abs(ay1 - by0) < EPSILON or abs(by1 - ay0) < EPSILON:
        return max(0.0, min(ax1, bx1) - max(ax0, bx0))
    return 0.0


def contact_segment(
    contact: Contact, region: Region2D
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    """Start point, end point and outward normal of a contact segment.

    The segment lies on the side of ``region`` named by the contact location, optionally
    narrowed by ``span`` (coordinates along that side). The default is the whole side.
    """
    x0, x1, y0, y1 = bounds(region)
    side = str(contact.location)
    if side in {"x_min", "x_max"}:
        lo, hi = y0, y1
        at, normal = (x0, (-1.0, 0.0)) if side == "x_min" else (x1, (1.0, 0.0))
    else:
        lo, hi = x0, x1
        at, normal = (y0, (0.0, -1.0)) if side == "y_min" else (y1, (0.0, 1.0))
    if contact.span is not None:
        lo, hi = contact.span[0].to("m"), contact.span[1].to("m")
    if side in {"x_min", "x_max"}:
        return (at, lo), (at, hi), normal
    return (lo, at), (hi, at), normal


def segment_length(contact: Contact, region: Region2D) -> float:
    start, end, _ = contact_segment(contact, region)
    return abs(end[0] - start[0]) + abs(end[1] - start[1])


def segment_is_exposed(
    contact: Contact, region: Region2D, others: list[Region2D], step: float = 1e-12
) -> bool:
    """True when nothing else sits on the outer side of the whole contact segment."""
    start, end, normal = contact_segment(contact, region)
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        px = start[0] + fraction * (end[0] - start[0]) + normal[0] * step
        py = start[1] + fraction * (end[1] - start[1]) + normal[1] * step
        if any(contains(other, px, py) for other in others):
            return False
    return True
