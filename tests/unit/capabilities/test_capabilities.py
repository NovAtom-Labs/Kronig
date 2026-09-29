from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.models import Contact, DCStudy, ExperimentSpec, Region1D


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
    contact = Contact.model_validate(
        {"id": "anode", "location": "x_min", "kind": "ideal_gate"}
    )
    requested = valid_spec.model_copy(
        update={"contacts": (contact, *valid_spec.contacts[1:])}
    )

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


def test_schottky_contact_refuses_unbenchmarked_fermi_injection(
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
        "fermi" if model == "boltzmann" else model
        for model in valid_spec.physics.models
    )
    requested = valid_spec.model_copy(
        update={
            "contacts": (contact, *valid_spec.contacts[1:]),
            "physics": valid_spec.physics.model_copy(update={"models": models}),
        }
    )

    decision = CapabilityService().check(requested, devsim_manifest)

    issue = next(item for item in decision.issues if item.code == "incompatible_contact_model")
    assert issue.supported == ("boltzmann",)
