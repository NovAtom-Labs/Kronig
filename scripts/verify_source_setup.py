#!/usr/bin/env python3
"""Verify an existing native source setup without model credentials or user data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.bootstrap_dev import development_paths  # noqa: E402
from scripts.configure_ci_environment import _windows_mkl_runtime  # noqa: E402
from tcad_agent.observability.diagnostics import redact_diagnostic  # noqa: E402


class SmokeStageFailure(RuntimeError):
    def __init__(self, stage: str, diagnostics: str):
        self.stage = stage
        super().__init__(f"{stage}: {redact_diagnostic(diagnostics)[-2000:]}")


def run_checked(command, *, cwd, environment, timeout=180, stage="native process") -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise SmokeStageFailure(stage, result.stdout + "\n" + result.stderr)
    return result.stdout.strip()


def clean_environment(environment: dict[str, str]) -> dict[str, str]:
    return {
        name: value
        for name, value in environment.items()
        if not name.upper().startswith(("AWS_", "TCAD_", "AGENT_KRONIG_", "LLM_", "ELECTRON_"))
        and not any(word in name.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "API_KEY"))
        and name.upper() != "PYTHONPATH"
    }


def setup_snapshot(root: Path) -> tuple[str, str, int, int]:
    cache = root / ".tcad-agent-dev/bootstrap.json"
    index = root / "knowledge-sources/index/knowledge.sqlite3"
    stages = json.loads(cache.read_text())["stages"]
    if set(stages) != {"application", "devsim", "desktop"}:
        raise ValueError("setup receipt does not contain every dependency stage")
    return (
        hashlib.sha256(cache.read_bytes()).hexdigest(),
        hashlib.sha256(index.read_bytes()).hexdigest(),
        index.stat().st_mtime_ns,
        cache.stat().st_mtime_ns,
    )


def require_reuse(before: tuple[str, str, int, int], after: tuple[str, str, int, int]) -> None:
    if before != after:
        raise ValueError("repeat setup did not reuse its dependency receipts and knowledge index")


def scientific_summary(bundle):
    if bundle.manifest.state != "completed" or bundle.result.status != "completed":
        raise ValueError("native simulation did not complete")
    if bundle.validation.overall != "passed":
        raise ValueError("native simulation validation did not pass")
    if bundle.manifest.simulator_version != bundle.result.simulator_version:
        raise ValueError("native simulator provenance does not match canonical results")
    return {
        "status": "passed",
        "validation": bundle.validation.overall,
        "simulator_version": bundle.manifest.simulator_version,
        "input_digest": bundle.manifest.input_digest,
        "runtime_digest": bundle.manifest.runtime_digest,
        "artifacts_verified": len(bundle.manifest.artifacts),
    }


def simulation(output: Path) -> dict[str, object]:
    import yaml

    from tcad_agent.bundles.reader import BundleReader
    from tcad_agent.domain.models import ExperimentSpec
    from tcad_agent.experiments.service import ExperimentEngine
    from tcad_agent.runners.models import RunBudget

    spec = ExperimentSpec.model_validate(
        yaml.safe_load((ROOT / "examples/pn-junction.yaml").read_text())
    )
    engine = ExperimentEngine()
    prepared = engine.prepare(spec, "devsim")
    bundle = engine.execute(
        prepared,
        approved_plan_digest=prepared.plan_digest,
        output_root=output,
        budget=RunBudget(seconds=120),
    )
    return scientific_summary(BundleReader().read(bundle.root))


BACKEND_SMOKE = r"""
const path = require('node:path');
const crypto = require('node:crypto');
const [root, dataDir] = process.argv.slice(1);
const {BackendSupervisor} = require(path.join(root, 'desktop/src/backend-supervisor.js'));
const supervisor = new BackendSupervisor({projectRoot:root, dataDir,
  environment:process.env, tokenFactory:()=>crypto.randomBytes(32).toString('base64url'),
  startupTimeoutMs:120000});
