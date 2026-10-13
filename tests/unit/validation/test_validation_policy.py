from pathlib import Path
from types import SimpleNamespace

import pytest

from tcad_agent.results.models import CanonicalResult
from tcad_agent.validation import policy
from tcad_agent.validation.engine import ValidationEngine
from tcad_agent.validation.models import ValidationReport


def test_fresh_reports_record_policy_and_legacy_reports_do_not_infer_it() -> None:
    report = ValidationEngine().validate(CanonicalResult(backend="devsim", status="completed"))
    assert report.validation_policy_digest == policy.validation_policy_digest()
    assert len(report.validation_policy_digest) == 64
    assert ValidationReport(overall="passed", checks=()).validation_policy_digest is None


@pytest.mark.parametrize(
    "relative",
    [
        "validation/engine.py",
        "validation/physics.py",
        "validation/datasets.py",
        "validation/convergence.py",
        "validation/analytical.py",
        "domain/units.py",
        "domain/studies.py",
        "domain/models.py",
        "domain/profiles.py",
        "results/datasets.py",
    ],
)
def test_validation_policy_digest_changes_with_acceptance_source_drift(
    monkeypatch, relative
) -> None:
    original = policy.validation_policy_digest()
    read_bytes = Path.read_bytes
    package_root = Path(policy.__file__).parent.parent

    def changed_source(path: Path) -> bytes:
        content = read_bytes(path)
        return (
            content + b"\n# Changed scientific criterion\n"
            if path == package_root / relative
            else content
        )

    monkeypatch.setattr(Path, "read_bytes", changed_source)
    assert policy.validation_policy_digest() != original


def test_validation_policy_refuses_unavailable_source_and_module_code(monkeypatch) -> None:
    read_bytes = Path.read_bytes
    expected_path = Path(policy.__file__).parent / "physics.py"

    def missing_source(path: Path) -> bytes:
        if path == expected_path:
            raise FileNotFoundError("missing criterion source")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", missing_source)
    monkeypatch.setattr(
        policy,
        "import_module",
        lambda _name: SimpleNamespace(
            __spec__=SimpleNamespace(loader=SimpleNamespace(get_code=lambda _name: None))
        ),
    )
    with pytest.raises(ValueError, match="validation policy"):
        policy.validation_policy_digest()


def test_frozen_policy_uses_module_code_when_source_files_are_unavailable(monkeypatch) -> None:
    def missing_source(_path: Path) -> bytes:
        raise FileNotFoundError("frozen archive has no .py files")

    def frozen_module(_name: str):
        code = compile("def criterion():\n    return 0.05\n", "/build/one/module.py", "exec")
        return SimpleNamespace(
            __spec__=SimpleNamespace(loader=SimpleNamespace(get_code=lambda _name: code))
        )

    monkeypatch.setattr(Path, "read_bytes", missing_source)
    monkeypatch.setattr(policy, "import_module", frozen_module)
    first = policy.validation_policy_digest()
    assert len(first) == 64
    assert first == policy.validation_policy_digest()

    def relocated_module(_name: str):
        code = compile("def criterion():\n    return 0.05\n", "C:/installed/module.py", "exec")
        return SimpleNamespace(
            __spec__=SimpleNamespace(loader=SimpleNamespace(get_code=lambda _name: code))
        )

    monkeypatch.setattr(policy, "import_module", relocated_module)
    assert policy.validation_policy_digest() == first

    def changed_module(name: str):
        value = "0.10" if name == "tcad_agent.validation.physics" else "0.05"
        code = compile(f"def criterion():\n    return {value}\n", "/build/one/module.py", "exec")
        return SimpleNamespace(
            __spec__=SimpleNamespace(loader=SimpleNamespace(get_code=lambda _name: code))
        )

    monkeypatch.setattr(policy, "import_module", changed_module)
    assert policy.validation_policy_digest() != first
