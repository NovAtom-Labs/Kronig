"""Carrier-statistics applicability from solved local populations, not doping."""

from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation.datasets import axes_compatible
from tcad_agent.validation.models import ValidationCheck


def statistics_checks(result: CanonicalResult) -> tuple[ValidationCheck, ...]:
    identifier = "carrier-statistics-applicability"
    models = result.metadata.get("physics_models", [])
    mandatory = bool(result.metadata.get("validation_evidence_version"))
    paths = (
        "result.datasets.electron_density",
        "result.datasets.hole_density",
        "result.datasets.effective_density_conduction",
        "result.datasets.effective_density_valence",
    )

    def check(status, message, **values):
        return (
            ValidationCheck(
                id=identifier,
                level="physical",
                status=status,
                message=message,
                evidence_paths=paths,
                **values,
            ),
        )

    if "fermi" in models:
        return check(
            "not_applicable",
            "Fermi statistics selected; the nondegenerate Boltzmann domain restriction "
            "does not apply. This does not certify the Fermi primitive's calibration.",
        )
    if "boltzmann" not in models:
        return check(
            "not_applicable",
            "Selected carrier statistics were not recorded in canonical provenance.",
        )
    ratios = []
    for carrier, states in (
        ("electron_density", "effective_density_conduction"),
        ("hole_density", "effective_density_valence"),
    ):
        density, dos = result.datasets.get(carrier), result.datasets.get(states)
        if density is None or dos is None:
            return check(
                "failed" if mandatory else "not_applicable",
                "Local carrier population and effective density-of-states evidence is "
                "incomplete; Boltzmann applicability was not verified.",
            )
        if (
            density.unit != "m^-3"
            or dos.unit != "m^-3"
            or not axes_compatible(result, density, dos)
        ):
            return check(
                "failed",
                "Statistics evidence requires matching local coordinates and canonical "
                "concentration units.",
            )
        for n, nc, valid_n, valid_nc in zip(
            density.values,
            dos.values,
            density.validity or (True,) * len(density.values),
            dos.validity or (True,) * len(dos.values),
            strict=True,
        ):
            if not valid_n or not valid_nc:
                if mandatory:
                    return check(
                        "failed",
                        "Mandatory local statistics evidence contains invalid samples; "
                        "a valid subset cannot prove applicability.",
                    )
                continue
            if nc <= 0 or n < 0:
                return check(
                    "failed",
                    "Local density of states must be positive and carrier populations nonnegative.",
                )
            ratios.append(n / nc)
    if not ratios:
        return check("not_applicable", "No jointly valid local carrier samples are available.")
    # Conservative nondegenerate domain: n/Nc, p/Nv <= 0.1.
    # The first Fermi-integral correction is approximately population/(2**1.5 DOS).
    maximum = max(ratios)
    return check(
        "passed" if maximum <= 0.1 else "failed",
        "Boltzmann statistics require dilute local populations (n/Nc and p/Nv <= 0.1). "
        "High accumulation or injection can violate this even with lightly doped bulk. "
        "Explicit physics was not changed; review a Fermi-statistics plan.",
        measured_value=maximum,
        limit=0.1,
        unit="1",
        evidence_origin="derived",
    )
