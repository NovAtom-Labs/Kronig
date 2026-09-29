import pytest

from tcad_agent.adapters.devsim.runtime import (
    AdaptiveStepController,
    TransientRecoveryExhausted,
    waveform_voltage,
)


def test_pulse_waveform_has_explicit_rise_hold_and_fall() -> None:
    study = {
        "waveform": "pulse",
        "initial_voltage_v": 0.0,
        "final_voltage_v": 2.0,
        "start_s": 0.0,
        "stop_s": 10.0,
        "pulse_delay_s": 1.0,
        "rise_time_s": 2.0,
        "pulse_width_s": 3.0,
        "fall_time_s": 2.0,
    }

    assert waveform_voltage(study, 0.5) == pytest.approx(0.0)
    assert waveform_voltage(study, 2.0) == pytest.approx(1.0)
    assert waveform_voltage(study, 4.0) == pytest.approx(2.0)
    assert waveform_voltage(study, 7.0) == pytest.approx(1.0)
    assert waveform_voltage(study, 9.0) == pytest.approx(0.0)


def test_failed_transient_step_is_reduced_without_advancing_time() -> None:
    controller = AdaptiveStepController(
        initial_step=1.0,
        minimum_step=0.125,
        maximum_step=2.0,
        maximum_retries=3,
    )

    assert controller.candidate(10.0) == pytest.approx(1.0)
    assert controller.failed() == pytest.approx(0.5)
    assert controller.candidate(10.0) == pytest.approx(0.5)
    controller.succeeded()
    assert controller.candidate(10.0) == pytest.approx(0.75)


def test_transient_recovery_refuses_steps_below_the_reviewed_minimum() -> None:
    controller = AdaptiveStepController(
        initial_step=0.25,
        minimum_step=0.125,
        maximum_step=1.0,
        maximum_retries=1,
    )

    controller.failed()
    with pytest.raises(TransientRecoveryExhausted):
        controller.failed()
