import pytest
from pydantic import ValidationError

from tcad_agent.capabilities.descriptors import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityInputDescriptor,
    CapabilityMaturity,
    InputAuthority,
)
from tcad_agent.capabilities.models import CapabilityManifest
from tcad_agent.physics.materials import MaterialRegistry
from tcad_agent.physics.registry import PhysicsRegistry


def descriptor(
    identifier: str,
    *,
    maturity: CapabilityMaturity = CapabilityMaturity.REVIEWED,
    evidence_refs: tuple[str, ...] = ("official:devsim-2.9.1",),
    requires: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        id=identifier,
        category="model",
        summary=f"Capability {identifier}",
        maturity=maturity,
        evidence_refs=evidence_refs,
        requires=requires,
        conflicts=conflicts,
        required_inputs=(
            CapabilityInputDescriptor(
                path="study.temperature",
                description="Physical temperature",
                authority=InputAuthority.RESEARCHER,
                required=True,
                unit="K",
            ),
        ),
        produces=("potential",),
    )


def test_reviewed_capability_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        descriptor("model.invalid", evidence_refs=())


def test_catalog_rejects_unknown_dependencies_and_conflicts() -> None:
    with pytest.raises(ValidationError, match="unknown capability"):
        CapabilityCatalog(
            backend="devsim",
            adapter_version="0.1.0",
            descriptors=(descriptor("model.a", requires=("model.missing",)),),
        )


def test_catalog_public_view_excludes_unreviewed_entries() -> None:
    catalog = CapabilityCatalog(
        backend="devsim",
        adapter_version="0.1.0",
        descriptors=(
            descriptor("model.reviewed"),
            descriptor(
                "model.experimental",
                maturity=CapabilityMaturity.EXPERIMENTAL,
                evidence_refs=(),
            ),
        ),
    )

    public = catalog.public_view()

    assert [item.id for item in public.capabilities] == ["model.reviewed"]
    assert public.digest == catalog.digest
    assert public.capabilities[0].required_inputs[0].authority == "researcher"


def test_typed_descriptor_preserves_execution_and_backend_constraints() -> None:
    item = CapabilityDescriptor(
        id="model.reviewed_transport",
        category="model",
        summary="Reviewed portable transport model",
        maturity=CapabilityMaturity.REVIEWED,
        evidence_refs=("official:devsim-2.9.1",),
        supported_materials=("silicon",),
        supported_interfaces=("continuity",),
        supported_studies=("equilibrium", "dc"),
        available_observables=("electron_current_density",),
        required_validators=("terminal_current_conservation",),
        parameter_sources=("official:devsim-2.9.1",),
        execution_limits={"max_bias_points": 10000},
        backend_compatibility={"devsim": "2.9.1"},
        sentaurus_mapping="Mobility(...) placeholder",
    )

    catalog = CapabilityCatalog(
        backend="devsim", adapter_version="0.2.0", descriptors=(item,)
    )
    projected = catalog.public_view().capabilities[0]

    assert projected.supported_materials == ("silicon",)
    assert projected.required_validators == ("terminal_current_conservation",)
    assert projected.backend_compatibility == {"devsim": "2.9.1"}
    assert projected.sentaurus_mapping == "Mobility(...) placeholder"


def test_catalog_can_project_legacy_manifest_without_losing_limits() -> None:
    manifest = CapabilityManifest.from_backend("devsim")

    catalog = CapabilityCatalog.from_manifest(manifest)

    assert "study.equilibrium" in {item.id for item in catalog.descriptors}
    assert catalog.limits == manifest.limits
    assert catalog.public_view().backend == "devsim"
    ac = next(item for item in catalog.descriptors if item.id == "study.ac")
    assert {item.path for item in ac.required_inputs} >= {
        "study.contact",
        "study.frequency",
        "study.amplitude",
        "physics.temperature",
    }
    generic_dielectric = next(
        item for item in catalog.descriptors if item.id == "material.generic_dielectric"
    )
    assert {item.path for item in generic_dielectric.required_inputs} == {
        "regions.material",
        "regions.relative_permittivity",
    }
    assert ac.backend_compatibility == {"devsim": "2.9.1"}
    assert ac.execution_limits["max_bias_points"] == 10000
    assert set(ac.required_validators) >= {
        "canonical-datasets-structural",
        "operating-points-converged",
    }
    assert ac.sentaurus_mapping == "pending-reviewed-mapping"


def test_material_and_physics_registries_are_evidence_gated() -> None:
    materials = MaterialRegistry.default()
    physics = PhysicsRegistry.default()

    assert materials.require_reviewed("silicon").material_class == "semiconductor"
    assert materials.require_reviewed("silicon_dioxide").material_class == "dielectric"
    assert materials.require_reviewed("generic_dielectric").parameter_keys == (
        "relative_permittivity",
    )
    assert physics.require_reviewed("equation.poisson").produces == ("potential",)
    assert physics.require_reviewed("model.slotboom_bgn").produces == (
        "band_gap_narrowing",
        "effective_intrinsic_density",
    )
    assert "total_recombination_rate" in physics.require_reviewed(
        "model.auger"
    ).produces
    silicon = materials.require_reviewed("silicon")
    assert silicon.parameter_set_version == "2026-09-29.v1"
    assert set(silicon.parameter_sources) >= {
        "relative_permittivity",
        "electron_affinity",
        "band_gap",
    }
    assert silicon.backend_compatibility == {"devsim": "2.9.1"}


def test_transient_capability_exposes_conditional_pulse_inputs() -> None:
    catalog = CapabilityCatalog.from_manifest(CapabilityManifest.from_backend("devsim"))
    transient = next(item for item in catalog.descriptors if item.id == "study.transient")

    assert {item.path for item in transient.optional_inputs} >= {
        "study.pulse_delay",
        "study.rise_time",
        "study.pulse_width",
        "study.fall_time",
        "study.minimum_step",
        "study.maximum_retries",
    }
    assert all(
        "pulse" in (item.question_hint or "").lower()
        for item in transient.optional_inputs
        if item.path.startswith("study.pulse")
        or item.path in {"study.rise_time", "study.fall_time"}
    )
