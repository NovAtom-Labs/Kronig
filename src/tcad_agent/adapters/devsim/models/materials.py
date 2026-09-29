"""Reviewed backend material mapping and pinned silicon parameters.

The values are copied into every compiled payload so a run does not depend on
ambient DEVSIM defaults. The identifier is preserved as provenance and is
versioned whenever any value or equation changes.
"""

DEVSIM_MATERIAL_NAMES = {
    "silicon": "Si",
    "silicon_dioxide": "Ox",
    "generic_dielectric": "Ox",
}
MATERIAL_CLASSES = {
    "silicon": "semiconductor",
    "silicon_dioxide": "dielectric",
    "generic_dielectric": "dielectric",
}

SILICON_PARAMETER_SET_ID = "novatom.silicon.baseline.2026-09-29.v1"
SILICON_PARAMETER_SOURCES = {
    "electron_affinity_ev": {
        "source": "Agent Kronig reviewed silicon baseline",
        "version": "2026-09-29.v1",
    },
    "band_gap_ev": {
        "source": "Agent Kronig reviewed silicon baseline",
        "version": "2026-09-29.v1",
    },
    "effective_density_conduction_cm3": {
        "source": "Agent Kronig reviewed silicon baseline",
        "version": "2026-09-29.v1",
    },
    "effective_density_valence_cm3": {
        "source": "Agent Kronig reviewed silicon baseline",
        "version": "2026-09-29.v1",
    },
    "electron_lifetime_s": {
        "source": "Agent Kronig reviewed simulation baseline",
        "version": "2026-09-29.v1",
    },
    "hole_lifetime_s": {
        "source": "Agent Kronig reviewed simulation baseline",
        "version": "2026-09-29.v1",
    },
    "auger_electron_cm6_s": {
        "source": "Agent Kronig reviewed silicon baseline",
        "version": "2026-09-29.v1",
    },
    "auger_hole_cm6_s": {
        "source": "Agent Kronig reviewed silicon baseline",
        "version": "2026-09-29.v1",
    },
    "bgn_reference_energy_ev": {
        "source": "Agent Kronig reviewed Slotboom baseline",
        "version": "2026-09-29.v1",
    },
    "bgn_reference_density_cm3": {
        "source": "Agent Kronig reviewed Slotboom baseline",
        "version": "2026-09-29.v1",
    },
}
SILICON_PARAMETERS = {
    "electron_affinity_ev": 4.05,
    "band_gap_ev": 1.124,
    "effective_density_conduction_cm3": 2.8e19,
    "effective_density_valence_cm3": 1.04e19,
    "electron_lifetime_s": 1.0e-8,
    "hole_lifetime_s": 1.0e-8,
    "auger_electron_cm6_s": 2.8e-31,
    "auger_hole_cm6_s": 9.9e-32,
    "bgn_reference_energy_ev": 9.0e-3,
    "bgn_reference_density_cm3": 1.0e17,
}
