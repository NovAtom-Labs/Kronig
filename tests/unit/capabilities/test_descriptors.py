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


def test_catalog_can_project_legacy_manifest_without_losing_limits() -> None:
    manifest = CapabilityManifest.from_backend("devsim")

    catalog = CapabilityCatalog.from_manifest(manifest)

    assert "study.equilibrium" in {item.id for item in catalog.descriptors}
    assert catalog.limits == manifest.limits
    assert catalog.public_view().backend == "devsim"


def test_material_and_physics_registries_are_evidence_gated() -> None:
    materials = MaterialRegistry.default()
    physics = PhysicsRegistry.default()

    assert materials.require_reviewed("silicon").material_class == "semiconductor"
    assert materials.require_reviewed("silicon_dioxide").material_class == "dielectric"
    assert physics.require_reviewed("equation.poisson").produces == ("potential",)
    with pytest.raises(KeyError):
        physics.require_reviewed("model.band_gap_narrowing")
