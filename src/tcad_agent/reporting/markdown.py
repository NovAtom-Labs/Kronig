"""Markdown report rendered only from structured evidence."""

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.reporting.traceability import TraceabilityMatrix
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationReport


class MarkdownReport:
    def render(
        self,
        spec: ExperimentSpec,
        result: CanonicalResult,
        validation: ValidationReport,
        *,
        traceability: TraceabilityMatrix | None = None,
    ) -> str:
        if result.status != "completed":
            outcome = "Failed"
        elif validation.overall == "passed":
            outcome = "Completed"
        else:
            outcome = "Checks need attention"
        lines = [
            f"# {spec.name} TCAD Evidence Summary",
            "",
            f"**Outcome:** {outcome}",
            f"**Backend:** {result.backend}",
            f"**Simulator version:** {result.simulator_version or 'unavailable'}",
            f"**Validation:** {validation.overall}",
            "",
            "## Bias results",
            "",
            "| Bias (V) | Terminal | Current density | Converged |",
            "|---:|---|---:|:---:|",
        ]
        for point in result.bias_points:
            for terminal in result.terminals:
                current = point.terminal_currents_a_per_m2.get(terminal)
                value = "unavailable" if current is None else f"{current:.6e} A/m^2"
                lines.append(
                    f"| {point.bias_v:.6e} | {terminal} | {value} | "
                    f"{'yes' if point.converged else 'no'} |"
                )
        lines.extend(
            [
                "",
                "## Validation evidence",
                "",
                "| Check | Level | Status | Evidence origin | Measured | Limit |",
                "|---|---|---|---|---|---|",
            ]
        )
        for check in validation.checks:
            lines.append(
                f"| {check.id} | {check.level} | {check.status} | "
                f"{check.evidence_origin} | {check.measured_value} | {check.limit} |"
            )
        if traceability is not None:
            lines.extend(
                [
                    "",
                    "## Requested output traceability",
                    "",
                    "| Requested output | Status | Canonical evidence |",
                    "|---|---|---|",
                ]
            )
            for record in traceability.records:
                evidence = ", ".join(record.evidence_datasets) or "unavailable"
                lines.append(
                    f"| {record.deliverable} | {record.status.value} | {evidence} |"
                )
        lines.extend(
            [
                "",
                "## Spatial evidence",
                "",
                "- `results/fields.csv` contains normalized SI field samples.",
                "- `results/field-plots.svg` visualizes the same canonical field data.",
            ]
        )
        lines.extend(
            [
                "",
                "## Limitations",
                "",
                "- This result uses an uncalibrated silicon-first reference model.",
                "- One-dimensional terminal values are reported as current density.",
                "- Fabrication or external claims require expert review and calibration.",
                "",
            ]
        )
        return "\n".join(lines)
