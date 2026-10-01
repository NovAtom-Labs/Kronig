import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from tcad_agent.bundles.export import BundleArchiveService, LegacyBundleImporter
from tcad_agent.bundles.models import BundleInputs
from tcad_agent.bundles.reader import BundleIntegrityError, BundleReader
from tcad_agent.bundles.writer import BundleWriter
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.events.ledger import EventLedger
from tcad_agent.events.models import RunEventKind
from tcad_agent.results.models import BiasPoint, CanonicalResult, FieldSeries
from tcad_agent.runners.models import CompiledJob, NativeRunResult
from tcad_agent.validation.engine import ValidationEngine


def bundle_inputs(tmp_path: Path, valid_spec: ExperimentSpec) -> BundleInputs:
    compiled = tmp_path / "source-compiled"
    compiled.mkdir()
    input_path = compiled / "input.json"
    runtime_path = compiled / "run_devsim.py"
    stdout_path = compiled / "stdout.log"
    stderr_path = compiled / "stderr.log"
    native_path = compiled / "native_result.json"
    input_path.write_text("{}")
    runtime_path.write_text("# reviewed runtime\n")
    stdout_path.write_text("solver completed\n")
    stderr_path.write_text("")
    native_path.write_text("{}")
    events_path = compiled / "events.jsonl"
    ledger = EventLedger(events_path)
    ledger.append(RunEventKind.REQUESTED, {"run_id": "run-0001"})
    ledger.append(RunEventKind.COMPLETED, {"status": "completed"})
    job = CompiledJob(
        backend="devsim",
        entrypoint=runtime_path,
        input_files=(input_path, runtime_path),
        input_digest="a" * 64,
        runtime_digest="b" * 64,
        compiler_version="0.1.0",
    )
    native = NativeRunResult(
        backend="devsim",
        status="completed",
        return_code=0,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        result_path=native_path,
        elapsed_seconds=0.25,
    )
    result = CanonicalResult(
        backend="devsim",
        simulator_version="2.9.1",
        status="completed",
        terminals=("anode", "cathode"),
        bias_points=(
            BiasPoint(
                bias_v=0.1,
                converged=True,
                terminal_currents_a_per_m2={"anode": 1.0, "cathode": -1.0},
            ),
        ),
        fields={
            "potential": FieldSeries(
                positions_m=(0.0, 0.5e-6, 1.0e-6),
                values=(0.0, 0.4, 0.8),
                unit="V",
            ),
            "electron_density": FieldSeries(
                positions_m=(0.0, 0.5e-6, 1.0e-6),
                values=(1.0e16, 1.0e19, 1.0e23),
                unit="m^-3",
            ),
        },
    )
    validation = ValidationEngine().validate(result)
    return BundleInputs(
        run_id="run-0001",
        spec=valid_spec,
        job=job,
        native=native,
        result=result,
        validation=validation,
        events_path=events_path,
    )


def test_bundle_manifest_hashes_every_artifact_and_report_uses_structured_values(
    tmp_path: Path, valid_spec: ExperimentSpec
) -> None:
    bundle = BundleWriter(tmp_path / "bundles").write(bundle_inputs(tmp_path, valid_spec))
    manifest = json.loads((bundle.root / "manifest.json").read_text())
    assert manifest["state"] == "completed"
    assert manifest["execution_state"] == "completed"
    assert manifest["validation_state"] == "passed"
    assert set(manifest["artifacts"]) >= {
        "experiment.json",
        "compiled/input.json",
        "logs/stdout.log",
        "results/canonical.json",
        "results/fields.csv",
        "results/field-plots.svg",
        "validation/report.json",
        "events.jsonl",
        "report.md",
        "traceability.json",
    }
    for relative, item in manifest["artifacts"].items():
        data = (bundle.root / relative).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
    EventLedger(bundle.root / "events.jsonl").verify()
    report = (bundle.root / "report.md").read_text()
    assert "TCAD Evidence Summary" in report
    assert "Research report" not in report
    assert "1.000000e+00 A/m^2" in report
    assert "Evidence origin" in report
    assert "Requested output traceability" in report
    assert "potential" in (bundle.root / "results" / "fields.csv").read_text()
    plot = (bundle.root / "results" / "field-plots.svg").read_text()
    assert "<svg" in plot
    assert "electron_density" in plot


def test_bundle_reader_verifies_and_loads_axis_aware_results(
    tmp_path: Path, valid_spec: ExperimentSpec
) -> None:
    bundle = BundleWriter(tmp_path / "bundles").write(bundle_inputs(tmp_path, valid_spec))

    verified = BundleReader().read(bundle.root)

    assert verified.result.datasets["potential"].unit == "V"
    assert verified.result.axes["position__potential"].kind == "position"


def test_bundle_reader_rejects_tampered_canonical_data(
    tmp_path: Path, valid_spec: ExperimentSpec
) -> None:
    bundle = BundleWriter(tmp_path / "bundles").write(bundle_inputs(tmp_path, valid_spec))
    (bundle.root / "results" / "canonical.json").write_text("{}\n")

    with pytest.raises(BundleIntegrityError, match="mismatch"):
        BundleReader().read(bundle.root)


def test_bundle_export_is_verified_deterministic_and_user_selected(
    tmp_path: Path, valid_spec: ExperimentSpec
) -> None:
    bundle = BundleWriter(tmp_path / "bundles").write(bundle_inputs(tmp_path, valid_spec))
    service = BundleArchiveService()

    first = service.export(bundle.root, tmp_path / "exports" / "study.akbundle")
    second = service.export(bundle.root, tmp_path / "exports" / "study-copy.akbundle")

    assert first.destination == tmp_path / "exports" / "study.akbundle"
    assert first.sha256 == second.sha256
    with zipfile.ZipFile(first.destination) as archive:
        assert "manifest.json" in archive.namelist()
        assert "results/canonical.json" in archive.namelist()


def test_verified_legacy_import_preserves_source_and_rejects_tampering(
    tmp_path: Path, valid_spec: ExperimentSpec
) -> None:
    source = BundleWriter(tmp_path / "legacy-runs").write(
        bundle_inputs(tmp_path, valid_spec)
    ).root
    importer = LegacyBundleImporter(tmp_path / "managed" / "bundles")

    imported = importer.import_directory(source)

    assert imported.is_dir()
    assert source.is_dir()
    assert BundleReader().read(imported).manifest.run_id == "run-0001"
    with pytest.raises(FileExistsError, match="already exists"):
        importer.import_directory(source)

    other_inputs = tmp_path / "other-inputs"
    other_inputs.mkdir()
    tampered_source = BundleWriter(tmp_path / "other-legacy-runs").write(
        bundle_inputs(other_inputs, valid_spec)
    ).root
    (tampered_source / "results" / "canonical.json").write_text("{}\n")
    with pytest.raises(BundleIntegrityError, match="mismatch"):
        LegacyBundleImporter(tmp_path / "other-managed").import_directory(
            tampered_source
        )


def test_failed_bundle_write_removes_staging_directory(
    tmp_path: Path, valid_spec: ExperimentSpec
) -> None:
    inputs = bundle_inputs(tmp_path, valid_spec).model_copy(
        update={"events_path": tmp_path / "missing-events.jsonl"}
    )
    root = tmp_path / "bundles"

    with pytest.raises(FileNotFoundError, match="event ledger"):
        BundleWriter(root).write(inputs)

    assert not (root / ".run-0001.staging").exists()
