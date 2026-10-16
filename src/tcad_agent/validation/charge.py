"""Integrated one-dimensional Gauss balance, including region and sheet charge."""

from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.datasets import axes_compatible
from tcad_agent.validation.models import ValidationCheck
from tcad_agent.validation.physics import _position_profiles


def integrated_charge_check(
    result: CanonicalResult, *, relative_tolerance: float, absolute_tolerance: float
) -> ValidationCheck:
    paths = (
        "result.datasets.charge_density",
        "result.datasets.validation_sheet_charge",
        "result.operating_points[*].terminal_charges_c_per_m2",
    )

    def check(status, message, **values):
        return ValidationCheck(
            id="contact-charge-balance",
            level="physical",
            status=status,
            message=message,
            unit="C/m^2",
            evidence_paths=paths,
            **values,
        )

    if result.metadata.get("validation_evidence_version"):
        required = ("charge_density", "validation_charge_weight", "validation_sheet_charge")
        missing = [name for name in required if name not in result.datasets]
        if missing:
            return check(
                "failed", "Required native charge evidence is missing: " + ", ".join(missing)
            )
    bulk = result.datasets.get("charge_density")
    if bulk is None:
        return check("not_applicable", "Integrated bulk-charge evidence is unavailable.")
    if bulk.unit != "C/m^3":
        return check("failed", "Bulk charge must use canonical C/m^3.")
    try:
        positions, study, profiles = _position_profiles(result, bulk)
    except ValueError as exc:
        return check("failed", str(exc))
    points = result.operating_points
    if len(profiles) != len(points) or not points:
        return check("failed", "Bulk-charge profiles must match all operating points.")
    if study and any(
        study[1][i] != point.coordinates.get(study[0]) for i, point in enumerate(points)
    ):
        return check("failed", "Charge profiles and terminal operating coordinates differ.")
    sheet = result.datasets.get("validation_sheet_charge")
    if sheet and (sheet.unit != "C/m^2" or len(sheet.values) != len(points)):
        return check("failed", "Sheet-charge evidence must match operating points in C/m^2.")
    residuals, limits, scales = [], [], []
    weights = result.datasets.get("validation_charge_weight")
    weight_profiles = None
    if weights is not None:
        if weights.unit != "m" or not axes_compatible(result, bulk, weights):
            return check(
                "failed",
                "Poisson integration weights require matching charge coordinates "
                "and units of length.",
            )
        _, _, weight_profiles = _position_profiles(result, weights)
    for i, (point, (values, valid)) in enumerate(zip(points, profiles, strict=True)):
        if point.state != "converged":
            continue
        if not all(valid) or (sheet and sheet.validity and not sheet.validity[i]):
            return check("failed", "Converged point contains invalid charge evidence.")
        if (
            not set(result.terminals) <= point.terminal_charges_c_per_m2.keys()
            or not result.terminals
        ):
            return check("failed", "Every declared terminal must have a finite charge.")
        integrated = sum(
            (right - left) * (a + b) / 2
            for left, right, a, b in zip(
                positions[:-1], positions[1:], values[:-1], values[1:], strict=True
            )
            if right > left
        )
        if weight_profiles is not None:
            local_weights, valid_weights = weight_profiles[i]
            if not all(valid_weights) or any(w < 0 for w in local_weights):
                return check("failed", "Invalid Poisson control-volume integration weights.")
            integrated = sum(q * w for q, w in zip(values, local_weights, strict=True))
        # Native interface sheet values are Poisson source charges; their physical
        # charge has the opposite sign. Bulk evidence is physical rho, not source rho.
        source_sheet = sheet.values[i] if sheet else 0.0
        terminal = sum(point.terminal_charges_c_per_m2.values())
        scale = max(
            abs(integrated),
            abs(source_sheet),
            sum(abs(q) for q in point.terminal_charges_c_per_m2.values()),
        )
        residuals.append(abs(terminal + integrated - source_sheet))
        scales.append(scale)
        limits.append(absolute_tolerance + relative_tolerance * scale)
    if not residuals:
        return check("not_applicable", "No converged charge-balance operating point is available.")
    worst = max(range(len(residuals)), key=lambda i: residuals[i] / max(limits[i], 1e-300))
    return check(
        "passed" if all(a <= b for a, b in zip(residuals, limits, strict=True)) else "failed",
        "Contact displacement flux plus bulk charge integrated over the recorded native "
        "Poisson control volumes must balance interface sheet sources at every converged "
        "point. Fixed-potential contact nodes replace bulk Poisson rows and are not counted "
        "twice. This checks discrete Gauss consistency, not continuum quadrature accuracy; "
        "independent mesh verification evaluates spatial resolution.",
        measured_value=residuals[worst],
        limit=limits[worst],
        scale=scales[worst],
        absolute_tolerance=absolute_tolerance,
        relative_tolerance=relative_tolerance,
        evidence_origin="derived",
    )
