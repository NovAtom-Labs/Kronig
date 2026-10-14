import pytest

from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.interfaces import Interface1D
from tcad_agent.domain.models import Contact, DCStudy, ExperimentSpec, Region1D
from tcad_agent.domain.studies import (
    ACStudy,
    DCPointsStudy,
    EquilibriumStudy,
    FrequencyStudy,
    ParameterStudy,
    TemperatureStudy,
    TransientStudy,
)


@pytest.mark.parametrize("bias", ["-0.37 V", "0.42 V"])
def test_single_fermi_level_is_not_a_midpoint_substitute_under_bias(
    valid_spec, devsim_manifest, bias
):
    study = DCPointsStudy.model_validate(
        {"kind": "dc_points", "contact": "anode", "values": ["0 V", bias]}
    )
    requested = valid_spec.model_copy(update={"study": study, "observables": ("fermi_level",)})
    decision = CapabilityService().check(requested, devsim_manifest)
    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    issue = next(i for i in decision.issues if i.code == "single_fermi_level_outside_equilibrium")
    assert "quasi" in issue.message.lower()
    assert "midpoint" in issue.message.lower()
    separate = requested.model_copy(
        update={"observables": ("electron_quasi_fermi_level", "hole_quasi_fermi_level")}
    )
    assert CapabilityService().check(separate, devsim_manifest).status is CapabilityStatus.SUPPORTED


def test_single_fermi_level_remains_available_at_equilibrium_and_zero_bias(
    valid_spec, devsim_manifest
):
    for study in (
        EquilibriumStudy(kind="equilibrium"),
        DCPointsStudy.model_validate({"kind": "dc_points", "contact": "anode", "values": ["0 V"]}),
    ):
        spec = valid_spec.model_copy(update={"study": study, "observables": ("fermi_level",)})
        assert CapabilityService().check(spec, devsim_manifest).status is CapabilityStatus.SUPPORTED


@pytest.mark.parametrize("kind", ["ideal_gate", "metal_work_function"])
def test_electrostatic_gate_bias_does_not_imply_split_carrier_fermi_levels(
    valid_spec, devsim_manifest, kind
):
    gate = {"id": "anode", "location": "x_min", "kind": kind}
    if kind == "metal_work_function":
        gate["work_function"] = "4.1 eV"
    spec = valid_spec.model_copy(
        update={
            "regions": (
                valid_spec.regions[0].model_copy(update={"material": "silicon_dioxide"}),
                valid_spec.regions[1],
            ),
            "profiles": (valid_spec.profiles[1],),
            "interfaces": (
                Interface1D.model_validate(
                    {
                        "id": "material_boundary",
                        "left_region": valid_spec.regions[0].id,
                        "right_region": valid_spec.regions[1].id,
                    }
                ),
            ),
            "contacts": (
                Contact.model_validate(gate),
                valid_spec.contacts[1],
            ),
            "study": DCPointsStudy.model_validate(
                {"kind": "dc_points", "contact": "anode", "values": ["-0.6 V", "1.3 V"]}
            ),
            "observables": ("fermi_level",),
        }
    )
    spec = ExperimentSpec.model_validate(spec.model_dump(warnings=False))
    decision = CapabilityService().check(spec, devsim_manifest)
    assert decision.status is CapabilityStatus.SUPPORTED


