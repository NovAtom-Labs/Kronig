import pytest
from pydantic import TypeAdapter, ValidationError

from tcad_agent.domain.studies import Study1D, expand_study_points

STUDY = TypeAdapter(Study1D)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "equilibrium"},
        {
            "kind": "dc",
            "contact": "left",
            "start": "-1 V",
            "stop": "1 V",
            "step": "0.1 V",
            "strategy": "adaptive",
            "minimum_step": "1 mV",
            "maximum_retries": 8,
        },
        {"kind": "dc_points", "contact": "left", "values": ["0 V", "1 V", "-1 V"]},
        {"kind": "ac", "contact": "gate", "frequency": "1 MHz", "amplitude": "10 mV"},
        {
            "kind": "frequency",
            "contact": "gate",
            "start": "1 kHz",
            "stop": "1 MHz",
            "points": 7,
            "spacing": "log",
            "amplitude": "10 mV",
        },
        {
            "kind": "transient",
            "start": "0 s",
            "stop": "1 ns",
            "initial_step": "1 ps",
            "maximum_step": "100 ps",
        },
        {"kind": "temperature", "values": ["250 K", "300 K", "350 K"]},
        {
            "kind": "parameter",
            "parameter_path": "profiles.channel.value",
            "values": ["1e15 cm^-3", "1e16 cm^-3"],
        },
    ],
)
def test_generic_study_contracts(payload: dict) -> None:
    assert STUDY.validate_python(payload).kind == payload["kind"]


def test_exact_dc_points_preserve_researcher_order() -> None:
    study = STUDY.validate_python(
        {"kind": "dc_points", "contact": "left", "values": ["0 V", "2 V", "-2 V"]}
    )

    assert [value.to("V") for value in expand_study_points(study)] == [0.0, 2.0, -2.0]


def test_exact_dc_points_can_request_bounded_adaptive_continuation() -> None:
    study = STUDY.validate_python(
        {
            "kind": "dc_points",
            "contact": "left",
            "values": ["0 V", "2 V", "0 V", "-2 V"],
            "strategy": "adaptive",
            "minimum_step": "10 mV",
            "maximum_retries": 12,
        }
    )

    assert study.strategy == "adaptive"
    assert study.minimum_step.to("V") == pytest.approx(0.01)


def test_frequency_expansion_is_logarithmic_and_bounded() -> None:
    study = STUDY.validate_python(
        {
            "kind": "frequency",
            "contact": "gate",
            "start": "1 kHz",
            "stop": "1 MHz",
            "points": 4,
            "spacing": "log",
            "amplitude": "10 mV",
        }
    )

    assert [value.to("Hz") for value in expand_study_points(study)] == pytest.approx(
        [1e3, 1e4, 1e5, 1e6]
    )


def test_study_rejects_unbounded_point_count() -> None:
    with pytest.raises(ValidationError, match="10000"):
        STUDY.validate_python(
            {
                "kind": "frequency",
                "contact": "gate",
                "start": "1 Hz",
                "stop": "1 GHz",
                "points": 10001,
                "spacing": "log",
                "amplitude": "10 mV",
            }
        )
