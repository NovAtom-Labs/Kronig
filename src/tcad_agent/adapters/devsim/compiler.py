"""Deterministic compiler and normalizer for the DEVSIM backend."""

from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from pathlib import Path
from typing import cast

from tcad_agent.adapters.devsim import runtime
from tcad_agent.adapters.devsim.extract import normalize_native_field
from tcad_agent.adapters.devsim.models.materials import (
    SILICON_PARAMETER_SET_ID,
    SILICON_PARAMETER_SOURCES,
    SILICON_PARAMETERS,
)
from tcad_agent.adapters.devsim.payload import DevsimPayload
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.profiles import (
    ConstantProfile,
    ConstantTemperatureProfile,
    ErrorFunctionProfile,
    FixedChargeProfile,
    GaussianProfile,
    LinearProfile,
    LinearTemperatureProfile,
    PiecewiseConstantProfile,
    PiecewiseConstantTemperatureProfile,
    TabulatedProfile,
    TabulatedTemperatureProfile,
)
from tcad_agent.domain.studies import (
    ACStudy,
    DCPointsStudy,
    DCStudy,
    EquilibriumStudy,
    FrequencyStudy,
    ParameterStudy,
    TemperatureStudy,
    TransientStudy,
    expand_study_points,
)
from tcad_agent.physics.parameters import REGISTERED_PARAMETERS
from tcad_agent.results.datasets import AxisKind, Dataset, DatasetCentering, ScientificAxis
from tcad_agent.results.models import BiasPoint, CanonicalResult, FieldSeries, OperatingPoint
from tcad_agent.runners.models import CompiledJob, NativeRunResult


