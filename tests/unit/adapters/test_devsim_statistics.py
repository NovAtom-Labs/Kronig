"""Independent statistics references, including the native branch regression."""

import math

import pytest

from tcad_agent.adapters.devsim import runtime


def _quadrature(eta, *, derivative=False):
    # t=s^2 removes the square-root endpoint singularity of F_(1/2).
    count = 8192
    step = math.sqrt(max(eta, 0) + 80) / count

    def integrand(index):
        s = index * step
        delta = s * s - eta
        exponential = math.exp(-abs(delta))
        occupation = exponential / (1 + exponential) if delta >= 0 else 1 / (1 + exponential)
        if derivative:
            occupation *= 1 - occupation
        return 4 / math.sqrt(math.pi) * s * s * occupation

    return (
        step
        / 3
        * (
            integrand(0)
            + integrand(count)
            + 4 * math.fsum(integrand(i) for i in range(1, count, 2))
            + 2 * math.fsum(integrand(i) for i in range(2, count, 2))
        )
    )


def test_inverse_statistical_branches_join_without_density_or_fermi_energy_jump():
    breakpoint = 8.46296036621705
    left = runtime._inverse_fermi_ratio(breakpoint * (1 - 1e-10))
    right = runtime._inverse_fermi_ratio(breakpoint * (1 + 1e-10))
    assert abs(right - left) < 1e-8
    assert runtime._inverse_fermi_ratio(breakpoint) == pytest.approx(4.8405128292, abs=1e-10)


@pytest.mark.parametrize("eta", [-100, -20, -5, -1, 0, 2, 4.84, 7.06, 10, 35, 100])
def test_forward_statistics_agree_with_independent_normalized_fermi_integral(eta):
    ratio = runtime._fermi_ratio(eta)
    assert ratio == pytest.approx(_quadrature(eta), rel=0.0022)
    assert runtime._inverse_fermi_ratio(ratio) == pytest.approx(eta, abs=2e-12)


@pytest.mark.parametrize("eta", [-100, -20, -5, 0, 4.84, 10, 100])
def test_forward_statistics_are_positive_and_monotone_through_both_branches(eta):
    before = runtime._fermi_ratio(eta - 1e-5)
    after = runtime._fermi_ratio(eta + 1e-5)
    assert 0 < before < after


@pytest.mark.parametrize(
    "eta", [-100, -20, -5, -1, 0, 2, 4.83, 4.8405128292, 4.85, 7.06, 10, 35, 100]
)
def test_statistical_derivative_matches_independent_integral_not_only_its_own_inverse(eta):
    from tcad_agent.adapters.devsim.statistics import inverse_fermi_derivative

    actual = 1 / inverse_fermi_derivative(runtime._fermi_ratio(eta))
    assert actual == pytest.approx(_quadrature(eta, derivative=True), rel=0.0062)


@pytest.mark.parametrize("ratio", [0.0, -1.0, math.nan, math.inf])
def test_inverse_statistics_fail_closed_for_invalid_density_ratio(ratio):
    with pytest.raises(ValueError):
        runtime._inverse_fermi_ratio(ratio)
