"""Allowlisted profile evaluation and expression construction."""

from __future__ import annotations

import bisect
import math

from tcad_agent.adapters.devsim.payload import (
    ConstantProfilePayload,
    ErrorFunctionProfilePayload,
    GaussianProfilePayload,
    LinearProfilePayload,
    ProfilePayload,
    RegionPayload,
    TabulatedProfilePayload,
)


def evaluate_profile(profile: ProfilePayload, region: RegionPayload, x_cm: float) -> float:
    if isinstance(profile, ConstantProfilePayload):
        return profile.value_cm3
    if isinstance(profile, LinearProfilePayload):
        fraction = (x_cm - region.x0_cm) / (region.x1_cm - region.x0_cm)
        return profile.start_value_cm3 + fraction * (
            profile.end_value_cm3 - profile.start_value_cm3
        )
    if isinstance(profile, GaussianProfilePayload):
        normalized = (x_cm - profile.center_cm) / profile.standard_deviation_cm
        return profile.peak_cm3 * math.exp(-0.5 * normalized * normalized)
    if isinstance(profile, ErrorFunctionProfilePayload):
        normalized = (x_cm - profile.junction_position_cm) / profile.characteristic_length_cm
        fraction = 0.5 * math.erfc(normalized)
        if profile.orientation == "increasing_x":
            fraction = 1.0 - fraction
        return profile.surface_value_cm3 * fraction
    if isinstance(profile, TabulatedProfilePayload):
        index = bisect.bisect_right(profile.positions_cm, x_cm)
        if index == 0:
            return profile.values_cm3[0]
        if index >= len(profile.positions_cm):
            return profile.values_cm3[-1]
        if profile.interpolation == "nearest":
            left = index - 1
            right = index
            if x_cm - profile.positions_cm[left] <= profile.positions_cm[right] - x_cm:
                return profile.values_cm3[left]
            return profile.values_cm3[right]
        left = index - 1
        right = index
        fraction = (x_cm - profile.positions_cm[left]) / (
            profile.positions_cm[right] - profile.positions_cm[left]
        )
        return profile.values_cm3[left] + fraction * (
            profile.values_cm3[right] - profile.values_cm3[left]
        )
    raise TypeError(f"unsupported profile payload: {type(profile).__name__}")


def devsim_expression(profile: ProfilePayload, region: RegionPayload) -> str:
    """Build an expression only from validated numeric payload values."""
    if isinstance(profile, ConstantProfilePayload):
        return f"{profile.value_cm3:.17g}"
    if isinstance(profile, LinearProfilePayload):
        fraction = f"((x-{region.x0_cm:.17g})/{(region.x1_cm - region.x0_cm):.17g})"
        return (
            f"{profile.start_value_cm3:.17g}+{fraction}*"
            f"{(profile.end_value_cm3 - profile.start_value_cm3):.17g}"
        )
    if isinstance(profile, GaussianProfilePayload):
        return (
            f"{profile.peak_cm3:.17g}*exp(-0.5*((x-{profile.center_cm:.17g})/"
            f"{profile.standard_deviation_cm:.17g})^2)"
        )
    if isinstance(profile, ErrorFunctionProfilePayload):
        argument = (
            f"((x-{profile.junction_position_cm:.17g})/{profile.characteristic_length_cm:.17g})"
        )
        base = f"0.5*erfc{argument}"
        if profile.orientation == "increasing_x":
            base = f"(1-({base}))"
        return f"{profile.surface_value_cm3:.17g}*({base})"
    if isinstance(profile, TabulatedProfilePayload):
        expression = f"{profile.values_cm3[-1]:.17g}"
        for index in range(len(profile.positions_cm) - 2, -1, -1):
            x0 = profile.positions_cm[index]
            x1 = profile.positions_cm[index + 1]
            y0 = profile.values_cm3[index]
            y1 = profile.values_cm3[index + 1]
            if profile.interpolation == "nearest":
                boundary = (x0 + x1) / 2
                segment = f"{y0:.17g}"
            else:
                boundary = x1
                segment = f"{y0:.17g}+(x-{x0:.17g})*{((y1 - y0) / (x1 - x0)):.17g}"
            expression = f"ifelse(x < {boundary:.17g}, {segment}, {expression})"
        return expression
    raise TypeError(f"unsupported profile payload: {type(profile).__name__}")
