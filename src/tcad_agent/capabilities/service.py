"""Data-driven comparison of experiment requests and backend support."""

from tcad_agent.capabilities.models import (
    CapabilityDecision,
    CapabilityIssue,
    CapabilityManifest,
    CapabilityStatus,
)
from tcad_agent.domain.models import DCStudy, ExperimentSpec
from tcad_agent.domain.studies import (
    DCPointsStudy,
    FrequencyStudy,
    ParameterStudy,
    TemperatureStudy,
)
from tcad_agent.physics.parameters import REGISTERED_PARAMETERS
from tcad_agent.physics.registry import PhysicsRegistry


class CapabilityService:
    """Checks requested features without interpreting device names."""

    def check(
        self, spec: ExperimentSpec, manifest: CapabilityManifest
    ) -> CapabilityDecision:
        issues: list[CapabilityIssue] = []
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
                    message=(
                        "Klaassen mobility requires coupled electron and hole continuity"
                    ),
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
            "fixed_charge"
            if interface.fixed_charge_density is not None
            else "continuity"
            for interface in spec.interfaces
        )
        self._check_many(
            issues,
            "interfaces",
            requested_interfaces,
            manifest.interfaces,
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
                if "fermi" in spec.physics.models:
                    issues.append(
                        CapabilityIssue(
                            path=f"contacts[{index}]",
                            code="incompatible_contact_model",
                            message=(
                                "Schottky transport is currently benchmarked with "
                                "Boltzmann carrier statistics"
                            ),
                            requested="metal_work_function:fermi",
                            supported=("boltzmann",),
                        )
                    )
        self._check_one(issues, "study.kind", spec.study.kind, manifest.studies)
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
                        message=(
                            f"parameter sweep requires model {parameter.required_model}"
                        ),
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
        self._check_limit(
            issues,
            "regions",
            len(spec.regions),
            manifest.limits.get("max_regions"),
        )
        bias_points = 1
        if isinstance(spec.study, DCStudy):
            bias_points = round(
                (spec.study.stop.to("V") - spec.study.start.to("V"))
                / spec.study.step.to("V")
            ) + 1
        elif isinstance(spec.study, (DCPointsStudy, TemperatureStudy, ParameterStudy)):
            bias_points = len(spec.study.values)
        elif isinstance(spec.study, FrequencyStudy):
            bias_points = spec.study.points
        self._check_limit(
            issues,
            "study.bias_points",
            bias_points,
            manifest.limits.get("max_bias_points"),
        )
        status = (
            CapabilityStatus.BACKEND_UNSUPPORTED if issues else CapabilityStatus.SUPPORTED
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
