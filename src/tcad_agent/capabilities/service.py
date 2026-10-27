"""Data-driven comparison of experiment requests and backend support."""

from tcad_agent.capabilities.models import (
    CapabilityDecision,
    CapabilityIssue,
    CapabilityManifest,
    CapabilityStatus,
)
from tcad_agent.domain.models import DCStudy, ExperimentSpec
from tcad_agent.domain.studies import (
    ACStudy,
    DCPointsStudy,
    FrequencyStudy,
    ParameterStudy,
    TemperatureStudy,
    TransientStudy,
)
from tcad_agent.physics.parameters import REGISTERED_PARAMETERS
from tcad_agent.physics.registry import PhysicsRegistry

# Spatial quantities that need a line to be read along in a two-dimensional structure.
_PROFILE_OBSERVABLES = frozenset(
    {
        "potential",
        "electron_density",
        "hole_density",
        "charge_density",
        "net_doping",
        "conduction_band",
        "valence_band",
        "fermi_level",
        "electron_quasi_fermi_level",
        "hole_quasi_fermi_level",
        "electron_mobility",
        "hole_mobility",
        "recombination_rate",
        "srh_recombination_rate",
        "auger_recombination_rate",
        "donor_concentration",
        "acceptor_concentration",
        "band_gap",
        "band_gap_narrowing",
        "electron_affinity",
        "effective_intrinsic_carrier_concentration",
        "lattice_temperature",
        "electric_field",
        "electron_current_density",
        "hole_current_density",
        "total_current_density",
    }
)
_NEEDS_INPUT_CODES = frozenset(
    {
        "missing_contact_area",
        "missing_device_width",
        "missing_profile_cut",
        "observable_needs_model",
    }
)
# A native field exists only when the model that produces it is part of the physics.
_OBSERVABLE_MODELS = {
    "srh_recombination_rate": ("srh",),
    "auger_recombination_rate": ("auger",),
    "band_gap_narrowing": ("band_gap_narrowing", "slotboom_bgn"),
}


