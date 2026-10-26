"""Real file/shell/timeout protocol exercise with a deliberately synthetic solver.

Only the SSH transport is replaced by local filesystem/process operations. This
tests orchestration, never Sentaurus syntax, licensing, meshes or TCAD physics.
"""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_sentaurus_compiler import equilibrium_spec
from test_sentaurus_tables import export

from tcad_agent.adapters.sentaurus.compiler import SentaurusAdapter
from tcad_agent.adapters.sentaurus.normalizer import SentaurusNormalizer
from tcad_agent.adapters.sentaurus.runtime import bind_mesh
from tcad_agent.domain.models import ExperimentSpec
from tcad_agent.results.query import query_dataset
from tcad_agent.runners.models import RunBudget
from tcad_agent.runners.ssh import SSHSentaurusRunner


class LocalTransport:
    def __init__(self, env, mode):
        self.env = env
        self.mode = mode

    def exec_command(self, command):
        result = subprocess.run(command, shell=True, capture_output=True, env=self.env, timeout=10)
        stdout = io.BytesIO(result.stdout)

        class Channel:
            def recv_exit_status(self):
                return result.returncode

        stdout.channel = Channel()
        return io.BytesIO(), stdout, io.BytesIO(result.stderr)

    def open_sftp(self):
        return self

    def put(self, source, target):
        shutil.copyfile(source, target)

    def lstat(self, path):
        if self.mode == "oversize_export" and Path(path).name == "sentaurus-result.json":
            from types import SimpleNamespace

            return SimpleNamespace(st_mode=0o100600, st_size=65 * 1024 * 1024)
        return Path(path).lstat()

    def get(self, source, target, callback=None):
        if self.mode == "oversize_export" and Path(source).name == "sentaurus-result.json":
            pytest.fail("oversized JSON must be rejected before transfer")
        shutil.copyfile(source, target)
        if callback:
            callback(Path(target).stat().st_size, Path(target).stat().st_size)

    def close(self):
        pass


