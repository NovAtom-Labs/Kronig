"""Typed grounding rules for scientific interpretations and conclusions."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field

from tcad_agent.domain.models import ExperimentSpec, StrictModel
from tcad_agent.domain.profiles import ConstantProfile, ProfileSpecies
from tcad_agent.results.models import CanonicalResult


class ClaimKind(StrEnum):
    QUANTITATIVE = "quantitative"
    CARRIER_ROLE = "carrier_role"
    COMPARATIVE_MAGNITUDE = "comparative_magnitude"


class CarrierRole(StrEnum):
    MAJORITY = "majority"
    MINORITY = "minority"


class ScientificClaim(StrictModel):
    id: str = Field(min_length=1, max_length=160)
    kind: ClaimKind
    text: str = Field(min_length=1, max_length=2_000)
    evidence_datasets: tuple[str, ...] = ()
    control_result_ids: tuple[str, ...] = ()
    source_references: tuple[str, ...] = ()
    region_id: str | None = None
    carrier: Literal["electron", "hole"] | None = None
    carrier_role: CarrierRole | None = None


class ClaimAssessment(StrictModel):
    claim_id: str
    status: Literal["supported", "qualified", "rejected"]
    reasons: tuple[str, ...]
    evidence_datasets: tuple[str, ...]


def _majority_carrier(spec: ExperimentSpec, region_id: str) -> str | None:
    donors = 0.0
    acceptors = 0.0
    found = False
    for profile in spec.profiles:
        if not isinstance(profile, ConstantProfile) or profile.region != region_id:
            continue
        found = True
        if profile.species is ProfileSpecies.DONOR:
            donors += profile.value.to("1 / m**3")
        elif profile.species is ProfileSpecies.ACCEPTOR:
            acceptors += profile.value.to("1 / m**3")
    if not found or donors == acceptors:
        return None
    return "electron" if donors > acceptors else "hole"


def assess_scientific_claim(
    claim: ScientificClaim,
    spec: ExperimentSpec,
    result: CanonicalResult,
) -> ClaimAssessment:
    """Assess a typed claim against composition, canonical evidence, and controls."""

    reasons: list[str] = []
    if claim.kind is ClaimKind.COMPARATIVE_MAGNITUDE and not (
        claim.control_result_ids or claim.source_references
    ):
        reasons.append(
            "A comparative magnitude claim requires a control result or cited source."
        )
    if (
        claim.kind is ClaimKind.CARRIER_ROLE
        and claim.region_id is not None
        and claim.carrier is not None
        and claim.carrier_role is not None
    ):
        majority = _majority_carrier(spec, claim.region_id)
        if majority == claim.carrier and claim.carrier_role is CarrierRole.MINORITY:
            reasons.append(
                f"{claim.carrier.title()}s are the majority carriers in "
                f"{claim.region_id} under the confirmed doping composition."
            )
        elif majority is not None and majority != claim.carrier and (
            claim.carrier_role is CarrierRole.MAJORITY
        ):
            reasons.append(
                f"{claim.carrier.title()}s are not the majority carriers in "
                f"{claim.region_id} under the confirmed doping composition."
            )
    available = set(result.datasets)
    missing = tuple(
        dataset_id
        for dataset_id in claim.evidence_datasets
        if dataset_id not in available
    )
    if missing:
        reasons.append(
            "Canonical evidence is missing: " + ", ".join(sorted(missing)) + "."
        )
    if reasons:
        return ClaimAssessment(
            claim_id=claim.id,
            status="rejected",
            reasons=tuple(reasons),
            evidence_datasets=claim.evidence_datasets,
        )
    if not claim.evidence_datasets and not claim.source_references:
        return ClaimAssessment(
            claim_id=claim.id,
            status="qualified",
            reasons=("No canonical dataset or cited source supports this claim.",),
            evidence_datasets=(),
        )
    return ClaimAssessment(
        claim_id=claim.id,
        status="supported",
        reasons=("Claim is consistent with the supplied canonical evidence.",),
        evidence_datasets=claim.evidence_datasets,
    )
