import hashlib
from pathlib import Path

import pytest
import yaml

from tcad_agent.bundles.models import ArtifactRecord, BundleManifest
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.results.models import BiasPoint, CanonicalResult, FieldSeries
from tcad_agent.validation.engine import ValidationEngine

ROOT = Path(__file__).parents[1]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live-bedrock",
        action="store_true",
        default=False,
        help="run the opt-in Amazon Bedrock smoke test",
    )


@pytest.fixture
def valid_spec() -> ExperimentSpec:
    payload = yaml.safe_load((ROOT / "examples" / "pn-junction.yaml").read_text())
    return ExperimentSpec.model_validate(payload)


@pytest.fixture
def result_bundle_factory(valid_spec: ExperimentSpec):
    def create(
        root: Path,
        *,
        result_backend: str = "devsim",
        manifest_backend: str = "devsim",
    ) -> Path:
        bundle = root / "run-0001"
        (bundle / "results").mkdir(parents=True)
        (bundle / "validation").mkdir()
        result = CanonicalResult(
            backend=result_backend,
            simulator_version="2.10.0",
            status="completed",
            terminals=("left", "right"),
            bias_points=tuple(
                BiasPoint(
                    bias_v=bias,
                    converged=True,
                    terminal_currents_a_per_m2={
                        "left": 2.0e-16,
                        "right": -2.0e-16,
                    },
                )
                for bias in (0.0, 0.1, 0.2)
            ),
            fields={
                "potential": FieldSeries(
                    positions_m=(0.0, 1.0e-6, 2.0e-6),
                    values=(0.0, 0.41, 0.82),
                    unit="V",
                ),
                "electric_field": FieldSeries(
                    positions_m=(0.0, 1.0e-6, 2.0e-6),
                    values=(0.0, 1.6e7, 0.0),
                    unit="V/m",
                ),
                "electron_density": FieldSeries(
                    positions_m=(0.0, 1.0e-6, 2.0e-6),
                    values=(1.0e16, 1.0e19, 1.0e22),
                    unit="m^-3",
                ),
                "hole_density": FieldSeries(
                    positions_m=(0.0, 1.0e-6, 2.0e-6),
                    values=(1.0e22, 1.0e19, 1.0e16),
                    unit="m^-3",
                ),
            },
        )
        validation = ValidationEngine().validate(result, spec=valid_spec)
        files = {
            "experiment.json": valid_spec.model_dump_json(indent=2),
            "results/canonical.json": result.model_dump_json(indent=2),
            "validation/report.json": validation.model_dump_json(indent=2),
        }
        artifacts = {}
        for relative, content in files.items():
            target = bundle / relative
            target.write_text(content.rstrip() + "\n")
            raw = target.read_bytes()
            artifacts[relative] = ArtifactRecord(
                sha256=hashlib.sha256(raw).hexdigest(),
                bytes=len(raw),
            )
        manifest = BundleManifest(
            run_id="run-0001",
            state="completed",
            backend=manifest_backend,
            simulator_version="2.10.0",
            compiler_version="0.1.0",
            input_digest="a" * 64,
            runtime_digest="b" * 64,
            artifacts=artifacts,
        )
        (bundle / "manifest.json").write_text(
            manifest.model_dump_json(indent=2).rstrip() + "\n"
        )
        return bundle

    return create


@pytest.fixture
def unsupported_spec(valid_spec: ExperimentSpec) -> ExperimentSpec:
    physics = valid_spec.physics.model_copy(update={"models": ("hydrodynamic",)})
    return valid_spec.model_copy(update={"physics": physics})


@pytest.fixture
def devsim_manifest():
    from tcad_agent.capabilities.models import CapabilityManifest

    return CapabilityManifest.from_backend("devsim")


@pytest.fixture
def sentaurus_manifest():
    from tcad_agent.capabilities.models import CapabilityManifest

    return CapabilityManifest.from_backend("sentaurus")


@pytest.fixture(autouse=True)
def isolate_sentaurus_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent developer-specific Sentaurus settings from leaking into tests."""
    import os

    for key in tuple(os.environ):
        if key.startswith("TCAD_SENTAURUS_"):
            monkeypatch.delenv(key, raising=False)
