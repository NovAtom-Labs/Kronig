from tcad_agent.results.models import CanonicalResult
from tcad_agent.science.claims import (
    CarrierRole,
    ClaimKind,
    ScientificClaim,
    assess_scientific_claim,
)


def test_claim_grounding_rejects_minority_hole_claim_in_p_type_region(valid_spec) -> None:
    claim = ScientificClaim(
        id="claim-1",
        kind=ClaimKind.CARRIER_ROLE,
        text="Transport is dominated by minority-carrier hole transport in p_region.",
        evidence_datasets=("hole_density",),
        region_id="p_region",
        carrier="hole",
        carrier_role=CarrierRole.MINORITY,
    )
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        axes={},
        datasets={},
    )

    assessment = assess_scientific_claim(claim, valid_spec, result)

    assert assessment.status == "rejected"
    assert "majority" in assessment.reasons[0]


def test_comparative_magnitude_claim_requires_control_result_or_source(valid_spec) -> None:
    claim = ScientificClaim(
        id="claim-2",
        kind=ClaimKind.COMPARATIVE_MAGNITUDE,
        text="The electric field is substantially larger than the reference structure.",
        evidence_datasets=("electric_field",),
    )
    result = CanonicalResult(backend="devsim", status="completed")

    assessment = assess_scientific_claim(claim, valid_spec, result)

    assert assessment.status == "rejected"
    assert "control result or cited source" in assessment.reasons[0]


def test_claim_grounding_accepts_dataset_backed_noncomparative_claim(valid_spec) -> None:
    claim = ScientificClaim(
        id="claim-3",
        kind=ClaimKind.QUANTITATIVE,
        text="The reported electrostatic potential is taken from canonical evidence.",
        evidence_datasets=("potential",),
    )
    result = CanonicalResult(
        backend="devsim",
        status="completed",
        fields={
            "potential": {
                "positions_m": (0.0, 1.0),
                "values": (0.0, 0.7),
                "unit": "V",
            }
        },
    )

    assessment = assess_scientific_claim(claim, valid_spec, result)

    assert assessment.status == "supported"