@pytest.mark.parametrize(
    "mode",
    [
        "success",
        "failed",
        "timeout",
        "missing_export",
        "wrong_release",
        "wrong_terminals",
        "wrong_bias",
        "wrong_provenance",
        "legacy",
        "oversize_export",
    ],
)
def test_synthetic_native_pipeline_preserves_or_rejects_evidence(tmp_path, monkeypatch, mode):
    # GNU timeout is a site prerequisite of the current SSH bridge.
    if os.name != "posix":
        pytest.skip("the remote execution protocol uses a POSIX shell")
    inputs = tmp_path / "exporter-inputs"
    inputs.mkdir()
    data = export(inputs)
    terminal_map = {"left": "anode", "right": "cathode"}
    data["terminals"] = [terminal_map[name] for name in data["terminals"]]
    for point in data["operating_points"]:
        point["terminal_currents_a_per_m2"] = {
            terminal_map[name]: value for name, value in point["terminal_currents_a_per_m2"].items()
        }
    if mode == "wrong_release":
        data["simulator_version"] = "different-release"
    if mode == "wrong_terminals":
        data["terminals"] = ["left", "right"]
        for point in data["operating_points"]:
            point["terminal_currents_a_per_m2"] = {}
    if mode == "wrong_bias":
        data["axes"]["bias"]["values"][1] = 0.7
        data["operating_points"][1]["coordinates"]["bias"] = 0.7
    (inputs / "sentaurus-result.json").write_text(json.dumps(data))
    executable_dir = tmp_path / "bin"
    executable_dir.mkdir()
    if not shutil.which("timeout"):
        # macOS has no GNU timeout. This test-only substitute tests the bridge's
        # budget/status contract, not GNU timeout's implementation or HPC setup.
        timeout = executable_dir / "timeout"
        timeout.write_text(
            f"#!{Path(sys.executable).resolve()}\n"
            "import os,signal,subprocess,sys\n"
            "p=subprocess.Popen(sys.argv[2:],start_new_session=True)\n"
            "try: sys.exit(p.wait(timeout=float(sys.argv[1].removesuffix('s'))))\n"
            "except subprocess.TimeoutExpired:\n"
            " os.killpg(p.pid,signal.SIGKILL);p.wait();sys.exit(124)\n"
        )
        timeout.chmod(0o700)
    executable = executable_dir / "sdevice"
    executable.write_text(
        f"#!{Path(sys.executable).resolve()}\n"
        "import pathlib,shutil,time,sys,json\n"
        f"mode={mode!r}\n"
        "assert pathlib.Path('device.tdr').is_file()\n"
        "if mode=='timeout': time.sleep(5)\n"
        "if mode=='failed': sys.exit(23)\n"
        "pathlib.Path('sdevice.tdr').write_bytes(b'opaque synthetic output')\n"
        "if mode!='missing_export':\n"
        " for name in ('sentaurus-result.json','profiles.csv'):\n"
        f"  shutil.copyfile({str(inputs)!r}+'/'+name,name)\n"
        " data=json.loads(pathlib.Path('sentaurus-result.json').read_text())\n"
        " manifest=json.loads(pathlib.Path('job-manifest.json').read_text())\n"
        " data['provenance']={'compiler_version':manifest['compiler_version'],\n"
        "  'experiment_sha256':manifest['inputs']['experiment.json'],\n"
        "  'mesh_sha256':manifest['inputs']['device.tdr']}\n"
        " if mode=='wrong_provenance': data['provenance']['mesh_sha256']='0'*64\n"
        " if mode=='legacy':\n"
        "  data={'schema_version':'1.0','simulator_version':data['simulator_version'],\n"
        "   'status':'completed','terminals':data['terminals'],'fields':{},\n"
        "   'bias_points':[], 'current_density_unit':'A/m^2'}\n"
        " pathlib.Path('sentaurus-result.json').write_text(json.dumps(data))\n"
    )
    executable.chmod(0o700)
    env = {**os.environ, "PATH": str(executable_dir) + os.pathsep + os.environ["PATH"]}
    monkeypatch.delenv("TCAD_SENTAURUS_VERSION", raising=False)
    spec_data = equilibrium_spec().model_dump(mode="json")
    spec_data["name"] = "layered-silicon-study"
    spec_data["regions"][0]["id"] = "region_alpha"
    spec_data["profiles"][0]["region"] = "region_alpha"
    spec_data["observables"].remove("fermi_level")
    spec_data["study"] = {"kind": "dc_points", "contact": "anode", "values": ["-1 V", "0.6 V"]}
    adapter = SentaurusAdapter.from_defaults()
    compiled = adapter.compile(ExperimentSpec.model_validate(spec_data), tmp_path / "candidate")
    mesh = tmp_path / "synthetic-mesh.tdr"
    mesh.write_bytes(b"not a native mesh")
    job = bind_mesh(
        compiled,
        mesh,
        tmp_path / "prepared",
        simulator_version="synthetic-not-a-native-benchmark",
        review_reference="synthetic-fixture-only",
    )
    runner = SSHSentaurusRunner(
        host="local-test.invalid", user="test", remote_root=str(tmp_path / "remote")
    )
    monkeypatch.setattr(runner, "_connect", lambda: LocalTransport(env, mode))
    result = runner.run(job, RunBudget(seconds=0.1 if mode == "timeout" else 5))
    if mode == "success":
        assert result.status == "completed", result.error
        normalized = SentaurusNormalizer().normalize(result)
        curve = query_dataset(normalized, "capacitance", max_points=100)
        assert curve.values == pytest.approx((1e-4, 2e-4))
        assert (result.result_path.parent / "profiles.csv").is_file()
        audit = json.loads(result.audit_json_path.read_text())
        assert any(event["action"] == "bundle.preflight" for event in audit["events"])
    elif mode == "failed":
        assert result.status == "execution_failed"
        assert result.return_code == 23
    elif mode == "timeout":
        assert result.status == "timed_out"
    elif mode == "oversize_export":
        assert result.status == "execution_failed"
        assert "size limit" in result.error
    else:
        assert result.status == "malformed_result", result.error
        assert result.error
