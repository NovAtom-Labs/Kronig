from pathlib import Path

import pytest
import yaml

from tcad_agent.domain.interfaces import Interface1D
from tcad_agent.domain.models import Contact, ExperimentSpec
from tcad_agent.domain.profiles import (
    ConstantProfile,
    ConstantTemperatureProfile,
    FixedChargeProfile,
)
from tcad_agent.domain.units import QuantityValue
from tcad_agent.validation.analytical import built_in_potential_reference


@pytest.mark.parametrize(
    "change",
    [
        "fermi",
        "slotboom_bgn",
        "metal",
        "offset",
        "extra_doping",
        "fixed_charge",
        "sheet_charge",
        "spatial_temperature",
    ],
)
def test_classical_neutral_bulk_reference_excludes_different_physical_assumptions(change):
    spec = ExperimentSpec.model_validate(
        yaml.safe_load(Path("examples/al-pn-al-equilibrium-devsim.yaml").read_text())
    )
    if change in {"fermi", "slotboom_bgn"}:
        models = tuple(m for m in spec.physics.models if change != "fermi" or m != "boltzmann")
        spec = spec.model_copy(
            update={"physics": spec.physics.model_copy(update={"models": (*models, change)})}
        )
    elif change == "metal":
        contact = Contact.model_validate(
            {
                "id": "anode",
                "location": "x_min",
                "kind": "metal_work_function",
                "work_function": "4.1 eV",
            }
        )
        spec = spec.model_copy(update={"contacts": (contact, spec.contacts[1])})
    elif change == "offset":
        spec = spec.model_copy(
            update={
                "contacts": (
                    spec.contacts[0].model_copy(
                        update={"voltage_offset": QuantityValue.model_validate("0.1 V")}
                    ),
                    spec.contacts[1],
                )
            }
        )
    elif change == "sheet_charge":
        interface = Interface1D.model_validate(
            {
                "id": "join",
                "left_region": "p_region",
                "right_region": "n_region",
                "fixed_charge_density": "1e10 cm^-2",
            }
        )
        spec = spec.model_copy(update={"interfaces": (interface,)})
    elif change == "spatial_temperature":
        temperature = ConstantTemperatureProfile.model_validate(
            {"kind": "constant", "region": "p_region", "value": "310 K"}
        )
        spec = spec.model_copy(
            update={
                "physics": spec.physics.model_copy(update={"temperature_profiles": (temperature,)})
            }
        )
    else:
        profile = (
            ConstantProfile.model_validate(
                {
                    "kind": "constant",
                    "region": "p_region",
                    "species": "donor",
                    "value": "1e16 cm^-3",
                }
            )
            if change == "extra_doping"
            else FixedChargeProfile.model_validate(
                {"kind": "fixed_charge", "region": "p_region", "density": "1 C/m^3"}
            )
        )
        spec = spec.model_copy(update={"profiles": (*spec.profiles, profile)})
    assert built_in_potential_reference(spec) is None
