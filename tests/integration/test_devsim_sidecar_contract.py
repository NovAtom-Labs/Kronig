"""Exercise the production sidecar entrypoint with an actual compiled native job."""

import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from tcad_agent.adapters.devsim.compiler import DevsimAdapter
from tcad_agent.adapters.registry import resolve_devsim_python
from tcad_agent.desktop.devsim_runner import DevsimSidecarRunner
from tcad_agent.domain.studies import EquilibriumStudy
from tcad_agent.runners.models import RunBudget
from tcad_agent.validation.engine import ValidationEngine


@pytest.mark.integration
@pytest.mark.skipif(os.name == "nt", reason="POSIX development launcher fixture")
def test_compiler_to_sidecar_runs_real_fermi_physics(tmp_path, valid_spec):
    native_python = resolve_devsim_python()
    located = subprocess.run(
        [
            str(native_python),
            "-c",
            "import json,sysconfig;print(json.dumps(sysconfig.get_path('purelib')))",
        ],
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    package_root = Path(__file__).resolve().parents[2] / "src"
    launcher = tmp_path / "native-sidecar"
    launcher.write_text(
        f"#!{Path(sys.executable).resolve()}\nimport sys\n"
        f"sys.path.insert(0,{str(package_root)!r})\n"
        f"sys.path.append({sysconfig.get_path('purelib')!r})\n"
        f"sys.path.append({json.loads(located.stdout)!r})\n"
        "from tcad_agent.desktop.devsim_runner import main\nraise SystemExit(main())\n"
    )
    launcher.chmod(0o700)
    spec = valid_spec.model_copy(
        update={
            "study": EquilibriumStudy(kind="equilibrium"),
            "physics": valid_spec.physics.model_copy(
                update={
                    "models": tuple(
                        "fermi" if x == "boltzmann" else x for x in valid_spec.physics.models
                    )
                }
            ),
        }
    )
    adapter = DevsimAdapter.from_defaults()
    result = DevsimSidecarRunner(launcher).run(
        adapter.compile(spec, tmp_path / "compiled"), RunBudget(seconds=60)
    )
    assert result.status == "completed", result.stderr_path.read_text()
    canonical = adapter.normalize(result)
    assert canonical.metadata["physics_models"] == list(spec.physics.models)
    assert ValidationEngine().validate(canonical, spec=spec).overall == "passed"