class CapabilityService:
    """Checks requested features without interpreting device names."""

    def check(self, spec: ExperimentSpec, manifest: CapabilityManifest) -> CapabilityDecision:
        issues: list[CapabilityIssue] = []
        if manifest.backend != "devsim" and spec.solver.precision != "backend_default":
            issues.append(
                CapabilityIssue(
                    path="solver.precision",
                    code="unsupported_numerical_precision",
                    requested=spec.solver.precision,
                    message="Explicit numerical precision has no reviewed mapping in this adapter.",
                    supported=("backend_default",),
                )
            )
        self._check_one(issues, "dimension", spec.dimension, manifest.dimensions)
        self._check_many(
            issues,
            "physics.equations",
            tuple(str(value) for value in spec.physics.equations),
            manifest.equations,
        )
        self._check_many(issues, "physics.models", spec.physics.models, manifest.models)
        selected_physics = {
            *(f"equation.{value}" for value in spec.physics.equations),
            *(f"model.{value}" for value in spec.physics.models),
        }
        registry = PhysicsRegistry.default()
        for model in spec.physics.models:
            try:
                descriptor = registry.require_reviewed(f"model.{model}")
            except KeyError:
                continue
            missing = tuple(
                requirement.split(".", 1)[1]
                for requirement in descriptor.requires
                if requirement not in selected_physics
            )
            if missing:
                issues.append(
                    CapabilityIssue(
                        path="physics.models",
                        code="missing_model_dependency",
                        message=f"{model} requires {', '.join(missing)}",
                        requested=model,
                        supported=missing,
                    )
                )
        mobility_models = {
            model
            for model in spec.physics.models
            if model in {"constant_mobility", "klaassen_mobility"}
        }
        if len(mobility_models) > 1:
            issues.append(
                CapabilityIssue(
                    path="physics.models",
                    code="incompatible_models",
                    message="select exactly one bulk mobility model",
                    requested=",".join(sorted(mobility_models)),
                    supported=("constant_mobility", "klaassen_mobility"),
                )
            )
        if "klaassen_mobility" in mobility_models and not {
            "electron_continuity",
            "hole_continuity",
        }.issubset({str(value) for value in spec.physics.equations}):
            issues.append(
                CapabilityIssue(
                    path="physics.models",
                    code="missing_model_dependency",
                    message=("Klaassen mobility requires coupled electron and hole continuity"),
                    requested="klaassen_mobility",
                    supported=("electron_continuity", "hole_continuity"),
                )
            )
        if "high_field_saturation" in spec.physics.models and not mobility_models:
            issues.append(
                CapabilityIssue(
                    path="physics.models",
                    code="missing_model_dependency",
                    message="high-field saturation requires one reviewed bulk mobility model",
                    requested="high_field_saturation",
                    supported=("constant_mobility", "klaassen_mobility"),
                )
            )
        statistics_models = {
            model for model in spec.physics.models if model in {"boltzmann", "fermi"}
        }
        if len(statistics_models) > 1:
            issues.append(
                CapabilityIssue(
                    path="physics.models",
                    code="incompatible_models",
                    message="select exactly one carrier-statistics model",
                    requested=",".join(sorted(statistics_models)),
                    supported=("boltzmann", "fermi"),
                )
            )
        if "fermi" in statistics_models and not {
            "electron_continuity",
            "hole_continuity",
        }.issubset({str(value) for value in spec.physics.equations}):
            issues.append(
                CapabilityIssue(
                    path="physics.models",
                    code="missing_model_dependency",
                    message="Fermi statistics requires coupled electron and hole continuity",
                    requested="fermi",
                    supported=("electron_continuity", "hole_continuity"),
                )
            )
        if spec.physics.temperature_profiles:
            incompatible_models = {
                "fermi",
                "klaassen_mobility",
                "high_field_saturation",
            }.intersection(spec.physics.models)
            silicon_schottky = any(
                str(contact.kind) == "metal_work_function"
                and spec.regions[0 if str(contact.location) == "x_min" else -1].material
                == "silicon"
                for contact in spec.contacts
            )
            dynamic_study = isinstance(
                spec.study, (ACStudy, FrequencyStudy, TransientStudy, TemperatureStudy)
            )
            if incompatible_models or silicon_schottky or dynamic_study:
                requested = sorted(incompatible_models)
                if silicon_schottky:
                    requested.append("schottky")
                if dynamic_study:
                    requested.append(spec.study.kind)
                issues.append(
                    CapabilityIssue(
                        path="physics.temperature_profiles",
                        code="incompatible_temperature_profile",
                        message=(
                            "prescribed spatial temperature is not benchmarked for "
                            "the selected models or study"
                        ),
                        requested=",".join(requested),
                        supported=(
                            "boltzmann",
                            "constant_mobility",
                            "equilibrium",
                            "dc",
                            "dc_points",
                        ),
                    )
                )
            regions_by_id = {region.id: region for region in spec.regions}
            for index, temperature_profile in enumerate(spec.physics.temperature_profiles):
                if regions_by_id[temperature_profile.region].material != "silicon":
                    issues.append(
                        CapabilityIssue(
                            path=f"physics.temperature_profiles[{index}]",
                            code="incompatible_temperature_material",
                            message=(
                                "prescribed spatial temperature is currently "
                                "benchmarked for silicon regions"
                            ),
                            requested=regions_by_id[temperature_profile.region].material,
                            supported=("silicon",),
                        )
                    )
        self._check_many(
            issues,
            "regions.material",
            tuple(region.material for region in spec.regions),
            manifest.materials,
        )
        self._check_many(
            issues,
            "profiles",
            tuple(profile.kind for profile in spec.profiles),
            manifest.profiles,
        )
        if manifest.backend == "devsim":
            regions_by_id = {region.id: region for region in spec.regions}
            for index, profile in enumerate(spec.profiles):
                adjacent = regions_by_id[profile.region]
                if profile.kind != "fixed_charge" and adjacent.material != "silicon":
                    issues.append(
                        CapabilityIssue(
                            path=f"profiles[{index}].region",
                            code="incompatible_profile_material",
                            message=(
                                "donor and acceptor concentration profiles require "
                                "a reviewed semiconductor material"
                            ),
                            requested=adjacent.material,
                            supported=("silicon",),
                        )
                    )
        requested_interfaces = tuple(
            capability
            for interface in spec.interfaces
            for capability in (
                "continuity",
                *(("fixed_charge",) if interface.fixed_charge_density is not None else ()),
                *(("surface_srh",) if interface.surface_electron_velocity is not None else ()),
                *(("interface_trap",) if interface.trap_density is not None else ()),
            )
        )
        self._check_many(
            issues,
            "interfaces",
            requested_interfaces,
            manifest.interfaces,
        )
        if manifest.backend == "devsim":
            region_material = {region.id: region.material for region in spec.regions}
            for index, interface in enumerate(spec.interfaces):
                if interface.surface_electron_velocity is None and interface.trap_density is None:
                    continue
                materials = {
                    region_material[interface.left_region],
                    region_material[interface.right_region],
                }
                reviewed_pairs = materials == {"silicon"} or (
                    "silicon" in materials
                    and bool(materials.intersection({"silicon_dioxide", "generic_dielectric"}))
                )
                if not reviewed_pairs:
                    issues.append(
                        CapabilityIssue(
                            path=f"interfaces[{index}]",
                            code="incompatible_interface_materials",
                            message=(
                                "surface physics requires one silicon side and one "
                                "reviewed dielectric side"
                            ),
                            requested=":".join(sorted(materials)),
                            supported=(
                                "silicon:silicon",
                                "silicon:silicon_dioxide",
                                "generic_dielectric:silicon",
                            ),
                        )
                    )
                equations = {str(value) for value in spec.physics.equations}
                if not {"electron_continuity", "hole_continuity"}.issubset(equations):
                    issues.append(
                        CapabilityIssue(
                            path=f"interfaces[{index}]",
                            code="missing_interface_dependency",
                            message="surface physics requires coupled carrier transport",
                            requested=interface.id,
                            supported=("electron_continuity", "hole_continuity"),
                        )
                    )
        self._check_many(
            issues,
            "contacts",
            tuple(str(contact.kind) for contact in spec.contacts),
            manifest.contacts,
        )
        for index, contact in enumerate(spec.contacts):
            if manifest.backend != "devsim":
                continue
            adjacent = spec.regions[0 if str(contact.location) == "x_min" else -1]
            kind = str(contact.kind)
            allowed_materials = {
                "ohmic": ("silicon",),
                "ideal_gate": ("silicon_dioxide", "generic_dielectric"),
                "metal_work_function": (
                    "silicon",
                    "silicon_dioxide",
                    "generic_dielectric",
                ),
                "insulating": (
                    "silicon",
                    "silicon_dioxide",
                    "generic_dielectric",
                ),
            }[kind]
            if adjacent.material not in allowed_materials:
                message = "contact kind is incompatible with its adjacent material"
                issues.append(
                    CapabilityIssue(
                        path=f"contacts[{index}]",
                        code="incompatible_contact_material",
                        message=message,
                        requested=f"{kind}:{adjacent.material}",
                        supported=allowed_materials,
                    )
                )
            if kind == "metal_work_function" and adjacent.material == "silicon":
                if "fermi" in statistics_models and isinstance(
                    spec.study, (ACStudy, FrequencyStudy, TransientStudy)
                ):
                    issues.append(
                        CapabilityIssue(
                            path="study.kind",
                            code="unbenchmarked_contact_statistics_study",
                            message=(
                                "Fermi thermionic silicon contacts are benchmarked for "
                                "equilibrium and DC, not AC, frequency or transient response"
                            ),
                            requested=f"fermi:metal_work_function:{spec.study.kind}",
                            supported=("equilibrium", "dc", "dc_points"),
                        )
                    )
                equations = {str(value) for value in spec.physics.equations}
                if not {"electron_continuity", "hole_continuity"}.issubset(equations):
                    issues.append(
                        CapabilityIssue(
                            path=f"contacts[{index}]",
                            code="missing_contact_dependency",
                            message=(
                                "semiconductor metal work-function contact requires "
                                "coupled carrier transport"
                            ),
                            requested="metal_work_function:silicon",
                            supported=("electron_continuity", "hole_continuity"),
                        )
                    )
        self._check_one(issues, "study.kind", spec.study.kind, manifest.studies)
        bias_schedule = getattr(spec.study, "bias_schedule", None)
        if bias_schedule is not None:
            self._check_one(
                issues, "study.bias_schedule.kind", bias_schedule.kind, manifest.studies
            )
            if manifest.backend != "devsim":
                issues.append(
                    CapabilityIssue(
                        path="study.bias_schedule",
                        code="unsupported",
                        requested="coupled bias and AC",
                        message="Coupled bias and AC execution is not reviewed for this adapter.",
                    )
                )
        study_contact = getattr(spec.study, "contact", None)
        if study_contact is not None:
            selected = next(contact for contact in spec.contacts if contact.id == study_contact)
            if str(selected.kind) == "insulating":
                issues.append(
                    CapabilityIssue(
                        path="study.contact",
                        code="invalid_driven_contact",
                        message="an insulating boundary cannot be driven by a study",
                        requested=study_contact,
                        supported=tuple(
                            contact.id
                            for contact in spec.contacts
                            if str(contact.kind) != "insulating"
                        ),
                    )
                )
        if isinstance(spec.study, ParameterStudy):
            parameter = REGISTERED_PARAMETERS.get(spec.study.parameter_path)
            if parameter is None:
                issues.append(
                    CapabilityIssue(
                        path="study.parameter_path",
                        code="unregistered_parameter",
                        message="parameter sweep target is not registered",
                        requested=spec.study.parameter_path,
                        supported=tuple(sorted(REGISTERED_PARAMETERS)),
                    )
                )
            elif (
                parameter.required_model is not None
                and parameter.required_model not in spec.physics.models
            ):
                issues.append(
                    CapabilityIssue(
                        path="study.parameter_path",
                        code="missing_parameter_model",
                        message=(f"parameter sweep requires model {parameter.required_model}"),
                        requested=spec.study.parameter_path,
                        supported=(parameter.required_model,),
                    )
                )
        self._check_many(
            issues,
            "observables",
            tuple(str(observable) for observable in spec.observables),
            manifest.observables,
        )
        if "fermi_level" in spec.observables:
            # Bias on a dielectric boundary is not a carrier electrochemical
            # drive. Compare only injecting contacts, including their offsets.
            # AC profile fields are DC operating-point fields; transient fields
            # and prescribed thermal gradients do not imply thermal equilibrium.
            injecting = {
                contact.id: contact.voltage_offset.to("V")
                for contact in spec.contacts
                if contact.kind in {"ohmic", "metal_work_function"}
                and spec.regions[0 if str(contact.location) == "x_min" else -1].material
                == "silicon"
            }
            schedule = spec.study
            if isinstance(schedule, ACStudy | FrequencyStudy):
                schedule = schedule.bias_schedule
            if isinstance(schedule, DCStudy):
                biases = (schedule.start.to("V"), schedule.stop.to("V"))
            elif isinstance(schedule, DCPointsStudy):
                biases = tuple(point.to("V") for point in schedule.values)
            else:
                biases = (0.0,)
            drive = getattr(spec.study, "contact", None)
            split_contacts = any(
                len(
                    {
                        offset + (bias if contact == drive else 0.0)
                        for contact, offset in injecting.items()
                    }
                )
                > 1
                for bias in biases
            )
            if (
                split_contacts
                or isinstance(spec.study, TransientStudy)
                or spec.physics.temperature_profiles
            ):
                issues.append(
                    CapabilityIssue(
                        path="observables",
                        code="single_fermi_level_outside_equilibrium",
                        requested="fermi_level",
                        message=(
                            "A single Fermi level is not defined for this nonequilibrium study. "
                            "Use separate electron and hole quasi-Fermi levels; their midpoint "
                            "is not a physical substitute. Preserve explicitly requested "
                            "analyses and ask the researcher if a change is required."
                        ),
                        supported=("electron_quasi_fermi_level", "hole_quasi_fermi_level"),
                    )
                )
        if manifest.backend == "sentaurus":
            for observable in spec.observables:
                needed = _OBSERVABLE_MODELS.get(str(observable))
                if needed and not set(needed) & set(spec.physics.models):
                    issues.append(
                        CapabilityIssue(
                            path="physics.models",
                            code="observable_needs_model",
                            message=(
                                f"{observable} only exists when the {' or '.join(needed)} model "
                                "is part of the physics; the model changes the whole "
                                "simulation, so it is added to the experiment for approval, "
                                "never switched on silently"
                            ),
                            requested=str(observable),
                            supported=(
                                *(f"add the {name} model" for name in needed),
                                "drop this output",
                            ),
                        )
                    )
        if spec.dimension == 2 and not spec.profile_cuts:
            spatial = sorted(
                str(observable)
                for observable in spec.observables
                if str(observable) in _PROFILE_OBSERVABLES
            )
            if spatial:
                issues.append(
                    CapabilityIssue(
                        path="profile_cuts",
                        code="missing_profile_cut",
                        message=(
                            "profiles in a two-dimensional structure are taken along a lateral "
                            "line, so the depth of at least one cut is required"
                        ),
                        requested=",".join(spatial),
                        supported=("provide cut depth",),
                    )
                )
        if any(str(observable) == "absolute_terminal_current" for observable in spec.observables):
            if spec.dimension == 2:
                # A two-dimensional device carries current per unit width, so the width turns
                # it into amperes; contact areas follow from the geometry.
                if spec.width is None:
                    issues.append(
                        CapabilityIssue(
                            path="width",
                            code="missing_device_width",
                            message=(
                                "absolute terminal current in a two-dimensional device "
                                "requires the device width"
                            ),
                            requested="width",
                            supported=("provide device width",),
                        )
                    )
            missing_area = tuple(
                contact.id
                for contact in spec.contacts
                if contact.area is None and spec.dimension == 1
            )
            if missing_area:
                issues.append(
                    CapabilityIssue(
                        path="contacts.area",
                        code="missing_contact_area",
                        message=(
                            "absolute terminal current requires a physical area for "
                            "every reported terminal"
                        ),
                        requested=",".join(missing_area),
                        supported=("provide contact area", "use terminal current density"),
                    )
                )
        decomposition_outputs = {
            "electron_drift_current_density",
            "electron_diffusion_current_density",
            "hole_drift_current_density",
            "hole_diffusion_current_density",
            "current_decomposition_residual",
        }
        if (
            manifest.backend == "devsim"
            and "fermi" in spec.physics.models
            and isinstance(spec.study, ACStudy | FrequencyStudy | TransientStudy)
            and decomposition_outputs.intersection(str(value) for value in spec.observables)
        ):
            issues.append(
                CapabilityIssue(
                    path="observables",
                    code="unbenchmarked_diagnostic_study",
                    message=(
                        "Fermi current decomposition is not benchmarked for this dynamic study; "
                        "the restriction applies to this adapter's diagnostic, not Fermi physics"
                    ),
                    requested=f"current_decomposition:fermi:{spec.study.kind}",
                    supported=("equilibrium", "dc", "dc_points", "temperature", "parameter"),
                )
            )
        self._check_limit(
            issues,
            "regions",
            len(spec.regions),
            manifest.limits.get("max_regions"),
        )
        bias_points = 1
        if isinstance(spec.study, DCStudy):
            bias_points = (
                round(
                    (spec.study.stop.to("V") - spec.study.start.to("V")) / spec.study.step.to("V")
                )
                + 1
            )
        elif isinstance(spec.study, (DCPointsStudy, TemperatureStudy, ParameterStudy)):
            bias_points = len(spec.study.values)
        elif isinstance(spec.study, FrequencyStudy):
            bias_points = spec.study.points
        if bias_schedule is not None:
            from tcad_agent.domain.studies import expand_study_points

            bias_points = len(expand_study_points(bias_schedule)) * (
                spec.study.points if isinstance(spec.study, FrequencyStudy) else 1
            )
        self._check_limit(
            issues,
            "study.bias_points",
            bias_points,
            manifest.limits.get("max_bias_points"),
        )
        status = CapabilityStatus.SUPPORTED
        if issues:
            status = (
                CapabilityStatus.NEEDS_INPUT
                if all(issue.code in _NEEDS_INPUT_CODES for issue in issues)
                else CapabilityStatus.BACKEND_UNSUPPORTED
            )
        return CapabilityDecision(status=status, backend=manifest.backend, issues=tuple(issues))

    @staticmethod
    def _check_one(
        issues: list[CapabilityIssue],
        path: str,
        requested: str | int,
        supported: tuple[str | int, ...],
    ) -> None:
        if requested not in supported:
            issues.append(
                CapabilityIssue(
                    path=path,
                    code="unsupported_capability",
                    message=f"{requested!r} is not supported by this backend",
                    requested=requested,
                    supported=supported,
                )
            )

    @classmethod
    def _check_many(
        cls,
        issues: list[CapabilityIssue],
        path: str,
        requested: tuple[str, ...],
        supported: tuple[str, ...],
    ) -> None:
        for index, value in enumerate(requested):
            cls._check_one(issues, f"{path}[{index}]", value, supported)

    @staticmethod
    def _check_limit(
        issues: list[CapabilityIssue],
        path: str,
        requested: int,
        maximum: int | float | None,
    ) -> None:
        if maximum is not None and requested > maximum:
            issues.append(
                CapabilityIssue(
                    path=path,
                    code="backend_limit_exceeded",
                    message=f"{requested} exceeds backend limit {maximum}",
                    requested=requested,
                    supported=(maximum,),
                )
            )
