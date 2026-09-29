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
                    id="model.band_gap_narrowing",
                    category="model",
                    summary="Band-gap narrowing awaiting reviewed parameterization",
                    maturity=CapabilityMaturity.EXPERIMENTAL,
                    evidence_refs=(),
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
