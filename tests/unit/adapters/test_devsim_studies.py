import pytest

from tcad_agent.adapters.devsim.studies import AdaptiveSweep, SweepPoint


def test_fixed_sweep_preserves_exact_requested_order_and_failures() -> None:
    def solve(value: float) -> None:
        if abs(value) == 2.0:
            raise RuntimeError("did not converge")

    points = AdaptiveSweep(
        requested=(0.0, 2.0, -2.0),
        adaptive=False,
        minimum_step=0.1,
        maximum_retries=0,
    ).run(solve)

    assert [(point.value, point.state) for point in points] == [
        (0.0, "converged"),
        (2.0, "failed"),
        (-2.0, "failed"),
    ]


def test_adaptive_sweep_inserts_internal_points_but_returns_requested_points_only() -> None:
    solved: list[float] = []

    def solve(value: float) -> None:
        previous = solved[-1] if solved else 0.0
        if abs(value - previous) > 0.51:
            raise RuntimeError("step too large")
        solved.append(value)

    points = AdaptiveSweep(
        requested=(0.0, 1.0),
        adaptive=True,
        minimum_step=0.1,
        maximum_retries=8,
    ).run(solve)

    assert points == (
        SweepPoint(value=0.0, state="converged", attempts=1),
        SweepPoint(value=1.0, state="converged", attempts=2),
    )
    assert 0.5 in solved


def test_adaptive_sweep_is_bounded_and_preserves_failed_target() -> None:
    def never(_: float) -> None:
        raise RuntimeError("no convergence")

    points = AdaptiveSweep(
        requested=(1.0,),
        adaptive=True,
        minimum_step=0.2,
        maximum_retries=3,
    ).run(never)

    assert points[0].state == "failed"
    assert points[0].attempts <= 4
    assert points[0].message == "nonlinear solve did not converge"


def test_invalid_adaptive_budget_is_rejected() -> None:
    with pytest.raises(ValueError, match="minimum"):
        AdaptiveSweep(
            requested=(0.0, 1.0),
            adaptive=True,
            minimum_step=0.0,
            maximum_retries=3,
        )
