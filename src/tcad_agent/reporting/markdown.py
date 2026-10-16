"""Markdown report rendered only from structured evidence."""

from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.reporting.traceability import TraceabilityMatrix
from tcad_agent.results.models import CanonicalResult
from tcad_agent.results.presentation import display_projection, display_values
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
        projection = display_projection(result, spec.display_units, allow_missing=True)
        matched = {
            name if name in spec.display_units else name.partition("__")[0] for name in projection
        }
        for name in spec.display_units.keys() - matched:
            lines.extend(
                ["", f"Requested output `{name}` is unavailable; no values were fabricated."]
            )
        for name, dataset in result.datasets.items():
            if not (
                name.startswith(
                    (
                        "capacitance__",
                        "ac_capacitance__",
                        "absolute_capacitance__",
                        "absolute_ac_capacitance__",
                    )
                )
                or name in projection
            ):
                continue
            values, unit = display_values(dataset, projection.get(name))
            if len(dataset.shape) != 1 or not dataset.axes:
                continue
            axis = result.axes[dataset.axes[0]]
            lines.extend(
                [
                    "",
                    f"## {dataset.label}",
                    "",
                    f"Values shown in {unit}; canonical evidence remains {dataset.unit}.",
                    f"Source: `{dataset.source}`.",
                    "",
                    f"| {axis.label} ({axis.unit}) | {dataset.label} ({unit}) |",
                    "|---:|---:|",
                ]
            )
            for i, (coordinate, value) in enumerate(zip(axis.values, values, strict=True)):
                if dataset.validity is not None and not dataset.validity[i]:
                    formatted = "unavailable (failed sample)"
                elif dataset.imaginary_values is not None:
                    scale = projection.get(name, {}).get("scale", 1)
                    formatted = (
                        f"real {value:.6e}; imaginary {dataset.imaginary_values[i] * scale:.6e}"
                    )
                else:
                    formatted = f"{value:.6e}"
                lines.append(f"| {coordinate:.6e} | {formatted} |")
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
                lines.append(f"| {record.deliverable} | {record.status.value} | {evidence} |")
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
