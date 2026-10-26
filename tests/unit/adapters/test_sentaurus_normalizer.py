import json
from pathlib import Path

import pytest

from tcad_agent.adapters.sentaurus.normalizer import (
    SentaurusNormalizationError,
    SentaurusNormalizer,
)
from tcad_agent.runners.models import NativeRunResult

FIXTURE = Path("tests/fixtures/sentaurus/results/equilibrium_1d.json")


def native(path: Path) -> NativeRunResult:
    return NativeRunResult(
        backend="sentaurus",
        status="completed",
        return_code=0,
        stdout_path=path.parent / "stdout.log",
        stderr_path=path.parent / "stderr.log",
        result_path=path,
        elapsed_seconds=1.0,
    )


def mutate(tmp_path: Path, callback) -> Path:
    data = json.loads(FIXTURE.read_text())
    callback(data)
    path = tmp_path / "result.json"
    path.write_text(json.dumps(data))
    return path


def test_valid_result_is_normalized_to_si_units() -> None:
    result = SentaurusNormalizer().normalize(native(FIXTURE))
    assert result.status == "completed"
    assert result.simulator_version == "S-2024.03"
    assert result.fields["potential"].positions_m[-1] == pytest.approx(2.0e-6)
    assert result.fields["electric_field"].values[2] == pytest.approx(-1.25e6)
    assert result.fields["electron_density"].values[-1] == pytest.approx(1.0e23)
    assert result.bias_points[0].terminal_currents_a_per_m2["anode"] == pytest.approx(1.0e-12)


def test_missing_required_column_is_rejected(tmp_path: Path) -> None:
    path = mutate(tmp_path, lambda data: data["fields"]["potential"].pop("values"))
    with pytest.raises(SentaurusNormalizationError, match="invalid schema"):
        SentaurusNormalizer().normalize(native(path))


@pytest.mark.parametrize(
    "positions, message",
    [([0.0, 0.5, 0.5, 1.5, 2.0], "duplicate"), ([0.0, 1.0, 0.5, 1.5, 2.0], "monotonic")],
)
def test_invalid_coordinates_are_rejected(
    tmp_path: Path, positions: list[float], message: str
) -> None:
    path = mutate(
        tmp_path,
        lambda data: data["fields"]["potential"].update({"position": positions}),
    )
    with pytest.raises(SentaurusNormalizationError, match=message):
        SentaurusNormalizer().normalize(native(path))


def test_non_finite_value_is_rejected(tmp_path: Path) -> None:
    path = mutate(
        tmp_path,
        lambda data: data["fields"]["potential"]["values"].__setitem__(2, float("nan")),
    )
    with pytest.raises(SentaurusNormalizationError, match="finite"):
        SentaurusNormalizer().normalize(native(path))


def test_exact_simulator_version_is_required(tmp_path: Path) -> None:
    path = mutate(tmp_path, lambda data: data.update({"simulator_version": ""}))
    with pytest.raises(SentaurusNormalizationError, match="invalid schema"):
        SentaurusNormalizer().normalize(native(path))


def test_legacy_density_with_voltage_unit_is_rejected(tmp_path):
    path = mutate(tmp_path, lambda data: data["fields"]["electron_density"].update(unit="V"))
    with pytest.raises(SentaurusNormalizationError, match="unit"):
        SentaurusNormalizer().normalize(native(path))


def test_legacy_unknown_terminal_is_rejected(tmp_path):
    path = mutate(
        tmp_path, lambda data: data["bias_points"][0]["terminal_current_density"].update(ghost=1)
    )
    with pytest.raises(SentaurusNormalizationError, match="terminal"):
        SentaurusNormalizer().normalize(native(path))
