import pytest
from pydantic import TypeAdapter, ValidationError

from tcad_agent.domain.studies import Study1D, expand_study_points

STUDY = TypeAdapter(Study1D)


def test_ac_at_explicit_bias_schedule_preserves_the_dependency():
    study = STUDY.validate_python(
        {
            "kind": "ac",
            "contact": "drive",
            "frequency": "1 MHz",
            "amplitude": "10 mV",
            "bias_schedule": {
                "kind": "dc",
                "contact": "drive",
                "start": "-1 V",
                "stop": "1 V",
                "step": "0.5 V",
            },
        }
    )
    assert [value.to("V") for value in expand_study_points(study.bias_schedule)] == [
        -1,
        -0.5,
        0,
        0.5,
        1,
    ]


def test_ac_bias_dependency_rejects_different_driven_contacts():
    with pytest.raises(ValidationError, match="same contact"):
        STUDY.validate_python(
            {
                "kind": "ac",
                "contact": "drive",
                "frequency": "1 MHz",
                "amplitude": "10 mV",
                "bias_schedule": {"kind": "dc_points", "contact": "other", "values": ["1 V"]},
            }
        )


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
            "contact": "gate",
            "waveform": "step",
            "initial_voltage": "0 V",
            "final_voltage": "1 V",
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


def test_transient_pulse_requires_a_complete_bounded_timing_contract() -> None:
    pulse = STUDY.validate_python(
        {
            "kind": "transient",
            "contact": "gate",
            "waveform": "pulse",
            "initial_voltage": "0 V",
            "final_voltage": "1 V",
            "start": "0 ns",
            "stop": "10 ns",
            "initial_step": "0.1 ns",
            "minimum_step": "1 ps",
            "maximum_step": "1 ns",
            "pulse_delay": "1 ns",
            "rise_time": "1 ns",
            "pulse_width": "4 ns",
            "fall_time": "1 ns",
            "maximum_retries": 5,
        }
    )

    assert pulse.waveform == "pulse"
    assert pulse.pulse_width.to("s") == pytest.approx(4e-9)
    assert pulse.minimum_step.to("s") == pytest.approx(1e-12)

    with pytest.raises(ValidationError, match="pulse_width"):
        STUDY.validate_python(
            {
                "kind": "transient",
                "contact": "gate",
                "waveform": "pulse",
                "initial_voltage": "0 V",
                "final_voltage": "1 V",
                "start": "0 ns",
                "stop": "10 ns",
                "initial_step": "0.1 ns",
                "maximum_step": "1 ns",
                "pulse_delay": "1 ns",
                "rise_time": "1 ns",
                "fall_time": "1 ns",
            }
        )
