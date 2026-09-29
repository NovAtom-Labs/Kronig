import pytest
from pydantic import ValidationError

from tcad_agent.domain.models import ExperimentSpec


def stack() -> dict:
    return {
        "schema_version": "1.0",
        "name": "mixed-stack",
        "dimension": 1,
        "regions": [
            {"id": "oxide", "material": "silicon_dioxide", "x0": "0 nm", "x1": "10 nm"},
            {"id": "bulk", "material": "silicon", "x0": "10 nm", "x1": "1 um"},
        ],
        "interfaces": [
            {
                "id": "oxide_bulk",
                "left_region": "oxide",
                "right_region": "bulk",
                "fixed_charge_density": "1e11 cm^-2",
                "mesh_spacing": "0.5 nm",
            }
        ],
        "profiles": [],
        "contacts": [
            {
                "id": "gate",
                "location": "x_min",
                "kind": "metal_work_function",
                "work_function": "4.1 eV",
            },
            {"id": "back", "location": "x_max", "kind": "ohmic"},
        ],
        "physics": {"equations": ["poisson"]},
        "study": {"kind": "equilibrium"},
        "observables": ["potential", "electric_field"],
    }


def test_interface_between_adjacent_regions_accepts_fixed_sheet_charge() -> None:
    spec = ExperimentSpec.model_validate(stack())

    assert spec.interfaces[0].fixed_charge_density is not None
    assert spec.interfaces[0].fixed_charge_density.to("cm^-2") == pytest.approx(1e11)
    assert spec.interfaces[0].mesh_spacing.to("nm") == pytest.approx(0.5)


def test_interface_must_reference_an_adjacent_ordered_pair() -> None:
    payload = stack()
    payload["interfaces"][0]["left_region"] = "bulk"
    payload["interfaces"][0]["right_region"] = "oxide"

    with pytest.raises(ValidationError, match="adjacent ordered regions"):
        ExperimentSpec.model_validate(payload)


def test_every_material_boundary_requires_an_interface_record() -> None:
    payload = stack()
    payload["interfaces"] = []

    with pytest.raises(ValidationError, match="interface record"):
        ExperimentSpec.model_validate(payload)


def test_interface_accepts_unit_checked_surface_srh_and_acceptor_trap() -> None:
    payload = stack()
    payload["interfaces"][0].update(
        {
            "surface_electron_velocity": "1e4 cm/s",
            "surface_hole_velocity": "2e4 cm/s",
            "trap_density": "5e11 cm^-2",
            "trap_energy": "0.15 eV",
            "trap_type": "acceptor",
        }
    )

    interface = ExperimentSpec.model_validate(payload).interfaces[0]

    assert interface.surface_electron_velocity.to("cm/s") == pytest.approx(1e4)
    assert interface.trap_density.to("cm^-2") == pytest.approx(5e11)
    assert interface.trap_type == "acceptor"


def test_surface_srh_requires_both_capture_velocities() -> None:
    payload = stack()
    payload["interfaces"][0]["surface_electron_velocity"] = "1e4 cm/s"

    with pytest.raises(ValidationError, match="both electron and hole"):
        ExperimentSpec.model_validate(payload)


def test_interface_trap_requires_complete_single_level_definition() -> None:
    payload = stack()
    payload["interfaces"][0]["trap_density"] = "5e11 cm^-2"

    with pytest.raises(ValidationError, match="trap density, energy, and type"):
        ExperimentSpec.model_validate(payload)
