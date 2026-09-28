"""Markdown report rendered only from structured evidence."""

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.models import ValidationReport


class MarkdownReport:
    def render(
        self,
        spec: ExperimentSpec,
        result: CanonicalResult,
        validation: ValidationReport,
    ) -> str:
        outcome = "Completed" if validation.overall == "passed" else "Failed"
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
