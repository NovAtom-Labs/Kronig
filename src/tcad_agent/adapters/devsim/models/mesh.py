"""Deterministic mesh-tag generation."""

from tcad_agent.adapters.devsim.payload import RegionPayload


def boundary_tag(index: int, region_count: int) -> str:
    if index == 0:
        return "x_min"
    if index == region_count:
        return "x_max"
    return f"boundary_{index}"


def region_tags(index: int, regions: tuple[RegionPayload, ...]) -> tuple[str, str]:
    return boundary_tag(index, len(regions)), boundary_tag(index + 1, len(regions))
