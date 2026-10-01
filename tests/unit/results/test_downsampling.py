from tcad_agent.results.downsampling import extrema_preserving_indices


def test_extrema_downsampling_preserves_endpoints_and_spike() -> None:
    values = tuple(100.0 if index == 50 else float(index % 7) for index in range(101))

    indices = extrema_preserving_indices(values, max_points=20)

    assert indices[0] == 0
    assert indices[-1] == 100
    assert 50 in indices
    assert len(indices) <= 20


def test_downsampling_preserves_validity_transitions() -> None:
    values = tuple(float(index) for index in range(40))
    validity = tuple(not (10 <= index <= 14) for index in range(40))

    indices = extrema_preserving_indices(values, max_points=16, validity=validity)

    assert {9, 10, 14, 15}.issubset(indices)