class DevsimAdapter:
    compiler_version = "0.2.0"

    def __init__(self, manifest: CapabilityManifest) -> None:
        self._manifest = manifest

    @property
    def manifest(self) -> CapabilityManifest:
        return self._manifest

    @classmethod
    def from_defaults(cls) -> DevsimAdapter:
        return cls(CapabilityManifest.from_backend("devsim"))

    def compile(self, spec: ExperimentSpec, workspace: Path) -> CompiledJob:
        decision = CapabilityService().check(spec, self.manifest)
        if decision.status is not CapabilityStatus.SUPPORTED:
            details = "; ".join(f"{issue.path}: {issue.message}" for issue in decision.issues)
            raise CapabilityError(details)
        payload = self._payload(spec)
        workspace = workspace.resolve()
        input_bytes = (payload.model_dump_json(indent=2) + "\n").encode()
        runtime_path = Path(runtime.__file__)
        runtime_bytes = runtime_path.read_bytes()
        workspace.mkdir(parents=True, exist_ok=False)
        input_path = workspace / "input.json"
        entrypoint = workspace / "run_devsim.py"
        input_path.write_bytes(input_bytes)
        entrypoint.write_bytes(runtime_bytes)
        return CompiledJob(
            backend="devsim",
            entrypoint=entrypoint,
            arguments=(str(input_path.name),),
            environment={},
            input_files=(input_path, entrypoint),
            input_digest=hashlib.sha256(input_bytes).hexdigest(),
            runtime_digest=hashlib.sha256(runtime_bytes).hexdigest(),
            compiler_version=self.compiler_version,
        )

    def _payload(self, spec: ExperimentSpec) -> DevsimPayload:
        regions: list[dict[str, object]] = [
            {
                "id": region.id,
                "material": region.material,
                "x0_cm": region.x0.to("cm"),
                "x1_cm": region.x1.to("cm"),
                "mesh_spacing_cm": (
                    region.mesh_spacing.to("cm")
                    if region.mesh_spacing is not None
                    else max((region.x1.to("cm") - region.x0.to("cm")) / 50.0, 1e-9)
                ),
                "relative_permittivity": region.relative_permittivity,
                "minimum_mesh_spacing_cm": (
                    region.minimum_mesh_spacing.to("cm")
                    if region.minimum_mesh_spacing is not None
                    else None
                ),
                "maximum_mesh_spacing_cm": (
                    region.maximum_mesh_spacing.to("cm")
                    if region.maximum_mesh_spacing is not None
                    else None
                ),
            }
            for region in spec.regions
        ]
        interfaces = [
            {
                "id": interface.id,
                "left_region": interface.left_region,
                "right_region": interface.right_region,
                "fixed_charge_cm2": (
                    interface.fixed_charge_density.to("cm^-2")
                    if interface.fixed_charge_density is not None
                    else None
                ),
                "mesh_spacing_cm": (
                    interface.mesh_spacing.to("cm")
                    if interface.mesh_spacing is not None
                    else None
                ),
                "surface_electron_velocity_cm_s": (
                    interface.surface_electron_velocity.to("cm/s")
                    if interface.surface_electron_velocity is not None
                    else None
                ),
                "surface_hole_velocity_cm_s": (
                    interface.surface_hole_velocity.to("cm/s")
                    if interface.surface_hole_velocity is not None
                    else None
                ),
                "trap_density_cm2": (
                    interface.trap_density.to("cm^-2")
                    if interface.trap_density is not None
                    else None
                ),
                "trap_energy_ev": (
                    interface.trap_energy.to("eV")
                    if interface.trap_energy is not None
                    else None
                ),
                "trap_type": interface.trap_type,
            }
            for interface in spec.interfaces
        ]
        profiles: list[dict[str, object]] = []
        for profile in spec.profiles:
            common: dict[str, object] = {
                "kind": profile.kind,
                "region": profile.region,
            }
            if isinstance(profile, FixedChargeProfile):
                common["density_c_cm3"] = profile.density.to("C/cm^3")
            else:
                common["species"] = str(profile.species)
            if isinstance(profile, ConstantProfile):
                common["value_cm3"] = profile.value.to("cm^-3")
            elif isinstance(profile, LinearProfile):
                common["start_value_cm3"] = profile.start_value.to("cm^-3")
                common["end_value_cm3"] = profile.end_value.to("cm^-3")
            elif isinstance(profile, GaussianProfile):
                common["peak_cm3"] = profile.peak.to("cm^-3")
                common["center_cm"] = profile.center.to("cm")
                common["standard_deviation_cm"] = profile.standard_deviation.to("cm")
            elif isinstance(profile, ErrorFunctionProfile):
                common["surface_value_cm3"] = profile.surface_value.to("cm^-3")
                common["junction_position_cm"] = profile.junction_position.to("cm")
                common["characteristic_length_cm"] = profile.characteristic_length.to("cm")
                common["orientation"] = profile.orientation
            elif isinstance(profile, TabulatedProfile):
                common["positions_cm"] = tuple(value.to("cm") for value in profile.positions)
                common["values_cm3"] = tuple(value.to("cm^-3") for value in profile.values)
                common["interpolation"] = profile.interpolation
            elif isinstance(profile, PiecewiseConstantProfile):
                common["boundaries_cm"] = tuple(
                    value.to("cm") for value in profile.boundaries
                )
                common["values_cm3"] = tuple(
                    value.to("cm^-3") for value in profile.values
                )
            profiles.append(common)
        contacts = [
            {
                "id": contact.id,
                "backend_id": f"contact_{index}",
                "location": str(contact.location),
                "kind": str(contact.kind),
                "work_function_ev": (
                    contact.work_function.to("eV") if contact.work_function is not None else None
                ),
                "electron_richardson_a_cm2_k2": (
                    contact.electron_richardson_constant.to("A/cm^2/K^2")
                    if contact.electron_richardson_constant is not None
                    else (
                        112.0
                        if str(contact.kind) == "metal_work_function"
                        else None
                    )
                ),
                "hole_richardson_a_cm2_k2": (
                    contact.hole_richardson_constant.to("A/cm^2/K^2")
                    if contact.hole_richardson_constant is not None
                    else (
                        32.0
                        if str(contact.kind) == "metal_work_function"
                        else None
                    )
                ),
                "voltage_offset_v": contact.voltage_offset.to("V"),
                "area_m2": (
                    contact.area.to("m^2") if contact.area is not None else None
                ),
            }
            for index, contact in enumerate(spec.contacts)
        ]
        study = self._study_payload(spec)
        parameters = spec.physics.parameters
        material_parameters = dict(SILICON_PARAMETERS)
        overrides = {
            "electron_lifetime_s": (
                parameters.electron_lifetime.to("s")
                if parameters.electron_lifetime is not None
                else None
            ),
            "hole_lifetime_s": (
                parameters.hole_lifetime.to("s")
                if parameters.hole_lifetime is not None
                else None
            ),
            "auger_electron_cm6_s": (
                parameters.auger_electron_coefficient.to("cm^6/s")
                if parameters.auger_electron_coefficient is not None
                else None
            ),
            "auger_hole_cm6_s": (
                parameters.auger_hole_coefficient.to("cm^6/s")
                if parameters.auger_hole_coefficient is not None
                else None
            ),
            "bgn_reference_energy_ev": (
                parameters.bgn_reference_energy.to("eV")
                if parameters.bgn_reference_energy is not None
                else None
            ),
            "bgn_reference_density_cm3": (
                parameters.bgn_reference_density.to("cm^-3")
                if parameters.bgn_reference_density is not None
                else None
            ),
        }
        material_parameters.update(
            {key: value for key, value in overrides.items() if value is not None}
        )
        parameter_sources = dict(SILICON_PARAMETER_SOURCES)
        if "fermi" in spec.physics.models:
            parameter_sources["carrier_statistics"] = {
                "source": (
                    "DEVSIM 2.9.1 Fermi/InvFermi primitives and Agent Kronig "
                    "reviewed quasi-Fermi-gradient discretization"
                ),
                "version": "devsim-43b41ca+novatom.fermi-gradient.2026-09-29.v1",
            }
        if any(
            str(contact.kind) == "metal_work_function"
            and spec.regions[0 if str(contact.location) == "x_min" else -1].material
            == "silicon"
            for contact in spec.contacts
        ):
            parameter_sources["schottky_transport"] = {
                "source": (
                    "Agent Kronig reviewed thermionic-emission boundary with "
                    "metal-work-function barrier"
                ),
                "version": "novatom.schottky-thermionic.2026-09-29.v1",
            }
        if any(
            interface.surface_electron_velocity is not None
            or interface.trap_density is not None
            for interface in spec.interfaces
        ):
            parameter_sources["surface_physics"] = {
                "source": (
                    "Agent Kronig reviewed surface-SRH and single-level "
                    "interface-trap equations"
                ),
                "version": "novatom.surface-physics.2026-09-29.v1",
            }
        if spec.physics.temperature_profiles:
            parameter_sources["prescribed_spatial_temperature"] = {
                "source": (
                    "Agent Kronig reviewed local-temperature silicon "
                    "drift-diffusion formulation"
                ),
                "version": "novatom.spatial-temperature.2026-09-29.v1",
            }
        mesh_anchors = self._mesh_anchor_payloads(spec, regions)
        temperature_profiles: list[dict[str, object]] = []
        for temperature_profile in spec.physics.temperature_profiles:
            compiled: dict[str, object] = {
                "kind": temperature_profile.kind,
                "region": temperature_profile.region,
            }
            if isinstance(temperature_profile, LinearTemperatureProfile):
                compiled.update(
                    start_k=temperature_profile.start_value.to("K"),
                    end_k=temperature_profile.end_value.to("K"),
                )
            elif isinstance(
                temperature_profile, PiecewiseConstantTemperatureProfile
            ):
                compiled.update(
                    boundaries_cm=tuple(
                        value.to("cm") for value in temperature_profile.boundaries
                    ),
                    values_k=tuple(
                        value.to("K") for value in temperature_profile.values
                    ),
                )
            elif isinstance(temperature_profile, TabulatedTemperatureProfile):
                compiled.update(
                    positions_cm=tuple(
                        value.to("cm") for value in temperature_profile.positions
                    ),
                    values_k=tuple(
                        value.to("K") for value in temperature_profile.values
                    ),
                )
            elif isinstance(temperature_profile, ConstantTemperatureProfile):
                compiled["value_k"] = temperature_profile.value.to("K")
            temperature_profiles.append(compiled)
        return DevsimPayload.model_validate(
            {
                "schema_version": "2.0",
                "experiment_name": spec.name,
                "regions": regions,
                "interfaces": interfaces,
                "mesh_anchors": mesh_anchors,
                "profiles": profiles,
                "contacts": contacts,
                "physics": {
                    "equations": [str(value) for value in spec.physics.equations],
                    "models": list(spec.physics.models),
                    "temperature_k": spec.physics.temperature.to("K"),
                    "temperature_profiles": temperature_profiles,
                    "parameter_set_id": SILICON_PARAMETER_SET_ID,
                    "parameter_sources": parameter_sources,
                    **material_parameters,
                },
                "sign_convention": spec.sign_convention.model_dump(mode="json"),
                "solver": spec.solver.model_dump(mode="json"),
                "study": study,
                "observables": [str(value) for value in spec.observables],
            }
        )

    @staticmethod
    def _mesh_anchor_payloads(
        spec: ExperimentSpec,
        regions: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Merge explicit anchors with profile landmarks using bounded spacing.

        Landmark discovery depends only on typed profile geometry. It does not infer
        a device type or alter the approved physical profile.
        """

        compiled_regions = {str(region["id"]): region for region in regions}
        anchors: dict[float, dict[str, object]] = {}

        def add(position_cm: float, spacing_cm: float, source: str) -> None:
            existing = anchors.get(position_cm)
            if existing is None or spacing_cm < cast(float, existing["spacing_cm"]):
                anchors[position_cm] = {
                    "position_cm": position_cm,
                    "spacing_cm": spacing_cm,
                    "source": source,
                }

        for anchor in spec.mesh_anchors:
            add(anchor.position.to("cm"), anchor.spacing.to("cm"), "user")

        def bounded_spacing(region: dict[str, object], candidate: float) -> float:
            target = min(candidate, cast(float, region["mesh_spacing_cm"]))
            minimum = region.get("minimum_mesh_spacing_cm")
            maximum = region.get("maximum_mesh_spacing_cm")
            if minimum is not None:
                target = max(target, cast(float, minimum))
            if maximum is not None:
                target = min(target, cast(float, maximum))
            return target

        for profile in spec.profiles:
            region = compiled_regions[profile.region]
            if isinstance(profile, GaussianProfile):
                add(
                    profile.center.to("cm"),
                    bounded_spacing(
                        region,
                        profile.standard_deviation.to("cm") / 4.0,
                    ),
                    "profile:gaussian:center",
                )
            elif isinstance(profile, ErrorFunctionProfile):
                add(
                    profile.junction_position.to("cm"),
                    bounded_spacing(
                        region,
                        profile.characteristic_length.to("cm") / 4.0,
                    ),
                    "profile:error_function:junction",
                )
            elif isinstance(profile, PiecewiseConstantProfile):
                for boundary in profile.boundaries[1:-1]:
                    add(
                        boundary.to("cm"),
                        bounded_spacing(
                            region, cast(float, region["mesh_spacing_cm"])
                        ),
                        "profile:piecewise_constant:boundary",
                    )
            elif isinstance(profile, TabulatedProfile):
                coordinates = tuple(value.to("cm") for value in profile.positions)
                for index, position in enumerate(coordinates):
                    neighbors = []
                    if index:
                        neighbors.append(position - coordinates[index - 1])
                    if index + 1 < len(coordinates):
                        neighbors.append(coordinates[index + 1] - position)
                    add(
                        position,
                        bounded_spacing(region, min(neighbors) / 4.0),
                        "profile:tabulated:sample",
                    )
        for temperature_profile in spec.physics.temperature_profiles:
            region = compiled_regions[temperature_profile.region]
            if isinstance(
                temperature_profile, PiecewiseConstantTemperatureProfile
            ):
                for boundary in temperature_profile.boundaries[1:-1]:
                    add(
                        boundary.to("cm"),
                        bounded_spacing(
                            region, cast(float, region["mesh_spacing_cm"])
                        ),
                        "temperature:piecewise_constant:boundary",
                    )
            elif isinstance(temperature_profile, TabulatedTemperatureProfile):
                coordinates = tuple(
                    value.to("cm") for value in temperature_profile.positions
                )
                for index, position in enumerate(coordinates):
                    neighbors = []
                    if index:
                        neighbors.append(position - coordinates[index - 1])
                    if index + 1 < len(coordinates):
                        neighbors.append(coordinates[index + 1] - position)
                    add(
                        position,
                        bounded_spacing(region, min(neighbors) / 4.0),
                        "temperature:tabulated:sample",
                    )
        return [anchors[position] for position in sorted(anchors)]

    @staticmethod
    def _study_payload(spec: ExperimentSpec) -> dict[str, object]:
        study = spec.study
        if isinstance(study, EquilibriumStudy):
            return {"kind": "equilibrium"}
        if isinstance(study, DCStudy):
            return {
                "kind": "dc",
                "contact": study.contact,
                "biases_v": tuple(value.to("V") for value in expand_study_points(study)),
                "strategy": study.strategy,
                "minimum_step_v": (
                    study.minimum_step.to("V") if study.minimum_step is not None else None
                ),
                "maximum_retries": study.maximum_retries,
            }
        if isinstance(study, DCPointsStudy):
            return {
                "kind": "dc_points",
                "contact": study.contact,
                "biases_v": tuple(value.to("V") for value in study.values),
                "strategy": study.strategy,
                "minimum_step_v": (
                    study.minimum_step.to("V")
                    if study.minimum_step is not None
                    else None
                ),
                "maximum_retries": study.maximum_retries,
            }
        if isinstance(study, ACStudy):
            return {
                "kind": "ac",
                "contact": study.contact,
                "frequencies_hz": (study.frequency.to("Hz"),),
                "amplitude_v": study.amplitude.to("V"),
            }
        if isinstance(study, FrequencyStudy):
            return {
                "kind": "frequency",
                "contact": study.contact,
                "frequencies_hz": tuple(value.to("Hz") for value in expand_study_points(study)),
                "amplitude_v": study.amplitude.to("V"),
            }
        if isinstance(study, TransientStudy):
            return {
                "kind": "transient",
                "contact": study.contact,
                "waveform": study.waveform,
                "initial_voltage_v": study.initial_voltage.to("V"),
                "final_voltage_v": study.final_voltage.to("V"),
                "start_s": study.start.to("s"),
                "stop_s": study.stop.to("s"),
                "initial_step_s": study.initial_step.to("s"),
                "minimum_step_s": (
                    study.minimum_step.to("s")
                    if study.minimum_step is not None
                    else study.initial_step.to("s") / 16.0
                ),
                "maximum_step_s": study.maximum_step.to("s"),
                "maximum_steps": study.maximum_steps,
                "maximum_retries": study.maximum_retries,
                "pulse_delay_s": (
                    study.pulse_delay.to("s") if study.pulse_delay is not None else None
                ),
                "rise_time_s": (
                    study.rise_time.to("s") if study.rise_time is not None else None
                ),
                "pulse_width_s": (
                    study.pulse_width.to("s") if study.pulse_width is not None else None
                ),
                "fall_time_s": (
                    study.fall_time.to("s") if study.fall_time is not None else None
                ),
            }
        if isinstance(study, TemperatureStudy):
            return {
                "kind": "temperature",
                "parameter_path": "physics.temperature",
                "values_si": tuple(value.to("K") for value in study.values),
                "unit": "K",
            }
        if isinstance(study, ParameterStudy):
            parameter = REGISTERED_PARAMETERS[study.parameter_path]
            return {
                "kind": "parameter",
                "parameter_path": study.parameter_path,
                "values_si": tuple(value.to(parameter.unit) for value in study.values),
                "unit": parameter.unit,
            }
        raise TypeError(f"unsupported study: {type(study).__name__}")

    def normalize(self, native: NativeRunResult) -> CanonicalResult:
        if native.status != "completed" or native.result_path is None:
            return CanonicalResult(
                backend="devsim",
                status=native.status,
                native_result_path=native.result_path,
                error=native.error,
            )
        data = json.loads(native.result_path.read_text())
        points = tuple(
            BiasPoint(
                bias_v=point["bias_v"],
                converged=point["converged"],
                terminal_currents_a_per_m2={
                    name: value * 1e4 for name, value in point["currents_a_per_cm2"].items()
                },
                terminal_electron_currents_a_per_m2={
                    name: value * 1e4
                    for name, value in point.get(
                        "electron_currents_a_per_cm2", {}
                    ).items()
                },
                terminal_hole_currents_a_per_m2={
                    name: value * 1e4
                    for name, value in point.get(
                        "hole_currents_a_per_cm2", {}
                    ).items()
                },
            )
            for point in data["bias_points"]
        )
        fields: dict[str, FieldSeries] = {}
        axes: dict[str, ScientificAxis] = {}
        datasets: dict[str, Dataset] = {}
        for name, field in data["fields"].items():
            positions, values, unit = normalize_native_field(field)
            fields[name] = FieldSeries(
                positions_m=positions,
                values=values,
                unit=unit,
            )
            axis_id = f"position__{name}"
            axes[axis_id] = ScientificAxis(
                id=axis_id,
                kind=AxisKind.POSITION,
                label="Position",
                unit="m",
                values=positions,
            )
            datasets[name] = Dataset(
                id=name,
                label=name.replace("_", " ").title(),
                unit=unit,
                axes=(axis_id,),
                shape=(len(values),),
                centering=DatasetCentering(field.get("centering", "node")),
                values=values,
                metadata=(
                    {
                        "discretization": "continuum edge-centered diagnostic",
                        "reference_current": "native solved carrier current",
                    }
                    if name == "current_decomposition_residual"
                    else {}
                ),
            )
        study_axis = data.get("study_axis")
        if study_axis is None:
            operating_axis_id = "bias"
            operating_axis_kind = AxisKind.BIAS
            operating_axis_label = "Applied bias"
            operating_axis_unit = "V"
            raw_operating_points = data["bias_points"]
            coordinate_key = "bias_v"
            native_field_sweeps = data.get("field_sweeps", {})
        else:
            operating_axis_id = str(study_axis["id"])
            operating_axis_kind = AxisKind(str(study_axis["kind"]))
            operating_axis_label = str(study_axis["label"])
            operating_axis_unit = str(study_axis["unit"])
            raw_operating_points = data.get("study_points", [])
            coordinate_key = "coordinate"
            native_field_sweeps = data.get("study_field_sweeps", {})
        operating_points = tuple(
            OperatingPoint(
                index=index,
                state="converged" if point["converged"] else "failed",
                coordinates={operating_axis_id: float(point[coordinate_key])},
                terminal_currents_a_per_m2={
                    name: value * 1e4
                    for name, value in point["currents_a_per_cm2"].items()
                },
                terminal_electron_currents_a_per_m2={
                    name: value * 1e4
                    for name, value in point.get(
                        "electron_currents_a_per_cm2", {}
                    ).items()
                },
                terminal_hole_currents_a_per_m2={
                    name: value * 1e4
                    for name, value in point.get(
                        "hole_currents_a_per_cm2", {}
                    ).items()
                },
                terminal_charges_c_per_m2={
                    name: value * 1e4
                    for name, value in point.get("charges_c_per_cm2", {}).items()
                },
                attempts=point.get("attempts", 1),
                message=point.get("message"),
            )
            for index, point in enumerate(raw_operating_points)
        )
        contact_areas = {
            str(name): float(value)
            for name, value in data.get("contact_areas_m2", {}).items()
        }
        interface_charges = {
            str(name): float(value) * 1e4
            for name, value in data.get(
                "interface_charge_densities_c_per_cm2", {}
            ).items()
        }
        if (
            "interface_charge_density" in data.get("requested_observables", ())
            and interface_charges
        ):
            interface_ids = tuple(interface_charges)
            axes["interface_index"] = ScientificAxis(
                id="interface_index",
                kind=AxisKind.INDEX,
                label="Interface index",
                unit="1",
                values=tuple(float(index) for index in range(len(interface_ids))),
            )
            datasets["interface_charge_density"] = Dataset(
                id="interface_charge_density",
                label="Interface charge density",
                unit="C/m^2",
                axes=("interface_index",),
                shape=(len(interface_ids),),
                centering=DatasetCentering.INTERFACE,
                values=tuple(interface_charges[name] for name in interface_ids),
                source="native:configured-fixed-plus-interface-trap-charge",
                metadata={
                    "interface_ids": json.dumps(interface_ids, separators=(",", ":"))
                },
            )
        interface_surface_rates = {
            str(name): float(value) * 1e4
            for name, value in data.get(
                "interface_surface_recombination_cm2_s", {}
            ).items()
        }
        if (
            "surface_recombination_rate" in data.get("requested_observables", ())
            and interface_surface_rates
        ):
            interface_ids = tuple(interface_surface_rates)
            axes["surface_interface_index"] = ScientificAxis(
                id="surface_interface_index",
                kind=AxisKind.INDEX,
                label="Surface interface index",
                unit="1",
                values=tuple(float(index) for index in range(len(interface_ids))),
            )
            datasets["surface_recombination_rate"] = Dataset(
                id="surface_recombination_rate",
                label="Surface recombination rate",
                unit="m^-2/s",
                axes=("surface_interface_index",),
                shape=(len(interface_ids),),
                centering=DatasetCentering.INTERFACE,
                values=tuple(interface_surface_rates[name] for name in interface_ids),
                source="native:SurfaceRecombinationSheet",
                metadata={
                    "interface_ids": json.dumps(interface_ids, separators=(",", ":"))
                },
            )
        trap_occupancies = {
            str(name): float(value)
            for name, value in data.get("interface_trap_occupancies", {}).items()
        }
        if (
            "interface_trap_occupancy" in data.get("requested_observables", ())
            and trap_occupancies
        ):
            interface_ids = tuple(trap_occupancies)
            axes["trap_interface_index"] = ScientificAxis(
                id="trap_interface_index",
                kind=AxisKind.INDEX,
                label="Trap interface index",
                unit="1",
                values=tuple(float(index) for index in range(len(interface_ids))),
            )
            datasets["interface_trap_occupancy"] = Dataset(
                id="interface_trap_occupancy",
                label="Interface trap occupancy",
                unit="1",
                axes=("trap_interface_index",),
                shape=(len(interface_ids),),
                centering=DatasetCentering.INTERFACE,
                values=tuple(trap_occupancies[name] for name in interface_ids),
                source="native:InterfaceTrapOccupancy",
                metadata={
                    "interface_ids": json.dumps(interface_ids, separators=(",", ":"))
                },
            )
        if operating_points:
            coordinate_values = tuple(
                point.coordinates[operating_axis_id] for point in operating_points
            )
            axes[operating_axis_id] = ScientificAxis(
                id=operating_axis_id,
                kind=operating_axis_kind,
                label=operating_axis_label,
                unit=operating_axis_unit,
                values=coordinate_values,
            )
            for terminal in data["terminals"]:
                currents = tuple(
                    point.terminal_currents_a_per_m2.get(terminal, 0.0)
                    for point in operating_points
                )
                electron_currents = tuple(
                    point.terminal_electron_currents_a_per_m2.get(terminal, 0.0)
                    for point in operating_points
                )
                hole_currents = tuple(
                    point.terminal_hole_currents_a_per_m2.get(terminal, 0.0)
                    for point in operating_points
                )
                charges = tuple(
                    point.terminal_charges_c_per_m2.get(terminal, 0.0)
                    for point in operating_points
                )
                datasets[f"terminal_current__{terminal}"] = Dataset(
                    id=f"terminal_current__{terminal}",
                    label=f"Terminal current at {terminal}",
                    unit="A/m^2",
                    axes=(operating_axis_id,),
                    shape=(len(coordinate_values),),
                    centering=DatasetCentering.OPERATING_POINT,
                    values=currents,
                    validity=tuple(point.state == "converged" for point in operating_points),
                )
                datasets[f"terminal_electron_current__{terminal}"] = Dataset(
                    id=f"terminal_electron_current__{terminal}",
                    label=f"Terminal electron current at {terminal}",
                    unit="A/m^2",
                    axes=(operating_axis_id,),
                    shape=(len(coordinate_values),),
                    centering=DatasetCentering.OPERATING_POINT,
                    values=electron_currents,
                    validity=tuple(
                        point.state == "converged" for point in operating_points
                    ),
                )
                datasets[f"terminal_hole_current__{terminal}"] = Dataset(
                    id=f"terminal_hole_current__{terminal}",
                    label=f"Terminal hole current at {terminal}",
                    unit="A/m^2",
                    axes=(operating_axis_id,),
                    shape=(len(coordinate_values),),
                    centering=DatasetCentering.OPERATING_POINT,
                    values=hole_currents,
                    validity=tuple(
                        point.state == "converged" for point in operating_points
                    ),
                )
                datasets[f"terminal_charge__{terminal}"] = Dataset(
                    id=f"terminal_charge__{terminal}",
                    label=f"Terminal charge at {terminal}",
                    unit="C/m^2",
                    axes=(operating_axis_id,),
                    shape=(len(coordinate_values),),
                    centering=DatasetCentering.OPERATING_POINT,
                    values=charges,
                    validity=tuple(point.state == "converged" for point in operating_points),
                )
                area = contact_areas.get(terminal)
                if area is not None:
                    datasets[f"absolute_terminal_current__{terminal}"] = Dataset(
                        id=f"absolute_terminal_current__{terminal}",
                        label=f"Absolute terminal current at {terminal}",
                        unit="A",
                        axes=(operating_axis_id,),
                        shape=(len(coordinate_values),),
                        centering=DatasetCentering.OPERATING_POINT,
                        values=tuple(value * area for value in currents),
                    )
                    datasets[f"absolute_terminal_charge__{terminal}"] = Dataset(
                        id=f"absolute_terminal_charge__{terminal}",
                        label=f"Absolute terminal charge at {terminal}",
                        unit="C",
                        axes=(operating_axis_id,),
                        shape=(len(coordinate_values),),
                        centering=DatasetCentering.OPERATING_POINT,
                        values=tuple(value * area for value in charges),
                    )
                capacitance = (
                    self._finite_difference(coordinate_values, charges)
                    if operating_axis_id == "bias"
                    and all(point.state == "converged" for point in operating_points)
                    else None
                )
                if capacitance is not None:
                    datasets[f"capacitance__{terminal}"] = Dataset(
                        id=f"capacitance__{terminal}",
                        label=f"Quasi-static capacitance at {terminal}",
                        unit="F/m^2",
                        axes=(operating_axis_id,),
                        shape=(len(coordinate_values),),
                        centering=DatasetCentering.OPERATING_POINT,
                        values=capacitance,
                        source=f"derived:dQdV:terminal_charge__{terminal}",
                    )
                    if area is not None:
                        datasets[f"absolute_capacitance__{terminal}"] = Dataset(
                            id=f"absolute_capacitance__{terminal}",
                            label=f"Absolute quasi-static capacitance at {terminal}",
                            unit="F",
                            axes=(operating_axis_id,),
                            shape=(len(coordinate_values),),
                            centering=DatasetCentering.OPERATING_POINT,
                            values=tuple(value * area for value in capacitance),
                            source=f"derived:area:capacitance__{terminal}",
                        )
            if len(operating_points) > 1:
                for name, sweep in native_field_sweeps.items():
                    final_field = fields.get(name)
                    axis_id = f"position__{name}"
                    if final_field is None or axis_id not in axes:
                        continue
                    position_count = len(final_field.positions_m)
                    native_values = tuple(float(value) for value in sweep["values"])
                    expected = len(operating_points) * position_count
                    if len(native_values) != expected:
                        raise ValueError(
                            f"native field sweep shape does not match operating points: {name}"
                        )
                    normalized_values: list[float] = []
                    for index in range(len(operating_points)):
                        start = index * position_count
                        stop = start + position_count
                        _positions, values, unit = normalize_native_field(
                            {
                                "positions_cm": sweep["positions_cm"],
                                "values": native_values[start:stop],
                                "unit": sweep["unit"],
                            }
                        )
                        normalized_values.extend(values)
                    datasets[name] = Dataset(
                        id=name,
                        label=name.replace("_", " ").title(),
                        unit=unit,
                        axes=(operating_axis_id, axis_id),
                        shape=(len(operating_points), position_count),
                        centering=DatasetCentering(sweep.get("centering", "node")),
                        values=tuple(normalized_values),
                        validity=tuple(bool(value) for value in sweep["validity"]),
                    )
        frequency_points = data.get("frequency_points", [])
        if frequency_points:
            frequencies = tuple(
                float(point["frequency_hz"]) for point in frequency_points
            )
            axes["frequency"] = ScientificAxis(
                id="frequency",
                kind=AxisKind.FREQUENCY,
                label="Frequency",
                unit="Hz",
                values=frequencies,
            )
            driven_contact = str(data["ac_contact"])
            real = tuple(
                float(point["admittance_real_s_per_cm2"]) * 1e4
                for point in frequency_points
            )
            imaginary = tuple(
                float(point["admittance_imag_s_per_cm2"]) * 1e4
                for point in frequency_points
            )
            current_real = tuple(
                float(point["current_real_a_per_cm2"]) * 1e4
                for point in frequency_points
            )
            current_imaginary = tuple(
                float(point["current_imag_a_per_cm2"]) * 1e4
                for point in frequency_points
            )
            conductance = tuple(
                float(point["conductance_s_per_cm2"]) * 1e4
                for point in frequency_points
            )
            capacitance = tuple(
                float(point["capacitance_f_per_cm2"]) * 1e4
                for point in frequency_points
            )
            datasets[f"complex_admittance__{driven_contact}"] = Dataset(
                id=f"complex_admittance__{driven_contact}",
                label=f"Complex admittance at {driven_contact}",
                unit="S/m^2",
                axes=("frequency",),
                shape=(len(frequencies),),
                centering=DatasetCentering.CONTACT,
                values=real,
                imaginary_values=imaginary,
                source="simulator:small-signal-ac",
            )
            datasets[f"complex_current_response__{driven_contact}"] = Dataset(
                id=f"complex_current_response__{driven_contact}",
                label=f"Complex current response at {driven_contact}",
                unit="A/m^2",
                axes=("frequency",),
                shape=(len(frequencies),),
                centering=DatasetCentering.CONTACT,
                values=current_real,
                imaginary_values=current_imaginary,
                source="simulator:small-signal-ac-current",
            )
            datasets[f"ac_conductance__{driven_contact}"] = Dataset(
                id=f"ac_conductance__{driven_contact}",
                label=f"AC conductance at {driven_contact}",
                unit="S/m^2",
                axes=("frequency",),
                shape=(len(frequencies),),
                centering=DatasetCentering.CONTACT,
                values=conductance,
                source=f"derived:real:complex_admittance__{driven_contact}",
            )
            datasets[f"ac_capacitance__{driven_contact}"] = Dataset(
                id=f"ac_capacitance__{driven_contact}",
                label=f"Small-signal capacitance at {driven_contact}",
                unit="F/m^2",
                axes=("frequency",),
                shape=(len(frequencies),),
                centering=DatasetCentering.CONTACT,
                values=capacitance,
                source=(
                    "derived:imaginary_over_omega:"
                    f"complex_admittance__{driven_contact}"
                ),
                metadata={"dc_operating_point_v": "0.0"},
            )
            area = contact_areas.get(driven_contact)
            if area is not None:
                datasets[f"absolute_ac_capacitance__{driven_contact}"] = Dataset(
                    id=f"absolute_ac_capacitance__{driven_contact}",
                    label=f"Absolute small-signal capacitance at {driven_contact}",
                    unit="F",
                    axes=("frequency",),
                    shape=(len(frequencies),),
                    centering=DatasetCentering.CONTACT,
                    values=tuple(value * area for value in capacitance),
                    source=f"derived:area:ac_capacitance__{driven_contact}",
                )
        return CanonicalResult(
            backend="devsim",
            simulator_version=data["simulator_version"],
            status="completed",
            terminals=tuple(data["terminals"]),
            bias_points=points,
            fields=fields,
            axes=axes,
            datasets=datasets,
            operating_points=operating_points,
            native_result_path=native.result_path,
            sign_convention={
                str(key): str(value)
                for key, value in data.get("sign_convention", {}).items()
            },
            metadata={
                "parameter_set_id": data.get("parameter_set_id", "unknown"),
                "parameter_sources": data.get("parameter_sources", {}),
                "solver_configuration": data.get("solver_configuration", {}),
                "solver_events": data.get("solver_events", []),
                "native_model_names": data.get("native_model_names", {}),
                "regions": data.get("regions", []),
                "interfaces": data.get("interfaces", []),
            },
        )

    @staticmethod
    def _finite_difference(
        coordinates: tuple[float, ...], values: tuple[float, ...]
    ) -> tuple[float, ...] | None:
        deltas = tuple(right - left for left, right in pairwise(coordinates))
        if (
            len(coordinates) < 2
            or any(delta == 0 for delta in deltas)
            or not (all(delta > 0 for delta in deltas) or all(delta < 0 for delta in deltas))
        ):
            return None
        derivatives: list[float] = []
        for index in range(len(values)):
            if index == 0:
                left, right = 0, 1
            elif index == len(values) - 1:
                left, right = index - 1, index
            else:
                left, right = index - 1, index + 1
            derivatives.append(
                (values[right] - values[left])
                / (coordinates[right] - coordinates[left])
            )
        return tuple(derivatives)
