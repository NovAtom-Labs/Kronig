"""Typed metadata emitted for the licensed Sentaurus runner."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field

from tcad_agent.domain.models import StrictModel
from tcad_agent.runners.models import CompiledJob


class SourceLocation(StrictModel):
    file: str
    line: int = Field(ge=1)


class NativeOperatingPoint(StrictModel):
    index: int = Field(ge=0)
    bias_v: float
    contact: str
    profile_prefix: str


class NativeReview(StrictModel):
    simulator_version: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class SentaurusJobManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: Literal["sentaurus"] = "sentaurus"
    compiler_version: str
    command_file: Literal["sdevice.cmd"] = "sdevice.cmd"
    required_runtime_inputs: tuple[Literal["device.tdr"], ...] = ("device.tdr",)
    expected_outputs: tuple[str, ...]
    inputs: dict[str, str]
    source_map: dict[str, SourceLocation]
    qualification: Literal["candidate_requires_native_review"] = "candidate_requires_native_review"
    operating_points: tuple[NativeOperatingPoint, ...] = ()
    native_review: NativeReview | None = None


_MAX_INPUT_BYTES = 512 * 1024 * 1024


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _bundle_digest(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode())
        digest.update(b"\0")
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def validate_bundle(
    job: CompiledJob,
    *,
    require_mesh: bool = True,
    simulator_version: str | None = None,
) -> SentaurusJobManifest:
    """Check identity/completeness, not mesh physics or native syntax correctness."""
    if job.backend != "sentaurus":
        raise ValueError("only Sentaurus bundles can be prepared")
    root = job.entrypoint.parent.resolve()
    names = [path.name for path in job.input_files]
    if len(names) != len(set(names)) or not names or len(names) > 256:
        raise ValueError("duplicate or excessive bundle inputs")
    total = 0
    for path in job.input_files:
        if path.is_symlink():
            raise ValueError("bundle input symlinks are forbidden")
        if path.resolve().parent != root or not path.is_file():
            raise ValueError("bundle inputs must be regular files in the job directory")
        total += path.stat().st_size
    if total > _MAX_INPUT_BYTES:
        raise ValueError("bundle exceeds input size limit")
    if "job-manifest.json" not in names:
        raise ValueError("missing Sentaurus job manifest")
    if _bundle_digest(job.input_files) != job.input_digest:
        raise ValueError("compiled bundle digest mismatch")
    manifest = SentaurusJobManifest.model_validate_json((root / "job-manifest.json").read_bytes())
    if set(names) != {*manifest.inputs, "job-manifest.json"}:
        raise ValueError("bundle files do not match the manifest")
    if set(manifest.inputs) - {"experiment.json", "sdevice.cmd", "device.tdr"}:
        raise ValueError("unrecognized bundle input")
    if (
        job.entrypoint != root / manifest.command_file
        or manifest.compiler_version != job.compiler_version
    ):
        raise ValueError("compiler/entrypoint does not match the manifest")
    for name, expected in manifest.inputs.items():
        if _file_digest(root / name) != expected:
            raise ValueError(f"bundle input hash mismatch: {name}")
    if require_mesh:
        if any(name not in names for name in manifest.required_runtime_inputs):
            raise ValueError("missing native mesh: bind a reviewed device.tdr before submission")
        if manifest.native_review is None:
            raise ValueError("native mesh and deck review reference is required")
        if simulator_version and manifest.native_review.simulator_version != simulator_version:
            raise ValueError("native review release differs from the configured release")
    return manifest


def bind_mesh(
    job: CompiledJob,
    mesh: Path,
    destination: Path,
    *,
    simulator_version: str,
    review_reference: str,
) -> CompiledJob:
    """Make a new hash-bound bundle from a release-reviewed external native mesh.

    The caller's review must cover geometry, doping, contact names and the deck.
    Opaque bytes cannot establish that review or qualify the physics automatically.
    """
    manifest = validate_bundle(job, require_mesh=False)
    if not simulator_version.strip() or not review_reference.strip():
        raise ValueError("exact release and native review reference are required")
    if mesh.is_symlink() or not mesh.is_file() or not 0 < mesh.stat().st_size <= _MAX_INPUT_BYTES:
        raise ValueError("mesh must be a nonempty bounded regular file, not a symlink")
    if (
        sum(path.stat().st_size for path in job.input_files) + mesh.stat().st_size
        > _MAX_INPUT_BYTES
    ):
        raise ValueError("bundle exceeds input size limit")
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for path in job.input_files:
        if path.name not in {"job-manifest.json", "device.tdr"}:
            shutil.copyfile(path, destination / path.name)
    shutil.copyfile(mesh, destination / "device.tdr")
    manifest = manifest.model_copy(
        update={
            "inputs": {**manifest.inputs, "device.tdr": _file_digest(destination / "device.tdr")},
            "native_review": NativeReview(
                simulator_version=simulator_version, reference=review_reference
            ),
        }
    )
    (destination / "job-manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    paths = tuple(destination / name for name in sorted({*manifest.inputs, "job-manifest.json"}))
    prepared = job.model_copy(
        update={
            "entrypoint": destination / manifest.command_file,
            "input_files": paths,
            "input_digest": _bundle_digest(paths),
        }
    )
    validate_bundle(prepared, simulator_version=simulator_version)
    return prepared
