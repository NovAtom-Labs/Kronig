"""Registered portable sweep targets with explicit units and dependencies."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RegisteredParameter:
    path: str
    unit: str
    payload_field: str
    required_model: str | None = None


REGISTERED_PARAMETERS = {
    item.path: item
    for item in (
        RegisteredParameter(
            "physics.parameters.electron_lifetime",
            "s",
            "electron_lifetime_s",
            "srh",
        ),
        RegisteredParameter(
            "physics.parameters.hole_lifetime",
            "s",
            "hole_lifetime_s",
            "srh",
        ),
        RegisteredParameter(
            "physics.parameters.auger_electron_coefficient",
            "cm^6/s",
            "auger_electron_cm6_s",
            "auger",
        ),
        RegisteredParameter(
            "physics.parameters.auger_hole_coefficient",
            "cm^6/s",
            "auger_hole_cm6_s",
            "auger",
        ),
        RegisteredParameter(
            "physics.parameters.bgn_reference_energy",
            "eV",
            "bgn_reference_energy_ev",
            "slotboom_bgn",
        ),
        RegisteredParameter(
            "physics.parameters.bgn_reference_density",
            "cm^-3",
            "bgn_reference_density_cm3",
            "slotboom_bgn",
        ),
    )
}
