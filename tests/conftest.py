from pathlib import Path

import pytest
import yaml

from tcad_agent.domain.models import ExperimentSpec

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
