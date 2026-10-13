import sys
from pathlib import Path

import pytest

from tcad_agent.adapters.registry import BackendAdapterUnavailable, get_backend
from tcad_agent.desktop.devsim_runner import DevsimSidecarRunner
from tcad_agent.runners.local import LocalRunner


def test_devsim_backend_binding_owns_adapter_and_runner() -> None:
    binding = get_backend("devsim")

    assert binding.adapter.manifest.backend == "devsim"


def test_devsim_backend_uses_packaged_sidecar_when_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = tmp_path / "agent-kronig-devsim"
    runner.write_text("fixed sidecar")
    monkeypatch.setenv("AGENT_KRONIG_DEVSIM_RUNNER", str(runner))

    binding = get_backend("devsim")

    assert isinstance(binding.runner, DevsimSidecarRunner)
    assert binding.runner.executable == runner.resolve()


def test_devsim_backend_defaults_to_active_python_without_machine_local_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("AGENT_KRONIG_DEVSIM_RUNNER", raising=False)
    monkeypatch.delenv("TCAD_DEVSIM_PYTHON", raising=False)
    monkeypatch.chdir(tmp_path)

    binding = get_backend("devsim")

    assert isinstance(binding.runner, LocalRunner)
    assert binding.runner.devsim_python == Path(sys.executable).absolute()


def test_sentaurus_backend_uses_ssh_runner_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TCAD_SENTAURUS_RUNNER", "ssh")

    binding = get_backend("sentaurus")

    assert binding.adapter.manifest.backend == "sentaurus"
    assert type(binding.runner).__name__ == "SSHSentaurusRunner"


def test_unknown_backend_refuses_explicitly() -> None:
    with pytest.raises(BackendAdapterUnavailable, match="unknown"):
        get_backend("unknown")


def test_researcher_interfaces_do_not_import_devsim_adapter_directly() -> None:
    project = Path(__file__).parents[3]
    for relative in ("src/tcad_agent/cli.py", "src/tcad_agent/agent/tools.py"):
        source = (project / relative).read_text()
        assert "DevsimAdapter" not in source
        assert 'backend != "devsim"' not in source
