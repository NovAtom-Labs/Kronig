"""Bounded continuation schedules independent of DEVSIM process state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SweepPoint:
    value: float
    state: Literal["converged", "failed"]
    attempts: int
    message: str | None = None


class AdaptiveSweep:
    def __init__(
        self,
        *,
        requested: tuple[float, ...],
        adaptive: bool,
        minimum_step: float,
        maximum_retries: int,
    ) -> None:
        if not requested:
            raise ValueError("sweep requires at least one requested point")
        if minimum_step <= 0:
            raise ValueError("minimum adaptive step must be positive")
        if maximum_retries < 0:
            raise ValueError("maximum retries must be nonnegative")
        self.requested = requested
        self.adaptive = adaptive
        self.minimum_step = minimum_step
        self.maximum_retries = maximum_retries

    def run(self, solve: Callable[[float], None]) -> tuple[SweepPoint, ...]:
        results: list[SweepPoint] = []
        current = 0.0
        for target in self.requested:
            requested_target = target
            attempts = 1
            try:
                solve(target)
            except Exception:
                if not self.adaptive:
                    results.append(
                        SweepPoint(
                            target,
                            "failed",
                            attempts,
                            "nonlinear solve did not converge",
                        )
                    )
                    continue
                converged = False
                retry = 0
                left = current
                right = requested_target
                while retry < self.maximum_retries:
                    retry += 1
                    midpoint = left + (right - left) / 2
                    if abs(midpoint - left) < self.minimum_step:
                        break
                    try:
                        solve(midpoint)
                    except Exception:
                        right = midpoint
                        continue
                    left = midpoint
                    try:
                        attempts += 1
                        solve(requested_target)
                    except Exception:
                        continue
                    converged = True
                    break
                if not converged:
                    results.append(
                        SweepPoint(
                            target,
                            "failed",
                            attempts,
                            "nonlinear solve did not converge",
                        )
                    )
                    continue
            current = target
            results.append(SweepPoint(target, "converged", attempts))
        return tuple(results)
