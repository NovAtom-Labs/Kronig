"""Deterministic researcher-facing experiment plan artifacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tcad_agent.domain.units import QuantityValue
from tcad_agent.experiments.models import PreparedExperiment


@dataclass(frozen=True)
class PlanArtifactPaths:
    project_root: Path
    markdown_path: Path
    json_path: Path


def project_slug(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return normalized[:80] or "experiment"


def _display(value: Any) -> str:
    if isinstance(value, dict) and set(value) >= {"magnitude_si", "si_unit", "dimensionality"}:
        quantity = QuantityValue.model_validate(value)
        return f"{quantity.magnitude_si:g} {quantity.si_unit}"
    if isinstance(value, dict) and set(value) >= {"value", "unit"}:
        return f"{value['value']} {value['unit']}"
    if isinstance(value, dict):
        return "; ".join(
            f"{key.replace('_', ' ')}: {_display(item)}" for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return ", ".join(_display(item) for item in value)
    return str(value)


class ExperimentPlanArtifactWriter:
    """Write stable PLAN.md and plan.json files inside the selected project."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.resolve()

    def write(self, prepared: PreparedExperiment) -> PlanArtifactPaths:
        experiments = self.workspace / "experiments"
        if experiments.is_symlink():
            raise ValueError("experiments directory cannot be a symlink")
        experiments.mkdir(parents=True, exist_ok=True)
        slug = project_slug(prepared.spec.name)
        if prepared.recovery_proposal is not None:
            slug += f"-recovery-{prepared.plan_digest[:8]}"
        root = experiments / slug
        if root.is_symlink():
            raise ValueError("experiment project directory cannot be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        if root.resolve().parent != experiments.resolve():
            raise ValueError("experiment project escaped the workspace")

        payload = {
            "schema_version": "1.0",
            "backend": prepared.backend,
            "plan_digest": prepared.plan_digest,
            "capability_digest": prepared.capability_digest,
            "warnings": list(prepared.warnings),
            "spec": prepared.spec.normalized(),
            # The exact immutable execution record is retained in the structured
            # artifact so approval can resume by digest without transporting a
            # large model-generated payload through the conversation.
            "prepared": prepared.model_dump(mode="json"),
            "scientific_input_ledger": [
                record.model_dump(mode="json", exclude_none=True)
                for record in prepared.completeness.records
            ],
        }
        json_bytes = (
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        markdown_bytes = self._render_markdown(prepared).encode("utf-8")
        self._atomic_write(root / "plan.json", json_bytes)
        self._atomic_write(root / "PLAN.md", markdown_bytes)
        return PlanArtifactPaths(
            project_root=root,
            markdown_path=root / "PLAN.md",
            json_path=root / "plan.json",
        )

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _render_markdown(prepared: PreparedExperiment) -> str:
        spec = prepared.spec
        lines = [
            f"# {spec.name}",
            "",
            "## Approval identity",
            "",
            f"- Plan digest: `{prepared.plan_digest}`",
            f"- Capability digest: `{prepared.capability_digest}`",
            f"- Backend: `{prepared.backend}`",
            f"- Portable contract: ExperimentSpec {spec.schema_version}",
            "",
            "## Structure",
            "",
        ]
        if prepared.recovery_proposal is not None:
            proposal = prepared.recovery_proposal
            recovery = [
                "## Reviewed numerical recovery",
                "",
                f"Original immutable bundle: `{proposal.original_bundle_id}`",
                "",
                f"Recorded failure: {proposal.failure.evidence}",
                "",
                "Only these numerical settings change. "
                "Physics and requested outputs remain unchanged.",
                "",
            ]
            recovery.extend(
                f"- `{change.path}`: {_display(change.before)} → {_display(change.after)}"
                for change in proposal.changes
            )
            recovery.extend(["", "Unchanged scientific acceptance limits:", ""])
            recovery.extend(
                f"- `{limit.name}`: {limit.value:g}" for limit in proposal.validation_limits
            )
            recovery.extend(["", "Execution requires approval of this new plan.", ""])
            lines[lines.index("## Structure") : lines.index("## Structure")] = recovery
        for region in spec.regions:
            lines.append(
                f"- `{region.id}`: {region.material}, "
                f"{_display(region.x0.model_dump(mode='json'))} to "
                f"{_display(region.x1.model_dump(mode='json'))}"
            )
        lines.extend(["", "## Doping and charge profiles", ""])
        for profile in spec.profiles:
            lines.append(f"- {_display(profile.model_dump(mode='json', exclude_none=True))}")
        lines.extend(["", "## Contacts", ""])
        for contact in spec.contacts:
            area = (
                f", area {_display(contact.area.model_dump(mode='json'))}"
                if contact.area is not None
                else ""
            )
            lines.append(
                f"- `{contact.id}`: {contact.kind.value} at {contact.location.value}{area}"
                + (
                    f", work function {_display(contact.work_function.model_dump(mode='json'))}"
                    if contact.work_function is not None
                    else ""
                )
            )
        lines.extend(
            [
                "",
                "## Study and physics",
                "",
                f"- Study: `{spec.study.kind}`",
                f"- Equations: {', '.join(item.value for item in spec.physics.equations)}",
                f"- Models: {', '.join(spec.physics.models) or 'none'}",
                f"- Temperature: {_display(spec.physics.temperature.model_dump(mode='json'))}",
            ]
        )
        study = spec.study.model_dump(mode="json", exclude_none=True)
        for key, value in study.items():
            if key in {"kind", "maximum_retries"}:
                continue
            lines.append(f"- {key.replace('_', ' ').title()}: {_display(value)}")
        lines.extend(["", "## Requested observables", ""])
        lines.extend(f"- `{observable.value}`" for observable in spec.observables)
        if spec.profile_sampling:
            lines.extend(
                [
                    "",
                    "## Spatial profile points",
                    "",
                    _display(spec.profile_sampling.model_dump(mode="json")),
                ]
            )
            biases = ", ".join(f"{value:g} V" for value in spec.profile_bias_values_v())
            lines.append(f"Selected biases: {biases}")
            if spec.profile_sampling.mode == "automatic":
                lines.append(
                    "Selection uses approved schedule quantiles, "
                    "not inferred physical regime labels."
                )
        lines.extend(["", "## Scientific input ledger", ""])
        for record in prepared.completeness.records:
            if record.path.rsplit(".", 1)[-1] in {"dimensionality", "magnitude_si", "si_unit"}:
                continue
            value = "unresolved" if record.value is None else _display(record.value)
            lines.append(
                f"- `{record.path}`: {value}  "
                f"Authority: {record.authority.value}. Status: {record.status.value}."
            )
        if prepared.warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in prepared.warnings)
        lines.extend(["", "Approval applies only to the exact plan digest above.", ""])
        return "\n".join(lines)
