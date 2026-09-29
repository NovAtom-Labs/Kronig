"""Operating-point convergence evidence."""

from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationCheck


def convergence_checks(result: CanonicalResult) -> tuple[ValidationCheck, ...]:
    if not result.operating_points:
        return (
            ValidationCheck(
                id="operating-points-converged",
                level="numerical",
                status="not_applicable",
                message="This legacy result does not contain typed operating-point records.",
                evidence_origin="configured",
                evidence_paths=("result.operating_points",),
            ),
        )
    failures = [
        point.index for point in result.operating_points if point.state != "converged"
    ]
    return (
        ValidationCheck(
            id="operating-points-converged",
            level="numerical",
            status="passed" if not failures else "failed",
            measured_value=(
                len(result.operating_points)
                if not failures
                else "failed indices: " + ", ".join(str(index) for index in failures)
            ),
            limit="all requested operating points converged",
            message="Every requested point remains explicit and carries its solver state.",
            evidence_origin="simulator_observed",
            evidence_paths=("result.operating_points",),
        ),
    )