(async()=>{
  try {
    const ready = await supervisor.start();
    const response = await fetch(ready.url + '/desktop/bootstrap?token=' + ready.launchToken,
                                 {redirect:'manual'});
    if (response.status !== 303 && response.status !== 302)
      throw new Error('Session exchange failed');
    const cookie = response.headers.get('set-cookie').split(';')[0];
    const page = await fetch(ready.url + '/', {headers:{cookie}});
    const html = await page.text();
    if (!page.ok || !html.includes('Agent Kronig'))
      throw new Error('Workspace renderer unavailable');
  } finally {await supervisor.stop();}
  if (supervisor.running) throw new Error('Owned backend failed to stop');
  console.log(JSON.stringify({status:'passed', session_exchange:true,
                            renderer:true, shutdown:true}));
})().catch(error=>{console.error(error.message); process.exitCode=1;});
"""


def verify(repeat_bootstrap: bool) -> dict[str, object]:
    paths = development_paths(ROOT, platform.system())
    if Path(sys.prefix).resolve() != paths.application_python.parent.parent.resolve():
        raise ValueError("run this verifier with the checkout's .venv Python")
    environment = clean_environment(dict(os.environ))
    environment.update(
        {
            "TCAD_DEVSIM_PYTHON": str(paths.devsim_python),
            "TCAD_KNOWLEDGE_INDEX": str(ROOT / "knowledge-sources/index/knowledge.sqlite3"),
            "TCAD_SKILLS_ROOT": str(ROOT / "skills"),
            "OPENHANDS_SUPPRESS_BANNER": "1",
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    if platform.system() == "Windows":
        runtime = _windows_mkl_runtime(paths.devsim_python.parent.parent)
        environment["DEVSIM_MATH_LIBS"] = str(runtime)
        environment["PATH"] = str(runtime.parent) + os.pathsep + environment.get("PATH", "")

    def run(command: list[str], *, timeout: int = 180, stage="native process") -> str:
        return run_checked(command, cwd=ROOT, environment=environment, timeout=timeout, stage=stage)

    report: dict[str, object] = {
        "schema_version": "1.0",
        "status": "passed",
        "os": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "application_commit": run(["git", "rev-parse", "HEAD"]),
        "source_dirty": bool(run(["git", "status", "--porcelain"])),
        "dependency_inputs": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "requirements.txt",
                "requirements.lock",
                "requirements/devsim.txt",
                "desktop/pnpm-lock.yaml",
            )
        },
        "visual_gui_qualification": "not_performed",
    }
    run([sys.executable, "-m", "pip", "check"], stage="application dependencies")
    if repeat_bootstrap:
        before = setup_snapshot(ROOT)
        start = time.monotonic()
        run(
            [sys.executable, str(ROOT / "scripts/bootstrap_dev.py")],
            timeout=600,
            stage="repeat bootstrap",
        )
        require_reuse(before, setup_snapshot(ROOT))
        report["repeat_setup"] = {"status": "passed", "seconds": round(time.monotonic() - start, 2)}

    from tcad_agent.knowledge.retrieve import KnowledgeIndex

    hits = KnowledgeIndex(ROOT / "knowledge-sources/index/knowledge.sqlite3").search(
        "Schottky Fermi contact", {"backend": "devsim", "version": "2.9.1"}, limit=20
    )
    sources = {hit.citation.source_id for hit in hits if hit.reviewed}
    required = {"devsim-source-2.9.1", "devsim-documentation-2.9.0"}
    if not required <= sources:
        raise ValueError("reviewed public source and documentation retrieval is incomplete")
    report["knowledge_sources"] = sorted(required)
    electron_environment = {**environment, "ELECTRON_RUN_AS_NODE": "1"}
    electron = run_checked(
        [str(paths.electron), "-p", "process.versions.electron"],
        cwd=ROOT,
        environment=electron_environment,
        timeout=60,
        stage="Electron runtime",
    )
    expected = json.loads((ROOT / "desktop/package.json").read_text())["devDependencies"][
        "electron"
    ]
    if electron != expected:
        raise ValueError("native Electron executable does not match its dependency pin")
    report["electron"] = electron
    node = shutil.which("node")
    if node is None:
        raise ValueError("Node.js is unavailable")
    with tempfile.TemporaryDirectory(prefix="kronig-native-smoke-") as temporary:
        scratch = Path(temporary)
        report["simulation"] = json.loads(
            run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--simulation-output",
                    str(scratch / "runs"),
                ],
                stage="scientific simulation",
            )
        )
        report["desktop_backend"] = json.loads(
            run(
                [node, "-e", BACKEND_SMOKE, str(ROOT), str(scratch / "application-data")],
                stage="desktop backend",
            )
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repeat-bootstrap", action="store_true")
    parser.add_argument("--simulation-output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        report = (
            simulation(args.simulation_output)
            if args.simulation_output
            else verify(args.repeat_bootstrap)
        )
        status = 0
    except Exception as error:
        report = {
            "schema_version": "1.0",
            "status": "failed",
            "os": platform.system(),
            "architecture": platform.machine(),
            "application_commit": os.getenv("GITHUB_SHA", "unrecorded"),
            "failing_stage": getattr(error, "stage", "verification"),
            "error_type": type(error).__name__,
            "message": str(error)[:2000],
        }
        status = 1
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
