import pytest
from pydantic import ValidationError

from tcad_agent.domain.models import PhysicsParameters, PhysicsSelection


def test_reviewed_advanced_physics_parameters_are_unit_checked() -> None:
    parameters = PhysicsParameters.model_validate(
        {
            "electron_lifetime": "10 ns",
            "hole_lifetime": "12 ns",
            "auger_electron_coefficient": "2.8e-31 cm^6/s",
            "auger_hole_coefficient": "9.9e-32 cm^6/s",
            "bgn_reference_energy": "9e-3 eV",
            "bgn_reference_density": "1e17 cm^-3",
        }
    )

    assert parameters.electron_lifetime.to("s") == pytest.approx(1.0e-8)
    assert parameters.auger_electron_coefficient.to("cm^6/s") == pytest.approx(2.8e-31)
    assert parameters.bgn_reference_energy.to("eV") == pytest.approx(9.0e-3)


def test_advanced_parameters_reject_wrong_dimensions() -> None:
    with pytest.raises(ValidationError, match="volume-squared per time"):
        PhysicsParameters.model_validate({"auger_electron_coefficient": "1 cm^3/s"})


def test_physics_selection_requires_parameters_only_for_selected_model() -> None:
    with pytest.raises(ValidationError, match="Auger parameters require the auger model"):
        PhysicsSelection.model_validate(
            {
                "equations": ["poisson"],
                "models": ["boltzmann"],
                "parameters": {"auger_electron_coefficient": "2.8e-31 cm^6/s"},
            }
        )