@pytest.mark.parametrize(
    "observable",
    [
        "electron_drift_current_density",
        "electron_diffusion_current_density",
        "hole_drift_current_density",
        "hole_diffusion_current_density",
        "current_decomposition_residual",
    ],
)
@pytest.mark.parametrize(
    "study",
    [
        ACStudy.model_validate(
            {"kind": "ac", "contact": "anode", "frequency": "1e3 Hz", "amplitude": "0.01 V"}
        ),
        FrequencyStudy.model_validate(
            {
                "kind": "frequency",
                "contact": "anode",
                "start": "1e2 Hz",
                "stop": "1e4 Hz",
                "points": 3,
                "amplitude": "0.01 V",
            }
        ),
        TransientStudy.model_validate(
            {
                "kind": "transient",
                "contact": "anode",
                "waveform": "step",
                "initial_voltage": "0 V",
                "final_voltage": "0.05 V",
                "start": "0 s",
                "stop": "1e-9 s",
                "initial_step": "1e-11 s",
                "maximum_step": "1e-10 s",
            }
        ),
    ],
    ids=["ac", "frequency", "transient"],
)
def test_fermi_decomposition_dynamic_studies_require_their_own_benchmarks(
    valid_spec, devsim_manifest, study, observable
):
    physics = valid_spec.physics.model_copy(
        update={
            "models": tuple(
                "fermi" if model == "boltzmann" else model for model in valid_spec.physics.models
            )
        }
    )
    spec = valid_spec.model_copy(update={"physics": physics, "study": study})
    assert CapabilityService().check(spec, devsim_manifest).status is CapabilityStatus.SUPPORTED
    requested = spec.model_copy(update={"observables": (observable,)})
    decision = CapabilityService().check(requested, devsim_manifest)
    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    issue = next(
        issue for issue in decision.issues if issue.code == "unbenchmarked_diagnostic_study"
    )
    assert issue.requested == f"current_decomposition:fermi:{study.kind}"
    # The restriction is specific to this adapter's diagnostic benchmark envelope.
    other = CapabilityService().check(
        requested, devsim_manifest.model_copy(update={"backend": "sentaurus"})
    )
    assert not any(issue.code == "unbenchmarked_diagnostic_study" for issue in other.issues)
    classical = requested.model_copy(update={"physics": valid_spec.physics})
    assert (
        CapabilityService().check(classical, devsim_manifest).status is CapabilityStatus.SUPPORTED
    )


@pytest.mark.parametrize(
    "study",
    [
        EquilibriumStudy(kind="equilibrium"),
        DCPointsStudy.model_validate(
            {"kind": "dc_points", "contact": "anode", "values": ["0 V", "0.05 V"]}
        ),
        TemperatureStudy.model_validate({"kind": "temperature", "values": ["280 K", "300 K"]}),
        ParameterStudy.model_validate(
            {
                "kind": "parameter",
                "parameter_path": "physics.parameters.electron_lifetime",
                "values": ["1e-8 s", "1e-7 s"],
            }
        ),
    ],
    ids=["equilibrium", "dc_points", "temperature", "parameter"],
)
def test_fermi_decomposition_retains_supported_static_study_compositions(
    valid_spec, devsim_manifest, study
):
    requested = valid_spec.model_copy(
        update={
            "study": study,
            "physics": valid_spec.physics.model_copy(
                update={
                    "models": tuple(
                        "fermi" if model == "boltzmann" else model
                        for model in valid_spec.physics.models
                    )
                }
            ),
            "observables": ("current_decomposition_residual",),
        }
    )
    decision = CapabilityService().check(requested, devsim_manifest)
    assert decision.status is CapabilityStatus.SUPPORTED, decision.issues


