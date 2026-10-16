"""Names and dimensions of portable result presentation quantities."""

from tcad_agent.domain.units import UNIT_REGISTRY

# These are public quantity aliases, not device or prompt classifications.
QUANTITY_ALIASES = {
    "capacitance_density": "capacitance",
    "ac_capacitance_density": "ac_capacitance",
    "electron_concentration": "electron_density",
    "hole_concentration": "hole_density",
    "electrostatic_potential": "potential",
}

# Public quantity groups are expanded into individual canonical fields. They
# cannot infer area, new observables, or experimental parameters.
QUANTITY_GROUPS = {
    "carrier_density": ("electron_density", "hole_density"),
    "carrier_concentration": ("electron_density", "hole_density"),
}

QUANTITY_UNITS = {
    **dict.fromkeys(("capacitance", "ac_capacitance"), "F/m^2"),
    **dict.fromkeys(("absolute_capacitance", "absolute_ac_capacitance"), "F"),
    **dict.fromkeys(
        (
            "electron_density",
            "hole_density",
            "net_doping",
            "donor_concentration",
            "acceptor_concentration",
            "effective_intrinsic_carrier_concentration",
            "effective_density_conduction",
            "effective_density_valence",
        ),
        "m^-3",
    ),
    "potential": "V",
    "electric_field": "V/m",
    "electrostatic_flux": "C/m^2",
    "charge_density": "C/m^3",
    "fixed_charge_density": "C/m^3",
    **dict.fromkeys(("terminal_charge", "interface_charge_density"), "C/m^2"),
    "absolute_terminal_charge": "C",
    "lattice_temperature": "K",
    **dict.fromkeys(
        (
            "conduction_band",
            "valence_band",
            "fermi_level",
            "intrinsic_energy",
            "electron_affinity",
            "band_gap",
            "band_gap_narrowing",
            "electron_quasi_fermi_level",
            "hole_quasi_fermi_level",
        ),
        "eV",
    ),
    **dict.fromkeys(
        (
            "terminal_current",
            "terminal_current_density",
            "terminal_electron_current",
            "terminal_hole_current",
            "electron_current_density",
            "hole_current_density",
            "electron_drift_current_density",
            "electron_diffusion_current_density",
            "hole_drift_current_density",
            "hole_diffusion_current_density",
            "current_decomposition_residual",
            "total_current_density",
            "ac_current",
        ),
        "A/m^2",
    ),
    "absolute_terminal_current": "A",
    "complex_admittance": "S/m^2",
    "ac_conductance": "S/m^2",
    **dict.fromkeys(("electron_mobility", "hole_mobility"), "m^2/V/s"),
    **dict.fromkeys(
        (
            "recombination_rate",
            "srh_recombination_rate",
            "auger_recombination_rate",
            "total_recombination_rate",
            "electron_generation_rate",
            "hole_generation_rate",
        ),
        "m^-3/s",
    ),
    "surface_recombination_rate": "m^-2/s",
    "interface_trap_occupancy": "1",
}


def normalize_display_units(units: dict[str, str]) -> dict[str, str]:
    normalized = {}
    for name, unit in units.items():
        root, sep, contact = name.partition("__")
        roots = QUANTITY_GROUPS.get(root, (QUANTITY_ALIASES.get(root, root),))
        for canonical_root in roots:
            key = canonical_root + sep + contact
            if canonical_root not in QUANTITY_UNITS:
                raise ValueError(f"Unknown display quantity: {name}")
            try:
                UNIT_REGISTRY.Quantity(1, QUANTITY_UNITS[canonical_root]).to(unit)
            except Exception as exc:
                raise ValueError(
                    f"Display unit {unit} is incompatible with {canonical_root}"
                ) from exc
            if key in normalized:
                # Aliases must refer to the same display unit, not just dimensions.
                conversion = UNIT_REGISTRY.Quantity(1, unit).to(normalized[key])
                zero = UNIT_REGISTRY.Quantity(0, unit).to(normalized[key])
                if conversion.magnitude != 1 or zero.magnitude != 0:
                    raise ValueError(f"Conflicting display units for {key}")
            normalized[key] = unit
    return normalized
