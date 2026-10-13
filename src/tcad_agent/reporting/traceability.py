"""Trace requested scientific outputs to canonical result evidence."""

import math
from enum import StrEnum

from pydantic import Field

from tcad_agent.domain.models import ExperimentSpec, Observable, StrictModel
from tcad_agent.domain.studies import (
    ACStudy,
    DCPointsStudy,
    DCStudy,
    FrequencyStudy,
    expand_study_points,
)
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
                dataset_id == prefix or dataset_id.startswith(f"{prefix}__") for prefix in prefixes
            )
        )
        evidence = tuple(
            dataset_id for dataset_id in evidence if _valid_dataset(result, dataset_id)
        )
        if observable in _TERMINAL_PREFIXES:
            terminals = {contact.id for contact in spec.contacts}
            if not all(
                any(dataset_id.endswith("__" + terminal) for dataset_id in evidence)
                for terminal in terminals
            ):
                evidence = ()
            attributes = {
                Observable.TERMINAL_CURRENT: "terminal_currents_a_per_m2",
                Observable.TERMINAL_CURRENT_DENSITY: "terminal_currents_a_per_m2",
                Observable.TERMINAL_ELECTRON_CURRENT: "terminal_electron_currents_a_per_m2",
                Observable.TERMINAL_HOLE_CURRENT: "terminal_hole_currents_a_per_m2",
                Observable.TERMINAL_CHARGE: "terminal_charges_c_per_m2",
            }
            attribute = attributes.get(observable)
            points = result.operating_points or result.bias_points
            schedule = (
                spec.study.bias_schedule
                if isinstance(spec.study, ACStudy | FrequencyStudy)
                else spec.study
            )
            if isinstance(schedule, DCStudy | DCPointsStudy):
                requested_biases = tuple(value.to("V") for value in expand_study_points(schedule))
                available_biases = (
                    tuple(point.coordinates.get("bias") for point in result.operating_points)
                    if result.operating_points
                    else tuple(point.bias_v for point in result.bias_points)
                )
                schedule_complete = len(available_biases) == len(requested_biases) and all(
                    value is not None
                    and math.isclose(value, requested, rel_tol=1e-12, abs_tol=1e-12)
                    for value, requested in zip(available_biases, requested_biases, strict=False)
                )
            else:
                requested_points = expand_study_points(schedule) if schedule else ()
                schedule_complete = len(points) == (len(requested_points) or 1)
            if not schedule_complete:
                evidence = ()
            if (
                not evidence
                and attribute
                and points
                and schedule_complete
                and all(
                    getattr(point, "state", None) == "converged"
                    or getattr(point, "converged", False)
                    for point in points
                )
                and all(terminals.issubset(getattr(point, attribute, {})) for point in points)
                and all(
                    math.isfinite(getattr(point, attribute)[terminal])
                    for point in points
                    for terminal in terminals
                )
            ):
                evidence = ("operating_points" if result.operating_points else "bias_points",)
        elif spec.profile_sampling:
            requested = spec.profile_bias_values_v()
            evidence = tuple(
                dataset_id
                for dataset_id in evidence
                if _has_profile_points(result, dataset_id, requested)
            )
        status = TraceabilityStatus.SATISFIED if evidence else TraceabilityStatus.UNMET
        records.append(
            DeliverableTrace(
                deliverable=observable.value,
                status=status,
                evidence_datasets=evidence,
                rationale=(
                    "Requested output is present in canonical evidence."
                    if evidence
                    else "Requested output is missing, invalid, or incomplete "
                    "in canonical evidence."
                ),
            )
        )
    if isinstance(spec.study, ACStudy | FrequencyStudy):
        expected = 1 if isinstance(spec.study, ACStudy) else len(expand_study_points(spec.study))
        if spec.study.bias_schedule:
            expected *= len(expand_study_points(spec.study.bias_schedule))
        dataset_id = "ac_capacitance__" + spec.study.contact
        complete = (
            _valid_dataset(result, dataset_id)
            and len(result.datasets[dataset_id].values) == expected
        )
        records.append(
            DeliverableTrace(
                deliverable="study." + spec.study.kind,
                status=TraceabilityStatus.SATISFIED if complete else TraceabilityStatus.UNMET,
                evidence_datasets=(dataset_id,) if complete else (),
                rationale="Every requested small-signal point has valid canonical evidence."
                if complete
                else "Requested small-signal grid is missing or incomplete.",
            )
        )
    return TraceabilityMatrix(records=tuple(records))


def _valid_dataset(result, dataset_id):
    dataset = result.datasets.get(dataset_id)
    return dataset is not None and (dataset.validity is None or all(dataset.validity))


def _has_profile_points(result, dataset_id, requested):
    dataset = result.datasets[dataset_id]
    axes = [result.axes[axis_id] for axis_id in dataset.axes if result.axes[axis_id].kind == "bias"]
    values = axes[0].values if axes else tuple(point.bias_v for point in result.bias_points)
    return all(
        any(math.isclose(point, value, abs_tol=1e-12, rel_tol=1e-12) for value in values)
        for point in requested
    )
