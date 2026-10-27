"""Layered validators that do not depend on an LLM."""

from __future__ import annotations

import math

from tcad_agent.domain.models import EquilibriumStudy, ExperimentSpec, Observable
from tcad_agent.domain.profiles import FixedChargeProfile
from tcad_agent.domain.studies import (
    ACStudy,
    DCPointsStudy,
    DCStudy,
    FrequencyStudy,
    expand_study_points,
)
from tcad_agent.recovery.models import FailureKind, FailureRecord
from tcad_agent.results.models import CanonicalResult
from tcad_agent.results.presentation import display_projection
from tcad_agent.validation.analytical import built_in_potential_reference
from tcad_agent.validation.charge import integrated_charge_check
from tcad_agent.validation.convergence import convergence_checks
from tcad_agent.validation.datasets import dataset_checks
from tcad_agent.validation.models import (
    EvidenceOrigin,
    ValidationCheck,
    ValidationReport,
    ValidationStatus,
)
from tcad_agent.validation.physics import (
    band_checks,
    capacitance_consistency_checks,
    physics_checks,
    poisson_residual_checks,
    recombination_checks,
    sweep_continuity_checks,
)
from tcad_agent.validation.policy import validation_policy_digest
from tcad_agent.validation.refinement import mesh_stability_check
from tcad_agent.validation.statistics import statistics_checks


def _peak_doping_cm3(spec: ExperimentSpec) -> float:
    """Highest dopant concentration any profile carries, whatever its shape.

    A box, Gaussian or error-function source/drain is as noisy as a uniform one, so every
    profile's concentration-valued fields count; charge densities and tables do not.
    """
    peak = 0.0
    for profile in spec.profiles:
        for name in ("value", "peak", "surface_value", "start_value", "end_value"):
            quantity = getattr(profile, name, None)
            if quantity is None or getattr(profile, "kind", "") == "fixed_charge":
                continue
            try:
                peak = max(peak, quantity.to("cm^-3"))
            except Exception:  # noqa: BLE001 - a value in other units is not a concentration
                continue
    return peak


