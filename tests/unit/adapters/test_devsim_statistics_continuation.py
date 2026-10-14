"""Numerical initialization reaches full requested statistics, never a blend."""

from tcad_agent.adapters.devsim import runtime


def test_well_conditioned_statistics_initialization_does_not_repeat_fixed_small_steps():
    blends, events = [], []
    attempts = runtime.advance_fermi_blend(blends.append, lambda: True, events)
    assert blends == [1.0]
    assert attempts == 1
    assert events[-1]["blend"] == 1.0
    assert events[-1]["outcome"] == "converged"


def test_failed_full_statistics_seed_is_backtracked_then_reaches_full_physics():
    blends, events = [], []
    outcomes = iter([False, True, True])
    attempts = runtime.advance_fermi_blend(blends.append, lambda: next(outcomes), events)
    assert blends == [1.0, 0.5, 1.0]
    assert attempts == 3
    assert [event["outcome"] for event in events] == ["failed", "converged", "converged"]


def test_unresolvable_initialization_cannot_report_a_partial_statistics_model_as_complete():
    blends = []
    try:
        runtime.advance_fermi_blend(blends.append, lambda: False, [])
    except runtime.TransientRecoveryExhausted:
        pass
    else:
        raise AssertionError("Unresolved full-statistics initialization must fail")
    assert len(blends) <= 12
