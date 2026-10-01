"""Portable scientific dependency rules and bounded model discovery merging."""

from collections.abc import Iterable

from tcad_agent.domain.models import ExperimentSpec, Observable
from tcad_agent.science.models import (
    InputAuthority,
    InputResolutionRecord,
    ModelDiscoveredRequirement,
    ProvenanceReference,
    ResolutionStatus,
)


def absolute_current_area_requirements(
    spec: ExperimentSpec,
) -> tuple[InputResolutionRecord, ...]:
    """Resolve the physical area required to convert A/m^2 into amperes."""

    if Observable.ABSOLUTE_TERMINAL_CURRENT not in spec.observables:
        return ()
    records: list[InputResolutionRecord] = []
    for contact in spec.contacts:
        value = contact.area.model_dump(mode="json") if contact.area is not None else None
        resolved = contact.area is not None
        records.append(
            InputResolutionRecord(
                path=f"contacts.{contact.id}.area",
                quantity=f"Physical cross-sectional area of contact {contact.id}",
                value=value,
                authority=InputAuthority.RESEARCHER,
                source=(
                    ProvenanceReference(id="confirmed-experiment-spec", kind="researcher")
                    if resolved
                    else None
                ),
                required_by=(Observable.ABSOLUTE_TERMINAL_CURRENT.value,),
                status=(
                    ResolutionStatus.RESOLVED
                    if resolved
                    else ResolutionStatus.CLARIFICATION_REQUIRED
                ),
                rationale=(
                    "Absolute current equals terminal current density multiplied by "
                    "physical contact area."
                ),
                consequence=(
                    None
                    if resolved
                    else (
                        "Only normalized current density in A/m^2 can be reported "
                        "without this area."
                    )
                ),
            )
        )
    return tuple(records)


def merge_model_discoveries(
    *,
    registered_paths: set[str],
    discoveries: Iterable[ModelDiscoveredRequirement],
    allowed_evidence_refs: set[str],
    minimum_confidence: float = 0.7,
) -> tuple[tuple[ModelDiscoveredRequirement, ...], tuple[ModelDiscoveredRequirement, ...]]:
    """Accept only novel, evidence-bounded model discoveries."""

    accepted: list[ModelDiscoveredRequirement] = []
    rejected: list[ModelDiscoveredRequirement] = []
    seen = set(registered_paths)
    for discovery in discoveries:
        evidence_is_bounded = bool(discovery.evidence_refs) and set(
            discovery.evidence_refs
        ).issubset(allowed_evidence_refs)
        if (
            discovery.path in seen
            or discovery.confidence < minimum_confidence
            or not evidence_is_bounded
        ):
            rejected.append(discovery)
            continue
        accepted.append(discovery)
        seen.add(discovery.path)
    return tuple(accepted), tuple(rejected)
