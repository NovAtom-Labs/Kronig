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
    parameter_set_version: str
    parameter_sources: dict[str, str]
    backend_compatibility: dict[str, str]
    compatible_interfaces: tuple[str, ...] = ("continuity",)


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
                    parameter_set_version="2026-09-29.v1",
                    parameter_sources={
                        "relative_permittivity": "DEVSIM 2.9.1 simple_physics.py",
                        "electron_affinity": "Agent Kronig reviewed silicon baseline 2026-09-29.v1",
                        "band_gap": "Agent Kronig reviewed silicon baseline 2026-09-29.v1",
                        "effective_density_conduction": (
                            "Agent Kronig reviewed silicon baseline 2026-09-29.v1"
                        ),
                        "effective_density_valence": (
                            "Agent Kronig reviewed silicon baseline 2026-09-29.v1"
                        ),
                    },
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                MaterialDescriptor(
                    id="silicon_dioxide",
                    material_class="dielectric",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=source,
                    parameter_keys=("permittivity",),
                    parameter_set_version="devsim-2.9.1",
                    parameter_sources={
                        "relative_permittivity": "DEVSIM 2.9.1 simple_physics.py"
                    },
                    backend_compatibility={"devsim": "2.9.1"},
                ),
                MaterialDescriptor(
                    id="generic_dielectric",
                    material_class="dielectric",
                    maturity=CapabilityMaturity.REVIEWED,
                    evidence_refs=("agent-kronig:user-parameterized-dielectric:v1",),
                    parameter_keys=("relative_permittivity",),
                    parameter_set_version="researcher-supplied-v1",
                    parameter_sources={
                        "relative_permittivity": "researcher-owned experiment input"
                    },
                    backend_compatibility={"devsim": "2.9.1"},
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
