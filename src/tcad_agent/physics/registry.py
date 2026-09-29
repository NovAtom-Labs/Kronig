"""Physics capability registry that refuses unreviewed model selections."""

from __future__ import annotations

from tcad_agent.capabilities.descriptors import (
    CapabilityDescriptor,
    CapabilityMaturity,
)


class PhysicsRegistry:
    def __init__(self, descriptors: tuple[CapabilityDescriptor, ...]) -> None:
        by_id = {item.id: item for item in descriptors}
        if len(by_id) != len(descriptors):
            raise ValueError("physics capability ids must be unique")
        self._descriptors = by_id

    @classmethod
    def default(cls) -> PhysicsRegistry:
        evidence = ("devsim-examples:2.9.1",)
        return cls(
            (
                CapabilityDescriptor(
                    id="equation.poisson",
                    category="equation",
                    summary="Electrostatic potential from Poisson's equation",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=evidence,
                    produces=("potential",),
                ),
                CapabilityDescriptor(
                    id="equation.electron_continuity",
                    category="equation",
                    summary="Drift-diffusion electron continuity equation",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=evidence,
                    requires=("equation.poisson",),
                    produces=("electron_density", "electron_current_density"),
                ),
                CapabilityDescriptor(
                    id="equation.hole_continuity",
                    category="equation",
                    summary="Drift-diffusion hole continuity equation",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=evidence,
                    requires=("equation.poisson",),
                    produces=("hole_density", "hole_current_density"),
                ),
                CapabilityDescriptor(
                    id="model.boltzmann",
                    category="model",
                    summary="Classical Boltzmann carrier statistics",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=evidence,
                    produces=("electron_density", "hole_density"),
                    supported_materials=("silicon",),
                    parameter_sources=evidence,
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                CapabilityDescriptor(
                    id="model.fermi",
                    category="model",
                    summary=(
                        "Coupled Fermi-Dirac carrier statistics using DEVSIM native "
                        "Fermi integrals and quasi-Fermi-gradient transport"
                    ),
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=(
                        "devsim-fermi-integrals:2.9.1",
                        "novatom.fermi-gradient.2026-09-29.v1",
                    ),
                    requires=(
                        "equation.poisson",
                        "equation.electron_continuity",
                        "equation.hole_continuity",
                    ),
                    conflicts=("model.boltzmann",),
                    produces=(
                        "electron_density",
                        "hole_density",
                        "electron_quasi_fermi_level",
                        "hole_quasi_fermi_level",
                    ),
                    supported_materials=("silicon",),
                    parameter_sources=(
                        "devsim-fermi-integrals:2.9.1",
                        "novatom.fermi-gradient.2026-09-29.v1",
                    ),
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                CapabilityDescriptor(
                    id="model.constant_mobility",
                    category="model",
                    summary="Constant electron and hole bulk mobility",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=evidence,
                    requires=(
                        "equation.electron_continuity",
                        "equation.hole_continuity",
                    ),
                    produces=("electron_mobility", "hole_mobility"),
                    supported_materials=("silicon",),
                    parameter_sources=evidence,
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                CapabilityDescriptor(
                    id="model.srh",
                    category="model",
                    summary="Shockley-Read-Hall bulk recombination",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=evidence,
                    requires=(
                        "equation.electron_continuity",
                        "equation.hole_continuity",
                    ),
                    produces=("srh_recombination_rate",),
                    supported_materials=("silicon",),
                    parameter_sources=evidence,
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                CapabilityDescriptor(
                    id="model.slotboom_bgn",
                    category="model",
                    summary="Slotboom band-gap narrowing with a pinned parameter set",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=(
                        "novatom.silicon.baseline.2026-09-29.v1",
                        "devsim-expression-engine:2.9.1",
                    ),
                    requires=("equation.poisson",),
                    produces=(
                        "band_gap_narrowing",
                        "effective_intrinsic_density",
                    ),
                    supported_materials=("silicon",),
                    parameter_sources=("novatom.silicon.baseline.2026-09-29.v1",),
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                CapabilityDescriptor(
                    id="model.auger",
                    category="model",
                    summary="Electron and hole Auger recombination with pinned coefficients",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=(
                        "novatom.silicon.baseline.2026-09-29.v1",
                        "devsim-expression-engine:2.9.1",
                    ),
                    requires=(
                        "equation.electron_continuity",
                        "equation.hole_continuity",
                    ),
                    produces=(
                        "auger_recombination_rate",
                        "total_recombination_rate",
                    ),
                    supported_materials=("silicon",),
                    parameter_sources=("novatom.silicon.baseline.2026-09-29.v1",),
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                CapabilityDescriptor(
                    id="model.klaassen_mobility",
                    category="model",
                    summary="Doping and temperature dependent Klaassen bulk mobility",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=("devsim-klaassen:2.9.1",),
                    requires=(
                        "equation.electron_continuity",
                        "equation.hole_continuity",
                    ),
                    produces=("electron_mobility", "hole_mobility"),
                    supported_materials=("silicon",),
                    parameter_sources=("devsim-klaassen:2.9.1",),
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                CapabilityDescriptor(
                    id="model.high_field_saturation",
                    category="model",
                    summary="One-dimensional Philips velocity-saturation mobility",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=("devsim-klaassen:2.9.1",),
                    requires=(
                        "equation.electron_continuity",
                        "equation.hole_continuity",
                    ),
                    produces=("electron_mobility", "hole_mobility"),
                    supported_materials=("silicon",),
                    parameter_sources=("devsim-klaassen:2.9.1",),
                    backend_compatibility={"devsim": "2.9.1"},
                ),
            )
        )

    def require_reviewed(self, identifier: str) -> CapabilityDescriptor:
        descriptor = self._descriptors.get(identifier)
        if descriptor is None or descriptor.maturity is not CapabilityMaturity.REVIEWED:
            raise KeyError(f"physics capability is not reviewed: {identifier}")
        return descriptor

    def all(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))
