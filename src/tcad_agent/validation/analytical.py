"""Narrow analytical references used only when their assumptions are explicit."""

from __future__ import annotations

import math
from dataclasses import dataclass

from tcad_agent.domain.models import EquilibriumStudy, ExperimentSpec, ProfileSpecies
from tcad_agent.domain.profiles import ConstantProfile

_BOLTZMANN_OVER_CHARGE_V_PER_K = 8.617333262145e-5
_SILICON_INTRINSIC_DENSITY_CM3_AT_300_K = 1.0e10


@dataclass(frozen=True)
class BuiltInPotentialReference:
    value_v: float
    source: str


def built_in_potential_reference(
    spec: ExperimentSpec,
) -> BuiltInPotentialReference | None:
    """Return the abrupt silicon p-n reference only when all assumptions hold."""
    if not isinstance(spec.study, EquilibriumStudy):
        return None
    # This classical neutral-bulk reference is not a reference for metal
    # barriers, narrowed/degenerate bands, imposed charge or biased contacts.
    # A global potential range in those studies need not equal junction Vbi.
    if "fermi" in spec.physics.models or "slotboom_bgn" in spec.physics.models:
        return None
    if spec.physics.temperature_profiles or len(spec.profiles) != 2:
        return None
    if len(spec.contacts) != 2 or any(
        str(contact.kind) != "ohmic" or contact.voltage_offset.to("V") != 0
        for contact in spec.contacts
    ):
        return None
    if any(
        interface.fixed_charge_density is not None or interface.trap_density is not None
        for interface in spec.interfaces
    ):
        return None
    if len(spec.regions) != 2:
        return None
    if any(region.material.lower() != "silicon" for region in spec.regions):
        return None
    temperature_k = spec.physics.temperature.to("K")
    if not math.isclose(temperature_k, 300.0, abs_tol=1.0e-9):
        return None

    acceptors = [
        profile
        for profile in spec.profiles
        if isinstance(profile, ConstantProfile) and profile.species is ProfileSpecies.ACCEPTOR
    ]
    donors = [
        profile
        for profile in spec.profiles
        if isinstance(profile, ConstantProfile) and profile.species is ProfileSpecies.DONOR
    ]
    if len(acceptors) != 1 or len(donors) != 1:
        return None
    if acceptors[0].region == donors[0].region:
        return None

    acceptor_cm3 = acceptors[0].value.to("cm^-3")
    donor_cm3 = donors[0].value.to("cm^-3")
    ratio = acceptor_cm3 * donor_cm3 / (_SILICON_INTRINSIC_DENSITY_CM3_AT_300_K**2)
    if ratio <= 1.0:
        return None
    return BuiltInPotentialReference(
        value_v=(_BOLTZMANN_OVER_CHARGE_V_PER_K * temperature_k * math.log(ratio)),
        source="silicon-registry-1.0:abrupt-pn-equilibrium",
    )
