"""Portable material identities with explicit evidence and maturity."""

from __future__ import annotations

from typing import Literal

from tcad_agent.capabilities.descriptors import CapabilityMaturity
from tcad_agent.domain.models import StrictModel


class MaterialDescriptor(StrictModel):
    id: str
    material_class: Literal["semiconductor", "dielectric", "conductor"]
    maturity: CapabilityMaturity
    evidence_refs: tuple[str, ...]
    parameter_keys: tuple[str, ...] = ()


class MaterialRegistry:
    def __init__(self, descriptors: tuple[MaterialDescriptor, ...]) -> None:
        by_id = {item.id: item for item in descriptors}
        if len(by_id) != len(descriptors):
            raise ValueError("material ids must be unique")
        self._descriptors = by_id

    @classmethod
    def default(cls) -> MaterialRegistry:
        source = ("devsim-material-models:2.9.1",)
        return cls(
            (
                MaterialDescriptor(
                    id="silicon",
                    material_class="semiconductor",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=source,
                    parameter_keys=(
                        "permittivity",
                        "electron_affinity",
                        "band_gap",
                        "effective_density_conduction",
                        "effective_density_valence",
                    ),
                ),
                MaterialDescriptor(
                    id="silicon_dioxide",
                    material_class="dielectric",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=source,
                    parameter_keys=("permittivity",),
                ),
            )
        )

    def require_reviewed(self, identifier: str) -> MaterialDescriptor:
        descriptor = self._descriptors.get(identifier)
        if descriptor is None or descriptor.maturity is not CapabilityMaturity.REVIEWED:
            raise KeyError(f"material is not reviewed: {identifier}")
        return descriptor

    def all(self) -> tuple[MaterialDescriptor, ...]:
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))