def test_fermi_current_components_preserve_requested_statistics_and_contacts(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    spec = valid_spec.model_copy(
        update={
            "physics": valid_spec.physics.model_copy(
                update={
                    "models": tuple(
                        "fermi" if model == "boltzmann" else model
                        for model in valid_spec.physics.models
                    )
                }
            ),
            "contacts": tuple(
                Contact.model_validate(
                    {
                        "id": contact.id,
                        "location": contact.location,
                        "kind": "metal_work_function",
                        "work_function": "4.10 eV",
                    }
                )
                for contact in valid_spec.contacts
            ),
            "observables": (
                "electron_drift_current_density",
                "electron_diffusion_current_density",
                "hole_drift_current_density",
                "hole_diffusion_current_density",
                "current_decomposition_residual",
            ),
        }
    )
    decision = CapabilityService().check(spec, devsim_manifest)
    assert decision.status is CapabilityStatus.SUPPORTED, decision.issues


def test_refuses_model_missing_from_backend(valid_spec: ExperimentSpec) -> None:
    requested = valid_spec.model_copy(
        update={"physics": valid_spec.physics.model_copy(update={"models": ("hydrodynamic",)})}
    )
    manifest = CapabilityManifest.model_validate(
        {
            "backend": "devsim",
            "dimensions": [1],
            "equations": ["poisson"],
            "models": [],
        }
    )
    decision = CapabilityService().check(requested, manifest)
    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    assert decision.issues[0].path == "physics.equations[1]"
    assert "physics.models[0]" in {issue.path for issue in decision.issues}


def test_same_composition_can_target_two_manifests(
    valid_spec: ExperimentSpec,
    devsim_manifest: CapabilityManifest,
    sentaurus_manifest: CapabilityManifest,
) -> None:
    service = CapabilityService()
    assert service.check(valid_spec, devsim_manifest).status is CapabilityStatus.SUPPORTED
    assert service.check(valid_spec, sentaurus_manifest).status is CapabilityStatus.SUPPORTED


def test_backend_manifest_reports_execution_configuration(
    sentaurus_manifest: CapabilityManifest,
) -> None:
    assert sentaurus_manifest.execution_state == "unconfigured"


def test_backend_resource_budget_allows_more_than_ten_bias_points(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    study = DCStudy.model_validate(
        {"kind": "dc", "contact": "anode", "start": "0 V", "stop": "1 V", "step": "0.1 V"}
    )
    requested = valid_spec.model_copy(update={"study": study})

    decision = CapabilityService().check(requested, devsim_manifest)

    assert decision.status is CapabilityStatus.SUPPORTED


def test_backend_limits_reject_too_many_regions(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    regions = tuple(
        Region1D.model_validate(
            {
                "id": f"r{index}",
                "material": "silicon",
                "x0": f"{index} nm",
                "x1": f"{index + 1} nm",
            }
        )
        for index in range(33)
    )
    requested = valid_spec.model_copy(update={"regions": regions, "profiles": ()})

    decision = CapabilityService().check(requested, devsim_manifest)

    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    assert "regions" in {issue.path for issue in decision.issues}


def test_dopant_profile_on_dielectric_is_refused_before_compilation(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    regions = (
        valid_spec.regions[0].model_copy(
            update={"material": "generic_dielectric", "relative_permittivity": 7.5}
        ),
        *valid_spec.regions[1:],
    )
    requested = valid_spec.model_copy(update={"regions": regions})

    decision = CapabilityService().check(requested, devsim_manifest)

    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    issue = next(item for item in decision.issues if item.code == "incompatible_profile_material")
    assert issue.path == "profiles[0].region"
    assert issue.requested == "generic_dielectric"


def test_ohmic_contact_on_dielectric_is_refused_before_compilation(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    regions = (
        valid_spec.regions[0].model_copy(
            update={"material": "generic_dielectric", "relative_permittivity": 7.5}
        ),
        *valid_spec.regions[1:],
    )
    requested = valid_spec.model_copy(update={"regions": regions})

    decision = CapabilityService().check(requested, devsim_manifest)

    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    issue = next(item for item in decision.issues if item.code == "incompatible_contact_material")
    assert issue.path == "contacts[0]"
    assert issue.requested == "ohmic:generic_dielectric"


def test_gate_contact_on_semiconductor_is_refused_before_compilation(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    contact = Contact.model_validate({"id": "anode", "location": "x_min", "kind": "ideal_gate"})
    requested = valid_spec.model_copy(update={"contacts": (contact, *valid_spec.contacts[1:])})

    decision = CapabilityService().check(requested, devsim_manifest)

    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    issue = next(item for item in decision.issues if item.code == "incompatible_contact_material")
    assert issue.requested == "ideal_gate:silicon"


def test_recombination_model_dependencies_are_refused_before_runtime(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    physics = valid_spec.physics.model_copy(
        update={"equations": (valid_spec.physics.equations[0],), "models": ("auger",)}
    )
    requested = valid_spec.model_copy(update={"physics": physics})

    decision = CapabilityService().check(requested, devsim_manifest)

    assert decision.status is CapabilityStatus.BACKEND_UNSUPPORTED
    issue = next(item for item in decision.issues if item.code == "missing_model_dependency")
    assert issue.requested == "auger"
    assert set(issue.supported) == {"electron_continuity", "hole_continuity"}


def test_mixed_carrier_statistics_are_refused_before_runtime(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    physics = valid_spec.physics.model_copy(
        update={"models": (*valid_spec.physics.models, "fermi")}
    )
    requested = valid_spec.model_copy(update={"physics": physics})

    decision = CapabilityService().check(requested, devsim_manifest)

    issue = next(item for item in decision.issues if item.code == "incompatible_models")
    assert issue.message == "select exactly one carrier-statistics model"
    assert set(issue.supported) == {"boltzmann", "fermi"}


def test_fermi_statistics_requires_coupled_carrier_transport(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    physics = valid_spec.physics.model_copy(
        update={"equations": (valid_spec.physics.equations[0],), "models": ("fermi",)}
    )
    requested = valid_spec.model_copy(update={"physics": physics})

    decision = CapabilityService().check(requested, devsim_manifest)

    issue = next(
        item
        for item in decision.issues
        if item.code == "missing_model_dependency" and item.requested == "fermi"
    )
    assert set(issue.supported) == {"electron_continuity", "hole_continuity"}


def test_schottky_contact_requires_coupled_carrier_transport(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    contact = Contact.model_validate(
        {
            "id": valid_spec.contacts[0].id,
            "location": "x_min",
            "kind": "metal_work_function",
            "work_function": "4.10 eV",
        }
    )
    physics = valid_spec.physics.model_copy(
        update={"equations": (valid_spec.physics.equations[0],), "models": ()}
    )
    requested = valid_spec.model_copy(
        update={"contacts": (contact, *valid_spec.contacts[1:]), "physics": physics}
    )

    decision = CapabilityService().check(requested, devsim_manifest)

    issue = next(item for item in decision.issues if item.code == "missing_contact_dependency")
    assert set(issue.supported) == {"electron_continuity", "hole_continuity"}


def test_schottky_contact_supports_statistics_consistent_fermi_injection(
    valid_spec: ExperimentSpec, devsim_manifest: CapabilityManifest
) -> None:
    contact = Contact.model_validate(
        {
            "id": valid_spec.contacts[0].id,
            "location": "x_min",
            "kind": "metal_work_function",
            "work_function": "4.10 eV",
        }
    )
    models = tuple(
        "fermi" if model == "boltzmann" else model for model in valid_spec.physics.models
    )
    requested = valid_spec.model_copy(
        update={
            "contacts": (contact, *valid_spec.contacts[1:]),
            "physics": valid_spec.physics.model_copy(update={"models": models}),
        }
    )

    decision = CapabilityService().check(requested, devsim_manifest)

    assert decision.status is CapabilityStatus.SUPPORTED
    assert not decision.issues


def test_fermi_schottky_dynamic_combo_requires_its_own_reference_benchmark(
    valid_spec, devsim_manifest
):
    from tcad_agent.domain.studies import ACStudy

    requested = valid_spec.model_copy(
        update={
            "contacts": (
                Contact.model_validate(
                    {
                        "id": "anode",
                        "location": "x_min",
                        "kind": "metal_work_function",
                        "work_function": "4.1 eV",
                    }
                ),
                valid_spec.contacts[1],
            ),
            "physics": valid_spec.physics.model_copy(
                update={
                    "models": tuple(
                        "fermi" if str(m) == "boltzmann" else m for m in valid_spec.physics.models
                    )
                }
            ),
            "study": ACStudy.model_validate(
                {"kind": "ac", "contact": "anode", "frequency": "1e3 Hz", "amplitude": "0.01 V"}
            ),
        }
    )
    decision = CapabilityService().check(requested, devsim_manifest)
    assert any(issue.code == "unbenchmarked_contact_statistics_study" for issue in decision.issues)
    # A DEVSIM implementation gate is not a universal physics restriction.
    other_manifest = devsim_manifest.model_copy(update={"backend": "sentaurus"})
    other = CapabilityService().check(requested, other_manifest)
    assert not any(issue.code == "unbenchmarked_contact_statistics_study" for issue in other.issues)
