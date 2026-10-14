"""Conservation-row conditioning must not change other physical equations."""

import math

import pytest

from tcad_agent.adapters.devsim import density_solver


def test_conservation_replacement_retains_weak_source_without_rounded_transport_sum():
    ap, ai, ax = density_solver.replace_conservation_rows(
        [0, 2, 4],
        [0, 1, 0, 1],
        [1e7, -1e7, -1e7, 1e7],
        {1: {0: 1e-20, 1: 2e-20}},
    )
    assert list(ap) == [0, 2, 4]
    assert list(ai) == [0, 1, 0, 1]
    assert list(ax) == [1e7, 1e-20, -1e7, 2e-20]


def test_duplicate_csc_entries_are_summed_not_silently_overwritten():
    ap, ai, ax = density_solver.replace_conservation_rows(
        [0, 3, 4],
        [0, 0, 1, 1],
        [2.0, 3.0, -5.0, 5.0],
        {1: {0: 0.25, 1: 0.5}},
    )
    assert list(ap) == [0, 2, 3]
    assert list(ai) == [0, 1, 1]
    assert list(ax) == [5.0, 0.25, 0.5]


def test_empty_replacement_preserves_all_csc_entries():
    ap, ai, ax = density_solver.replace_conservation_rows([0, 1], [0], [2.0], {})
    assert list(ap) == [0, 1]
    assert list(ai) == [0]
    assert list(ax) == [2.0]


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_invalid_balance_coefficients_fail_closed(bad):
    with pytest.raises(ValueError):
        density_solver.replace_conservation_rows([0, 1], [0], [2.0], {0: {0: bad}})


def test_out_of_range_balance_row_or_column_is_not_written_into_solver_matrix():
    for rows in ({1: {0: 1.0}}, {0: {1: 1.0}}):
        with pytest.raises(ValueError):
            density_solver.replace_conservation_rows([0, 1], [0], [2.0], rows)


def test_strong_physical_pivot_avoids_minority_and_interface_constraint_rows():
    # Row 1 has the strongest diagonal but is an interface constraint and is
    # ineligible; row 0 is weak. Region/device names never enter this choice.
    pivot = density_solver.conservation_pivot(
        [0, 1, 2, 3],
        [0, 1, 2],
        [1e-20, 1e20, 100.0],
        [0, 2],
    )
    assert pivot == 2
