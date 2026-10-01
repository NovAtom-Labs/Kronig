"""Trace requested scientific outputs to canonical result evidence."""

from enum import StrEnum

from pydantic import Field

from tcad_agent.domain.models import ExperimentSpec, Observable, StrictModel
from tcad_agent.results.models import CanonicalResult


class TraceabilityStatus(StrEnum):
    SATISFIED = "satisfied"
    UNMET = "unmet"


class DeliverableTrace(StrictModel):
    deliverable: str
    status: TraceabilityStatus
    evidence_datasets: tuple[str, ...] = ()
    rationale: str = Field(min_length=1, max_length=800)


class TraceabilityMatrix(StrictModel):
    schema_version: str = "1.0"
    records: tuple[DeliverableTrace, ...]

    @property
    def complete(self) -> bool:
        return all(record.status is TraceabilityStatus.SATISFIED for record in self.records)


_TERMINAL_PREFIXES = {
    Observable.TERMINAL_CURRENT: ("terminal_current", "terminal_current_density"),
    Observable.TERMINAL_CURRENT_DENSITY: ("terminal_current_density", "terminal_current"),
    Observable.ABSOLUTE_TERMINAL_CURRENT: ("absolute_terminal_current",),
    Observable.TERMINAL_CHARGE: ("terminal_charge",),
    Observable.TERMINAL_ELECTRON_CURRENT: ("terminal_electron_current",),
    Observable.TERMINAL_HOLE_CURRENT: ("terminal_hole_current",),
}


def build_traceability(
    spec: ExperimentSpec,
    result: CanonicalResult,
) -> TraceabilityMatrix:
    dataset_ids = tuple(sorted(result.datasets))
    records = []
    for observable in spec.observables:
        prefixes = _TERMINAL_PREFIXES.get(observable, (observable.value,))
        evidence = tuple(
            dataset_id
            for dataset_id in dataset_ids
            if any(
                dataset_id == prefix or dataset_id.startswith(f"{prefix}__")
                for prefix in prefixes
            )
        )
        if not evidence and observable in _TERMINAL_PREFIXES and result.bias_points:
            evidence = ("operating_points",)
        status = (
            TraceabilityStatus.SATISFIED if evidence else TraceabilityStatus.UNMET
        )
        records.append(
            DeliverableTrace(
                deliverable=observable.value,
                status=status,
                evidence_datasets=evidence,
                rationale=(
                    "Requested output is present in canonical evidence."
                    if evidence
                    else "Requested output is absent from canonical evidence."
                ),
            )
        )
    return TraceabilityMatrix(records=tuple(records))
