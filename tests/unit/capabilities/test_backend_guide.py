"""The backend guide shown to Kronig must never promise more than the manifest supports."""

import re

import yaml

from tcad_agent.capabilities.active import resolve_backend
from tcad_agent.capabilities.descriptors import CapabilityCatalog
from tcad_agent.capabilities.models import CapabilityManifest


def _inventory(guide: str) -> dict[str, list[str]]:
    block = re.search(r"```yaml inventory\n(.*?)```", guide, re.S)
    assert block, "the guide needs a machine-checked inventory block"
    return yaml.safe_load(block.group(1))


def test_sentaurus_guide_inventory_equals_the_manifest() -> None:
    manifest = CapabilityManifest.from_backend("sentaurus")
    inventory = _inventory(manifest.guide)
    for field, values in inventory.items():
        assert sorted(getattr(manifest, field)) == sorted(values), field


def test_guide_reaches_the_preparation_view_and_is_part_of_the_digest() -> None:
    manifest = CapabilityManifest.from_backend("sentaurus")
    catalog = CapabilityCatalog.from_manifest(manifest)
    assert "Available now" in catalog.public_view().guide
    edited = CapabilityCatalog.from_manifest(manifest.model_copy(update={"guide": "other"}))
    assert edited.digest != catalog.digest


def test_backend_without_a_guide_still_loads() -> None:
    assert CapabilityManifest.from_backend("devsim").guide == ""


def test_the_simulator_a_request_names_selects_the_backend(monkeypatch) -> None:
    monkeypatch.delenv("TCAD_BACKEND", raising=False)
    assert resolve_backend("use Sentaurus on the HPC") == "sentaurus"
    assert resolve_backend("run it in SDevice please") == "sentaurus"
    assert resolve_backend("use DEVSIM") == "devsim"
    assert resolve_backend("a pn junction") == "devsim"
    assert resolve_backend("compare devsim and sentaurus") == "devsim"
    monkeypatch.setenv("TCAD_BACKEND", "sentaurus")
    assert resolve_backend("a pn junction") == "sentaurus"
    assert resolve_backend("use DEVSIM") == "devsim"
