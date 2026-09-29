"""Layered validators that do not depend on an LLM."""

from __future__ import annotations

import math

from tcad_agent.domain.models import EquilibriumStudy, ExperimentSpec, Observable
from tcad_agent.recovery.models import FailureKind, FailureRecord
from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.analytical import built_in_potential_reference
from tcad_agent.validation.convergence import convergence_checks
from tcad_agent.validation.datasets import dataset_checks
from tcad_agent.validation.models import (
    EvidenceOrigin,
    ValidationCheck,
    ValidationReport,
    ValidationStatus,
)
from tcad_agent.validation.physics import physics_checks


class ValidationEngine:
    def __init__(
        self,
        current_rtol: float = 1e-4,
        current_atol: float = 1e-6,
        equilibrium_current_atol: float = 1e-6,
        built_in_potential_rtol: float = 0.10,
        built_in_potential_atol: float = 0.02,
    ) -> None:
        tolerances = (
            current_rtol,
            current_atol,
            equilibrium_current_atol,
            built_in_potential_rtol,
            built_in_potential_atol,
        )
        if any(value < 0 for value in tolerances):
            raise ValueError("validation tolerances must be nonnegative")
        self.current_rtol = current_rtol
        self.current_atol = current_atol
        self.equilibrium_current_atol = equilibrium_current_atol
        self.built_in_potential_rtol = built_in_potential_rtol
        self.built_in_potential_atol = built_in_potential_atol

    def validate(
        self,
        result: CanonicalResult,
        *,
        expected_bias_points: int | None = None,
        require_provenance: bool = True,
        spec: ExperimentSpec | None = None,
    ) -> ValidationReport:
        checks: list[ValidationCheck] = []
        checks.append(
            self._check(
                "execution-status",
                "execution",
                result.status == "completed",
                result.status,
                "completed",
                "Simulator execution must complete before scientific validation.",
                evidence_origin="simulator_observed",
                evidence_paths=("native.status",),
            )
        )
        has_points = bool(result.bias_points)
        checks.append(
            self._check(
                "bias-points-present",
                "numerical",
                has_points,
                len(result.bias_points),
                ">= 1",
                "At least one solved bias point is required.",
                evidence_origin="simulator_observed",
                evidence_paths=("result.bias_points",),
            )
        )
        if expected_bias_points is not None:
            checks.append(
                self._check(
                    "expected-point-count",
                    "numerical",
                    len(result.bias_points) == expected_bias_points,
                    len(result.bias_points),
                    expected_bias_points,
                    "Solved bias point count must match the approved study.",
                    evidence_paths=("experiment.study", "result.bias_points"),
                )
            )
        converged = all(point.converged for point in result.bias_points) and has_points
        checks.append(
            self._check(
                "all-points-converged",
                "numerical",
                converged,
                sum(point.converged for point in result.bias_points),
                len(result.bias_points),
                "Every returned bias point must converge.",
                evidence_origin="simulator_observed",
                evidence_paths=("result.bias_points[*].converged",),
            )
        )
        finite = self._all_values_finite(result)
        checks.append(
            self._check(
                "finite-values",
                "numerical",
                finite,
                "finite" if finite else "non-finite",
                "finite",
                "Currents, biases, coordinates, and fields must contain finite numbers.",
                evidence_paths=("result.bias_points", "result.fields"),
            )
        )
        checks.extend(dataset_checks(result))
        checks.extend(convergence_checks(result))
        checks.extend(physics_checks(result))
        monotonic = True
        checks.append(
            self._check(
                "monotonic-bias",
                "numerical",
                monotonic,
                "monotonic" if monotonic else "non-monotonic",
                "monotonic",
                (
                    "Bias points preserve researcher order; directional constraints "
                    "are study-specific."
                ),
                evidence_paths=("result.bias_points[*].bias_v",),
            )
        )
        max_imbalance, max_limit = self._current_imbalance(result)
        checks.append(
            self._check(
                "terminal-current-conservation",
                "physical",
                max_imbalance <= max_limit and has_points,
                max_imbalance,
                max_limit,
                "The algebraic sum of terminal currents must satisfy the configured tolerance.",
                evidence_paths=("result.bias_points[*].terminal_currents_a_per_m2",),
            )
        )
        nonnegative = all(
            value >= 0
            for name, field in result.fields.items()
            if name in {"electron_density", "hole_density"}
            for value in field.values
        )
        checks.append(
            self._check(
                "nonnegative-carrier-density",
                "physical",
                nonnegative,
                "nonnegative" if nonnegative else "negative",
                ">= 0 m^-3",
                "Classical carrier densities cannot be negative.",
                evidence_paths=("result.fields.electron_density", "result.fields.hole_density"),
            )
        )
        if spec is not None:
            checks.append(self._requested_observables_check(result, spec))
        if spec is not None and isinstance(spec.study, EquilibriumStudy):
            checks.extend(self._equilibrium_checks(result, spec))
        if require_provenance:
            checks.append(
                self._check(
                    "simulator-version-recorded",
                    "provenance",
                    bool(result.simulator_version),
                    result.simulator_version or "missing",
                    "non-empty",
                    "A simulator version is required for reproducibility.",
                    evidence_origin="simulator_observed",
                    evidence_paths=("result.simulator_version",),
                )
            )
        overall: ValidationStatus = "passed"
        if any(check.status == "failed" for check in checks):
            overall = "failed"
        elif any(check.status == "warning" for check in checks):
            overall = "warning"
        return ValidationReport(overall=overall, checks=tuple(checks))

    def classify_failures(
        self,
        result: CanonicalResult,
        *,
        spec: ExperimentSpec | None = None,
    ) -> tuple[FailureRecord, ...]:
        if result.status == "execution_failed":
            return (
                FailureRecord(
                    kind=FailureKind.EXECUTION,
                    evidence=result.error or result.status,
                ),
            )
        if result.status == "timed_out":
            return (
                FailureRecord(
                    kind=FailureKind.TIMEOUT,
                    evidence=result.error or result.status,
                ),
            )
        if result.status == "malformed_result":
            return (
                FailureRecord(
                    kind=FailureKind.MALFORMED_OUTPUT,
                    evidence=result.error or result.status,
                ),
            )

        failures: list[FailureRecord] = []
        if result.bias_points and not all(point.converged for point in result.bias_points):
            failures.append(
                FailureRecord(
                    kind=FailureKind.NON_CONVERGENCE,
                    evidence="one or more bias points did not converge",
                )
            )
        if not self._all_values_finite(result):
            failures.append(
                FailureRecord(
                    kind=FailureKind.NONFINITE_RESULT,
                    evidence="canonical result contains NaN or infinite values",
                )
            )
            return tuple(failures)

        report = self.validate(result, spec=spec)
        if report.checks_by_id["terminal-current-conservation"].status == "failed":
            failures.append(
                FailureRecord(
                    kind=FailureKind.CONSERVATION,
                    evidence="terminal current conservation check failed",
                )
            )
        if report.checks_by_id["nonnegative-carrier-density"].status == "failed":
            failures.append(
                FailureRecord(
                    kind=FailureKind.PHYSICAL_SANITY,
                    evidence="carrier density sanity check failed",
                )
            )
        for check_id in ("equilibrium-terminal-current", "built-in-potential-reference"):
            check = report.checks_by_id.get(check_id)
            if check is not None and check.status == "failed":
                failures.append(
                    FailureRecord(
                        kind=FailureKind.PHYSICAL_SANITY,
                        evidence=f"{check_id} check failed",
                    )
                )
        observables = report.checks_by_id.get("requested-observables-present")
        if observables is not None and observables.status == "failed":
            failures.append(
                FailureRecord(
                    kind=FailureKind.MALFORMED_OUTPUT,
                    evidence="one or more approved observables are missing",
                )
            )
        return tuple(failures)

    @staticmethod
    def _requested_observables_check(
        result: CanonicalResult,
        spec: ExperimentSpec,
    ) -> ValidationCheck:
        missing: list[str] = []
        for observable in spec.observables:
            if observable is Observable.TERMINAL_CURRENT:
                complete_currents = bool(result.terminals) and bool(result.bias_points) and all(
                    set(result.terminals).issubset(point.terminal_currents_a_per_m2)
                    for point in result.bias_points
                )
                if not complete_currents:
                    missing.append(observable.value)
            elif observable is Observable.TERMINAL_CHARGE:
                complete_charge = bool(result.terminals) and bool(result.operating_points) and all(
                    set(result.terminals).issubset(point.terminal_charges_c_per_m2)
                    for point in result.operating_points
                )
                if not complete_charge:
                    missing.append(observable.value)
            else:
                dataset = result.datasets.get(observable.value)
                available = observable.value in result.fields or (
                    dataset is not None and dataset.source != "legacy-field-migration"
                )
                if not available:
                    missing.append(observable.value)
        measured = "complete" if not missing else f"missing: {', '.join(sorted(missing))}"
        return ValidationEngine._check(
            "requested-observables-present",
            "provenance",
            not missing,
            measured,
            "all approved observables",
            "Every observable in the approved experiment must appear in canonical results.",
            evidence_paths=("experiment.observables", "result.fields", "result.bias_points"),
        )

    def _equilibrium_checks(
        self,
        result: CanonicalResult,
        spec: ExperimentSpec,
    ) -> tuple[ValidationCheck, ...]:
        currents = [
            abs(value)
            for point in result.bias_points
            for value in point.terminal_currents_a_per_m2.values()
        ]
        maximum_current = max(currents, default=math.inf)
        checks = [
            self._check(
                "equilibrium-terminal-current",
                "physical",
                maximum_current <= self.equilibrium_current_atol,
                maximum_current,
                self.equilibrium_current_atol,
                "Every terminal current density must approach zero at thermal equilibrium.",
                evidence_paths=(
                    "experiment.study.kind",
                    "result.bias_points[*].terminal_currents_a_per_m2",
                ),
            )
        ]

        reference = built_in_potential_reference(spec)
        if reference is None:
            checks.append(
                ValidationCheck(
                    id="built-in-potential-reference",
                    level="physical",
                    status="not_applicable",
                    message=(
                        "The approved experiment is outside the reviewed abrupt silicon "
                        "p-n analytical reference domain."
                    ),
                    evidence_origin="configured",
                    evidence_paths=("experiment.json",),
                )
            )
            return tuple(checks)

        potential = result.fields.get("potential")
        if potential is None or potential.unit != "V" or not potential.values:
            checks.append(
                self._check(
                    "built-in-potential-reference",
                    "physical",
                    False,
                    "missing potential field in V",
                    reference.value_v,
                    "Built-in potential requires a normalized electrostatic potential field.",
                    evidence_paths=("result.fields.potential", reference.source),
                )
            )
            return tuple(checks)

        measured = max(potential.values) - min(potential.values)
        passed = math.isclose(
            measured,
            reference.value_v,
            rel_tol=self.built_in_potential_rtol,
            abs_tol=self.built_in_potential_atol,
        )
        checks.append(
            self._check(
                "built-in-potential-reference",
                "physical",
                passed,
                measured,
                (
                    f"{reference.value_v:.6g} V ± "
                    f"{self.built_in_potential_rtol:.0%} or "
                    f"{self.built_in_potential_atol:.6g} V"
                ),
                "Potential range must agree with the reviewed abrupt p-n analytical reference.",
                evidence_paths=("result.fields.potential", reference.source),
            )
        )
        return tuple(checks)

    def _current_imbalance(self, result: CanonicalResult) -> tuple[float, float]:
        worst_imbalance = 0.0
        worst_limit = self.current_atol
        for point in result.bias_points:
            currents = tuple(point.terminal_currents_a_per_m2.values())
            imbalance = abs(sum(currents))
            scale = max((abs(value) for value in currents), default=0.0)
            limit = self.current_atol + self.current_rtol * scale
            if imbalance > worst_imbalance:
                worst_imbalance = imbalance
                worst_limit = limit
        return worst_imbalance, worst_limit

    @staticmethod
    def _all_values_finite(result: CanonicalResult) -> bool:
        values: list[float] = []
        for bias_point in result.bias_points:
            values.append(bias_point.bias_v)
            values.extend(bias_point.terminal_currents_a_per_m2.values())
        for field in result.fields.values():
            values.extend(field.positions_m)
            values.extend(field.values)
        for axis in result.axes.values():
            values.extend(axis.values)
        for dataset in result.datasets.values():
            values.extend(dataset.values)
            if dataset.imaginary_values is not None:
                values.extend(dataset.imaginary_values)
        for operating_point in result.operating_points:
            values.extend(operating_point.coordinates.values())
            values.extend(operating_point.terminal_currents_a_per_m2.values())
            values.extend(operating_point.terminal_charges_c_per_m2.values())
        return all(math.isfinite(value) for value in values)

    @staticmethod
    def _check(
        check_id: str,
        level: str,
        passed: bool,
        measured: float | int | str,
        limit: float | int | str,
        message: str,
        evidence_origin: EvidenceOrigin = "derived",
        evidence_paths: tuple[str, ...] = (),
    ) -> ValidationCheck:
        return ValidationCheck.model_validate(
            {
                "id": check_id,
                "level": level,
                "status": "passed" if passed else "failed",
                "measured_value": measured,
                "limit": limit,
                "message": message,
                "evidence_origin": evidence_origin,
                "evidence_paths": evidence_paths,
            }
        )
