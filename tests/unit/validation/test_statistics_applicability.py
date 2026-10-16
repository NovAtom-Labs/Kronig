import pytest

from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.statistics import statistics_checks


def test_mandatory_diagnostic_samples_cannot_be_skipped_into_a_pass():
    result = evidence(0.001, validity=(True, False))
    result = result.model_copy(
        update={"metadata": {**result.metadata, "validation_evidence_version": "1"}}
    )
    assert statistics_checks(result)[0].status == "failed"


def test_new_diagnostic_version_missing_density_of_states_fails_closed():
    result = evidence(0.001)
    datasets = dict(result.datasets)
    del datasets["effective_density_conduction"]
    result = result.model_copy(
        update={
            "datasets": datasets,
            "metadata": {**result.metadata, "validation_evidence_version": "1"},
        }
    )
    assert statistics_checks(result)[0].status == "failed"


def evidence(ratio, *, models=("boltzmann",), validity=None):
    axis = ScientificAxis(id="x", kind="position", label="Position", unit="m", values=(0, 1))
    datasets = {}
    for name, values in (
        ("electron_density", (ratio * 10, ratio * 10)),
        ("hole_density", (0.01, 0.01)),
        ("effective_density_conduction", (10, 10)),
        ("effective_density_valence", (10, 10)),
    ):
        datasets[name] = Dataset(
            id=name,
            label=name,
            unit="m^-3",
            axes=("x",),
            shape=(2,),
            values=values,
            validity=validity,
        )
    return CanonicalResult(
        backend="devsim",
        status="completed",
        axes={"x": axis},
        datasets=datasets,
        metadata={"physics_models": list(models)},
    )


@pytest.mark.parametrize("ratio,status", [(0.001, "passed"), (0.5, "failed"), (10, "failed")])
def test_boltzmann_domain_uses_solved_density_not_doping(ratio, status):
    check = statistics_checks(evidence(ratio))[0]
    assert check.status == status
    assert check.measured_value == pytest.approx(ratio)


def test_fermi_does_not_claim_boltzmann_applicability():
    check = statistics_checks(evidence(10, models=("fermi",)))[0]
    assert check.status == "not_applicable"
    assert "Fermi" in check.message


def test_invalid_samples_cannot_prove_statistics_suitability():
    assert statistics_checks(evidence(0.001, validity=(False, False)))[0].status == "not_applicable"


def test_missing_density_of_states_is_not_a_pass():
    result = evidence(0.001)
    datasets = dict(result.datasets)
    del datasets["effective_density_valence"]
    assert (
        statistics_checks(result.model_copy(update={"datasets": datasets}))[0].status
        == "not_applicable"
    )