class ValidationEngine:
    def __init__(
        self,
        current_rtol: float = 1e-4,
        current_atol: float = 1e-6,
        equilibrium_current_atol: float = 1e-6,
        built_in_potential_rtol: float = 0.10,
        built_in_potential_atol: float = 0.02,
        contact_charge_rtol: float = 0.03,
        contact_charge_atol: float = 1e-10,
        current_noise_per_doping: float = 0.0,
    ) -> None:
        tolerances = (
            current_rtol,
            current_atol,
            equilibrium_current_atol,
            built_in_potential_rtol,
            built_in_potential_atol,
            contact_charge_rtol,
            contact_charge_atol,
            current_noise_per_doping,
        )
        if any(not math.isfinite(value) or value < 0 for value in tolerances):
            raise ValueError("validation tolerances must be finite and nonnegative")
        self.current_rtol = current_rtol
        self.current_atol = current_atol
        self.equilibrium_current_atol = equilibrium_current_atol
        self.built_in_potential_rtol = built_in_potential_rtol
        self.built_in_potential_atol = built_in_potential_atol
        self.contact_charge_rtol = contact_charge_rtol
        self.contact_charge_atol = contact_charge_atol
        self.current_noise_per_doping = current_noise_per_doping

    def _doping_noise_floor(self, spec: ExperimentSpec | None) -> float:
        """Current-density evaluation noise (A/m^2) a backend declares for this experiment.

        Opposing drift and diffusion fluxes cancel to zero at equilibrium; the leftover
        scales with the carrier concentration, so the declared coefficient (A/m^2 per cm^-3)
        multiplies the highest doping in the experiment. Zero for backends that declare none.
        """
        if spec is None or not self.current_noise_per_doping:
            return 0.0
        return self.current_noise_per_doping * _peak_doping_cm3(spec)

    def _current_atol(self, spec: ExperimentSpec | None) -> float:
        return max(self.current_atol, self._doping_noise_floor(spec))

    def _equilibrium_current_atol(self, spec: ExperimentSpec | None) -> float:
        return max(self.equilibrium_current_atol, self._doping_noise_floor(spec))

    @classmethod
    def for_backend(cls, backend: str) -> ValidationEngine:
        """Engine whose limits include the numerical floors the backend declares.

        A declared floor states how precisely that simulator evaluates a quantity; the
        limits actually used are always recorded in the validation report.
        """
        from tcad_agent.capabilities.models import CapabilityManifest

        declared = CapabilityManifest.from_backend(backend).validation_limits
        unknown = set(declared) - set(cls().acceptance_limits())
        if unknown:
            raise ValueError(f"unknown validation limits declared by {backend}: {sorted(unknown)}")
        return cls(**declared)

    def acceptance_limits(self) -> dict[str, float]:
        """Return configured scientific acceptance, separate from solver controls."""
        return {
            "current_rtol": self.current_rtol,
            "current_atol": self.current_atol,
            "equilibrium_current_atol": self.equilibrium_current_atol,
            "built_in_potential_rtol": self.built_in_potential_rtol,
            "built_in_potential_atol": self.built_in_potential_atol,
            "contact_charge_rtol": self.contact_charge_rtol,
            "contact_charge_atol": self.contact_charge_atol,
            "current_noise_per_doping": self.current_noise_per_doping,
        }

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
        points = result.bias_points or result.operating_points
        point_converged = tuple(
            getattr(point, "converged", getattr(point, "state", None) == "converged")
            for point in points
        )
        has_points = bool(points)
        checks.append(
            self._check(
                "bias-points-present",
                "numerical",
                has_points,
                len(points),
                ">= 1",
                "At least one solved operating point is required.",
                evidence_origin="simulator_observed",
                evidence_paths=("result.bias_points",),
            )
        )
        if expected_bias_points is not None:
            checks.append(
                self._check(
                    "expected-point-count",
                    "numerical",
                    len(points) == expected_bias_points,
                    len(points),
                    expected_bias_points,
                    "Solved operating point count must match the approved study.",
                    evidence_paths=("experiment.study", "result.bias_points"),
                )
            )
        converged = all(point_converged) and has_points
        checks.append(
            self._check(
                "all-points-converged",
                "numerical",
                converged,
                sum(point_converged),
                len(points),
                "Every returned operating point must converge.",
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
        checks.extend(statistics_checks(result))
        checks.append(mesh_stability_check(result))
        checks.extend(poisson_residual_checks(result))
        checks.extend(
            sweep_continuity_checks(
                result, absolute_noise_floors={"A/m^2": self._current_atol(spec)}
            )
        )
        checks.extend(capacitance_consistency_checks(result))
        checks.extend(band_checks(result))
        checks.extend(recombination_checks(result))
        checks.append(self._requested_study_order(result, spec))
        if spec and isinstance(spec.study, ACStudy | FrequencyStudy):
            count = 1 if isinstance(spec.study, ACStudy) else len(expand_study_points(spec.study))
            if spec.study.bias_schedule:
                count *= len(expand_study_points(spec.study.bias_schedule))
            dataset = result.datasets.get(f"ac_capacitance__{spec.study.contact}")
            complete = (
                dataset is not None
                and len(dataset.values) == count
                and (dataset.validity is None or all(dataset.validity))
            )
            checks.append(
                self._check(
                    "small-signal-grid-complete",
                    "numerical",
                    complete,
                    sum(dataset.validity)
                    if dataset and dataset.validity
                    else len(dataset.values)
                    if dataset
                    else 0,
                    count,
                    "Every approved bias-frequency point must have a valid small-signal response.",
                    evidence_origin="simulator_observed",
                    evidence_paths=(f"result.datasets.ac_capacitance__{spec.study.contact}",),
                )
            )
        checks.append(self._terminal_current_check(result, spec))
        checks.append(self._carrier_density_check(result))
        if spec is not None:
            checks.append(self._requested_observables_check(result, spec))
            try:
                display_projection(result, spec.display_units)
                display_check = ValidationCheck(
                    id="requested-display-units",
                    level="provenance",
                    status="passed" if spec.display_units else "not_applicable",
                    message="Every requested display quantity has "
                    "dimension-compatible canonical evidence."
                    if spec.display_units
                    else "No explicit output-unit choices were requested.",
                    evidence_paths=("experiment.display_units", "result.datasets"),
                )
            except ValueError as exc:
                display_check = ValidationCheck(
                    id="requested-display-units",
                    level="provenance",
                    status="failed",
                    message=str(exc),
                    evidence_paths=("experiment.display_units", "result.datasets"),
                )
            checks.append(display_check)
            checks.append(self._contact_charge_balance(result, spec))
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
        return ValidationReport(
            overall=overall,
            checks=tuple(checks),
            acceptance_limits=self.acceptance_limits(),
            validation_policy_digest=validation_policy_digest(),
        )

    @staticmethod
    def _requested_study_order(
        result: CanonicalResult, spec: ExperimentSpec | None
    ) -> ValidationCheck:
        schedule = (getattr(spec.study, "bias_schedule", None) or spec.study) if spec else None
        if not isinstance(schedule, DCStudy | DCPointsStudy):
            return ValidationCheck(
                id="requested-study-order",
                level="numerical",
                status="not_applicable",
                message="An approved DC schedule is required for order validation.",
                evidence_origin="configured",
                evidence_paths=("experiment.study", "result.bias_points"),
            )
        expected = tuple(value.to("V") for value in expand_study_points(schedule))
        measured = tuple(point.bias_v for point in result.bias_points)
        matches = len(expected) == len(measured) and all(
            math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-15)
            for left, right in zip(expected, measured, strict=True)
        )
        return ValidationCheck(
            id="requested-study-order",
            level="numerical",
            status="passed" if matches else "failed",
            measured_value=str(measured),
            limit=str(expected),
            message=(
                "Returned DC points must preserve the exact approved order, including "
                "reverse or bidirectional schedules."
            ),
            evidence_origin="derived",
            evidence_paths=("experiment.study", "result.bias_points[*].bias_v"),
        )

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
        points = result.bias_points or result.operating_points
        if points and not all(
            getattr(point, "converged", getattr(point, "state", None) == "converged")
            for point in points
        ):
            failures.append(
                FailureRecord(
                    kind=FailureKind.NON_CONVERGENCE,
                    evidence="one or more operating points did not converge",
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
            if observable in {
                Observable.TERMINAL_CURRENT,
                Observable.TERMINAL_CURRENT_DENSITY,
            }:
                complete_currents = (
                    bool(result.terminals)
                    and bool(result.bias_points or result.operating_points)
                    and all(
                        set(result.terminals).issubset(point.terminal_currents_a_per_m2)
                        for point in (result.bias_points or result.operating_points)
                    )
                )
                if not complete_currents:
                    missing.append(observable.value)
            elif observable is Observable.ABSOLUTE_TERMINAL_CURRENT:
                complete_absolute_currents = bool(result.terminals) and all(
                    f"absolute_terminal_current__{terminal}" in result.datasets
                    for terminal in result.terminals
                )
                if not complete_absolute_currents:
                    missing.append(observable.value)
            elif observable is Observable.TERMINAL_CHARGE:
                complete_charge = (
                    bool(result.terminals)
                    and bool(result.operating_points)
                    and all(
                        set(result.terminals).issubset(point.terminal_charges_c_per_m2)
                        for point in result.operating_points
                    )
                )
                if not complete_charge:
                    missing.append(observable.value)
            elif observable in {
                Observable.TERMINAL_ELECTRON_CURRENT,
                Observable.TERMINAL_HOLE_CURRENT,
            }:
                prefix = f"{observable.value}__"
                complete_components = bool(result.terminals) and all(
                    f"{prefix}{terminal}" in result.datasets for terminal in result.terminals
                )
                if not complete_components:
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
        points = tuple(
            point
            for point in (result.operating_points or result.bias_points)
            if getattr(point, "converged", getattr(point, "state", None) == "converged")
        )
        currents = [
            abs(value) for point in points for value in point.terminal_currents_a_per_m2.values()
        ]
        maximum_current = max(currents) if currents else None
        equilibrium_atol = self._equilibrium_current_atol(spec)
        complete = bool(points) and all(
            len(point.terminal_currents_a_per_m2) >= 2
            and set(result.terminals).issubset(point.terminal_currents_a_per_m2)
            for point in points
        )
        checks = [
            ValidationCheck(
                id="equilibrium-terminal-current",
                level="physical",
                status="not_applicable"
                if not currents
                else "passed"
                if complete
                and maximum_current is not None
                and maximum_current <= equilibrium_atol
                else "failed",
                measured_value=maximum_current
                if maximum_current is None or math.isfinite(maximum_current)
                else "nonfinite currents",
                limit=equilibrium_atol,
                unit="A/m^2",
                absolute_tolerance=equilibrium_atol,
                relative_tolerance=0,
                scale=maximum_current
                if maximum_current is not None and math.isfinite(maximum_current)
                else None,
                message="Every terminal current density must approach zero at thermal equilibrium."
                if currents
                else "No converged terminal-current evidence is available.",
                evidence_paths=(
                    "experiment.study.kind",
                    "result.operating_points[*].terminal_currents_a_per_m2",
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

    def _contact_charge_balance(
        self,
        result: CanonicalResult,
        spec: ExperimentSpec,
    ) -> ValidationCheck:
        if result.metadata.get("validation_evidence_version"):
            return integrated_charge_check(
                result,
                relative_tolerance=self.contact_charge_rtol,
                absolute_tolerance=self.contact_charge_atol,
            )
        if any(region.material == "silicon" for region in spec.regions):
            return ValidationCheck(
                id="contact-charge-balance",
                level="physical",
                status="not_applicable",
                message=(
                    "Bulk semiconductor charge requires a volume integral before "
                    "terminal charge balance can be evaluated."
                ),
                evidence_origin="configured",
                evidence_paths=("experiment.regions",),
            )
        points = tuple(point for point in result.operating_points if point.state == "converged")
        if not any(point.terminal_charges_c_per_m2 for point in points):
            return ValidationCheck(
                id="contact-charge-balance",
                level="physical",
                status="not_applicable",
                message="Canonical terminal-charge values are unavailable.",
                evidence_paths=("result.operating_points",),
            )
        if any(
            len(point.terminal_charges_c_per_m2) < 2
            or not set(result.terminals).issubset(point.terminal_charges_c_per_m2)
            or not all(math.isfinite(value) for value in point.terminal_charges_c_per_m2.values())
            for point in points
        ):
            return ValidationCheck(
                id="contact-charge-balance",
                level="physical",
                status="failed",
                message="Charge balance requires finite charge at every declared terminal.",
                unit="C/m^2",
                evidence_paths=("result.operating_points",),
            )
        elementary_charge = 1.602176634e-19
        configured_sheet_charge = elementary_charge * sum(
            interface.fixed_charge_density.to("m^-2")
            for interface in spec.interfaces
            if interface.fixed_charge_density is not None
        )
        regions = {region.id: region for region in spec.regions}
        configured_sheet_charge += sum(
            profile.density.to("C/m^3")
            * (regions[profile.region].x1.to("m") - regions[profile.region].x0.to("m"))
            for profile in spec.profiles
            if isinstance(profile, FixedChargeProfile)
        )
        errors = tuple(
            abs(sum(point.terminal_charges_c_per_m2.values()) - configured_sheet_charge)
            for point in points
        )
        maximum_error = max(errors, default=math.inf)
        limit = self.contact_charge_atol + self.contact_charge_rtol * abs(configured_sheet_charge)
        return ValidationCheck(
            id="contact-charge-balance",
            level="physical",
            status="passed" if maximum_error <= limit else "failed",
            measured_value=maximum_error,
            limit=limit,
            unit="C/m^2",
            absolute_tolerance=self.contact_charge_atol,
            relative_tolerance=self.contact_charge_rtol,
            scale=abs(configured_sheet_charge),
            message=(
                "Terminal displacement charge must balance configured dielectric "
                "interface sheet charge."
            ),
            evidence_paths=(
                "experiment.interfaces[*].fixed_charge_density",
                "result.operating_points[*].terminal_charges_c_per_m2",
            ),
        )

    def _terminal_current_check(
        self, result: CanonicalResult, spec: ExperimentSpec | None = None
    ) -> ValidationCheck:
        current_atol = self._current_atol(spec)
        points = tuple(
            point
            for point in (result.operating_points or result.bias_points)
            if getattr(point, "converged", getattr(point, "state", None) == "converged")
        )
        paths = (
            "result.operating_points[*].terminal_currents_a_per_m2",
            "result.bias_points[*].terminal_currents_a_per_m2",
        )
        if not any(point.terminal_currents_a_per_m2 for point in points):
            return ValidationCheck(
                id="terminal-current-conservation",
                level="physical",
                status="not_applicable",
                message="No converged terminal-current evidence is available.",
                evidence_paths=paths,
                unit="A/m^2",
            )
        if any(
            not result.terminals
            or not set(result.terminals).issubset(point.terminal_currents_a_per_m2)
            for point in points
        ):
            return ValidationCheck(
                id="terminal-current-conservation",
                level="physical",
                status="failed",
                message=(
                    "Current conservation requires every declared terminal at each valid point."
                ),
                evidence_paths=paths,
                unit="A/m^2",
            )
        residuals = []
        for point in points:
            currents = tuple(point.terminal_currents_a_per_m2.values())
            if not all(math.isfinite(value) for value in currents):
                return ValidationCheck(
                    id="terminal-current-conservation",
                    level="physical",
                    status="failed",
                    message="Terminal current evidence contains nonfinite numbers.",
                    unit="A/m^2",
                    evidence_paths=paths,
                )
            residual = abs(sum(currents))
            scale = max(abs(value) for value in currents)
            limit = current_atol + self.current_rtol * scale
            ratio = residual / limit if limit else (math.inf if residual else 0.0)
            residuals.append((ratio, residual, limit, scale))
        _ratio, residual, limit, scale = max(residuals)
        return ValidationCheck(
            id="terminal-current-conservation",
            level="physical",
            status="passed" if all(item[1] <= item[2] for item in residuals) else "failed",
            measured_value=residual,
            limit=limit,
            unit="A/m^2",
            absolute_tolerance=current_atol,
            relative_tolerance=self.current_rtol,
            scale=scale,
            message="The algebraic sum of terminal currents must satisfy the configured tolerance.",
            applicability_reason="Complete terminal currents at converged operating points.",
            evidence_paths=paths,
        )

    @staticmethod
    def _carrier_density_check(result: CanonicalResult) -> ValidationCheck:
        values: list[float] = []
        for name in ("electron_density", "hole_density"):
            dataset = result.datasets.get(name)
            if dataset is not None:
                valid = dataset.validity or (True,) * len(dataset.values)
                values.extend(
                    value for value, usable in zip(dataset.values, valid, strict=True) if usable
                )
            elif name in result.fields:
                values.extend(result.fields[name].values)
        return ValidationCheck(
            id="nonnegative-carrier-density",
            level="physical",
            status="not_applicable"
            if not values
            else "passed"
            if all(value >= 0 for value in values)
            else "failed",
            measured_value=min(values) if values else None,
            limit=0.0 if values else None,
            unit="m^-3",
            message="Classical carrier densities cannot be negative."
            if values
            else "No valid canonical carrier-density evidence is available.",
            evidence_paths=("result.datasets.electron_density", "result.datasets.hole_density"),
        )

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
