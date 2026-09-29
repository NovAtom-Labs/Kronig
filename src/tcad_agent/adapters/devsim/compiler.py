"""Deterministic compiler and normalizer for the DEVSIM backend."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tcad_agent.adapters.devsim import runtime
from tcad_agent.adapters.devsim.extract import normalize_native_field
from tcad_agent.adapters.devsim.payload import DevsimPayload
from tcad_agent.capabilities.models import CapabilityManifest, CapabilityStatus
from tcad_agent.capabilities.service import CapabilityService
from tcad_agent.domain.errors import CapabilityError
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.domain.profiles import (
    ConstantProfile,
    ErrorFunctionProfile,
    GaussianProfile,
    LinearProfile,
    TabulatedProfile,
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
        regions = [
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
            }
            for interface in spec.interfaces
        ]
        profiles: list[dict[str, object]] = []
        for profile in spec.profiles:
            common: dict[str, object] = {
                "kind": profile.kind,
                "region": profile.region,
                "species": str(profile.species),
            }
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
            profiles.append(common)
        contacts = [
            {
                "id": contact.id,
                "location": str(contact.location),
                "kind": str(contact.kind),
                "work_function_ev": (
                    contact.work_function.to("eV") if contact.work_function is not None else None
                ),
            }
            for contact in spec.contacts
        ]
        study = self._study_payload(spec)
        return DevsimPayload.model_validate(
            {
                "schema_version": "2.0",
                "experiment_name": spec.name,
                "regions": regions,
                "interfaces": interfaces,
                "profiles": profiles,
                "contacts": contacts,
                "physics": {
                    "equations": [str(value) for value in spec.physics.equations],
                    "models": list(spec.physics.models),
                    "temperature_k": spec.physics.temperature.to("K"),
                },
                "study": study,
                "observables": [str(value) for value in spec.observables],
            }
        )

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
                "start_s": study.start.to("s"),
                "stop_s": study.stop.to("s"),
                "initial_step_s": study.initial_step.to("s"),
                "maximum_step_s": study.maximum_step.to("s"),
                "maximum_steps": study.maximum_steps,
            }
        if isinstance(study, TemperatureStudy):
            return {
                "kind": "temperature",
                "parameter_path": "physics.temperature",
                "values_si": tuple(value.to("K") for value in study.values),
                "unit": "K",
            }
        if isinstance(study, ParameterStudy):
            return {
                "kind": "parameter",
                "parameter_path": study.parameter_path,
                "values_si": tuple(value.magnitude_si for value in study.values),
                "unit": study.values[0].si_unit,
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
            )
        operating_points = tuple(
            OperatingPoint(
                index=index,
                state="converged" if point["converged"] else "failed",
                coordinates={"bias": point["bias_v"]},
                terminal_currents_a_per_m2={
                    name: value * 1e4 for name, value in point["currents_a_per_cm2"].items()
                },
                terminal_charges_c_per_m2={
                    name: value * 1e4 for name, value in point.get("charges_c_per_cm2", {}).items()
                },
                attempts=point.get("attempts", 1),
                message=point.get("message"),
            )
            for index, point in enumerate(data["bias_points"])
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
        )
