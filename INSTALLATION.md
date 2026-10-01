# Agent Kronig Installation and Setup

This guide covers both the self-contained native application and a complete source installation. Most researchers should use a release installer. Developers and operators who need the scientific CLI or a modifiable checkout should use the source procedure and run the native development application.

Sentaurus is not installed by these steps. It must remain on a separately licensed host and is connected through Agent Kronig's restricted remote-runner protocol.

## Self-contained native installation

Release artifacts are produced for Linux AppImage, Debian or Ubuntu `.deb`, Windows NSIS and portable `.zip`, Intel Mac `.dmg` and `.zip`, and Apple Silicon `.dmg` and `.zip`. The native application includes its private backend and reviewed DEVSIM runner. End users do not install Python, Node.js, DEVSIM, Electron, or a browser.

### Download Alpha 12

| System | Recommended package | Alternative |
| --- | --- | --- |
| Linux x86-64 | [AppImage](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-linux-x64.AppImage) | [Debian package](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-linux-x64.deb) |
| Windows x86-64 | [NSIS installer](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-win-x64.exe) | [Portable ZIP](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-win-x64.zip) |
| Intel Mac | [DMG](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-x64.dmg) | [ZIP](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-x64.zip) |
| Apple Silicon | [DMG](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-arm64.dmg) | [ZIP](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-arm64.zip) |

Alpha 12 packages are unsigned and updates are manual. Windows SmartScreen or macOS Gatekeeper may warn before opening them. Download only from the official `v0.1.0-alpha.12` release and verify the package against its `SHA256SUMS.txt` entry.

Install or open the correct package using the normal operating system workflow, open `Settings` to configure Bedrock access, then choose `Open folder` to select a local repository. Agent Kronig changes the selected files directly on that computer. The API key uses operating-system protected storage. On Linux without a secret service, it remains in memory only for that application session.

Detailed platform instructions, application-data locations, update behavior, recovery, release building, and uninstall behavior are in [the desktop application operations guide](docs/operations/desktop-application.md).

## Native source installation

## 1. Supported installation profile

| Component | Supported pilot configuration |
| --- | --- |
| Operating system | Linux, Windows, or macOS workstation with a graphical desktop session |
| Python | CPython 3.13 |
| Desktop runtime | Node.js 24 and pnpm 11.19 |
| Source control | Git |
| Agent model | Amazon Bedrock model available to the configured account and region |
| Local simulator | DEVSIM 2.9.1 in a separate Python environment |
| Licensed simulator | Sentaurus on a separately configured licensed Linux host |

Electron owns an authenticated private backend on `127.0.0.1`. There is no supported standalone browser launcher or public application URL.

## 2. System prerequisites

Install these packages using the workstation's package manager:

- Git
- CPython 3.13, including `venv` support
- Node.js 24 and pnpm 11.19
- a C and C++ build toolchain for packages that do not have a compatible wheel
- `tmux`, recommended for stable long-running agent terminal sessions
- `zenity` or `kdialog`, optional but required for the native desktop folder picker

Example package names on Debian or Ubuntu systems are `git`, `build-essential`, `python3.13`, `python3.13-venv`, `python3.13-dev`, `tmux`, and `zenity`. Python 3.13 may require a distribution release or approved package source that provides it.

Confirm the required tools:

```bash
git --version
python3.13 --version
tmux -V
```

Python must report version 3.13.x. The project intentionally rejects other minor Python versions so the tested OpenHands and scientific dependency set remains reproducible.

## 3. Clone and bootstrap Agent Kronig

On macOS or Linux:

```bash
git clone git@github.com:NovAtom-Labs/Quiloo.git
cd Quiloo
python3.13 scripts/bootstrap_dev.py
```

On Windows PowerShell:

```powershell
git clone git@github.com:NovAtom-Labs/Quiloo.git
cd Quiloo
py -3.13 scripts\bootstrap_dev.py
```

The bootstrap checks every prerequisite before changing the checkout. It then:

- creates the repository `.venv` and installs Agent Kronig in editable mode
- creates a separate sibling `devsim/.venv` with DEVSIM 2.9.1
- installs the locked Electron dependencies
- records dependency fingerprints in ignored `.tcad-agent-dev/bootstrap.json`
- prints the correct launch command for the current operating system

No credential is requested, copied, printed, or stored by the bootstrap. If all fingerprints and outputs are unchanged, rerunning the command skips all three installation stages. Use `--force` to rebuild them deliberately.

For an internal or private deployment, use the organization-approved clone URL and authentication method. Do not place personal access tokens in shell history or repository files.

`requirements.txt` is the supported installer entry point. `requirements.lock` records the complete development environment used to verify the checkout. Edit dependency constraints only in `pyproject.toml`; the requirements files are generated artifacts.

## 4. Configure model access

Launch Agent Kronig and open Settings. Enter the approved Bedrock API key, AWS region, model identifier, and reasoning effort. The key is stored through the operating system's protected credential mechanism when available.

An ignored `.env` remains available for developers who need CLI configuration or advanced runner overrides:

```bash
cp .env.example .env
chmod 600 .env
```

Never commit `.env`, credentials, private signing keys, proprietary Sentaurus documents, or licensed examples. Rotate any credential that appears in a prompt, terminal transcript, report, or commit.

## 5. Optional CLI environment

The desktop launcher reads `.env` safely without evaluating it as shell code. The scientific CLI does not load it implicitly. On macOS or Linux, load it before model-dependent CLI commands with:

```bash
set -a
source .env
set +a
```

## 6. Verify the installation

Run the local checks first:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy --strict src
git diff --check
```

On a machine without Bedrock credentials or Sentaurus, the explicitly marked live tests remain skipped. An ordinary test failure is not expected and should be fixed before researchers use the installation.

Verify the DEVSIM execution path:

```bash
.venv/bin/tcad-agent validate examples/pn-junction.yaml
.venv/bin/tcad-agent run examples/pn-junction.yaml \
  --backend devsim \
  --approve \
  --output runs
```

The run must produce a completed evidence bundle whose validation status is `passed`.

## 7. Start the native development application

On macOS or Linux:

```bash
scripts/run_desktop_dev.sh
```

On Windows PowerShell:

```powershell
.\scripts\run_desktop_dev.ps1
```

Both wrappers use the same Python launcher. It loads the ignored `.env` when present without evaluating shell commands, starts the platform-native Electron binary, and lets Electron supervise the authenticated private backend. It never opens or prints a browser URL. Agent chat, activity, approvals, and OpenHands runtime state live in a process-scoped session directory and are deleted when the application exits. Settings, protected credentials, repository files, compiled outputs, and result bundles persist. Close Agent Kronig before copying persistent application data for backup.

## 8. Verify the repository agent

Create a disposable scientific repository:

```bash
.venv/bin/python scripts/create_repl_test_repo.py
```

To test approval-gated access outside the selected repository, add `--include-external-fixture`. The generator creates a sibling calibration file that must not be read without an explicit primary-agent approval.

In Agent Kronig:

1. Select `Open folder` and choose `test-workspaces/pn-junction-research`.
2. The application creates the temporary workspace session automatically.
3. Send this prompt in Chat:

```text
Read AGENTS.md and RESEARCH_TASK.md, then complete the research task end to end. Inspect and explain the execution path, run the failing checks, fix root causes only in src/junction_lab, rerun all checks, generate the requested artifacts, review the diff, and delegate one independent read-only physics review before finishing. Stay inside this repository. Do not use network services or git mutations. Do not edit tests, experiment.toml, or reference data.
```

4. Confirm the three-pane layout. At desktop width, resize both dividers and double-click each one to restore its default. At tablet width, open Repository as a drawer. At narrow width, open Agent as a drawer.
5. Use Chat for the current workspace session and approval decisions. Scientific execution first produces a repository `PLAN.md` and a compact plan card. Choose `Approve and run`, `Run unattended`, request a revision, or type `approved` while that exact plan is pending. Plan consent expires with the run. Other permission categories remain separate, and `Approve all like this` applies only to the displayed category for the current run.
6. Use Activity to inspect one expandable row per tool action, including phase, delegated ownership, duration, commands, and output. Current-operation summaries are derived from tool events. Raw provider reasoning is never stored or displayed.
7. Use Changes to confirm that only the files attributable to this run appear. Select a changed text file and verify that its unified diff opens in the central workspace.
8. Open a safe text file, select Edit, make a disposable change, and save it. Restore that manual edit before grading so it is not confused with agent work.
9. Wait for the final response, then run the deterministic grader:

```bash
.venv/bin/python evaluations/repl/grade_workspace.py \
  --workspace test-workspaces/pn-junction-research
```

Expected evidence includes five passing tests, corrected source code, generated JSON and Markdown artifacts, unchanged researcher-owned inputs, a delegated review result, and a grader score of 100. The run-scoped Changes view should list exactly `src/junction_lab/physics.py`, `src/junction_lab/report.py`, and `src/junction_lab/validation.py` for the deterministic repair scenario.

## 9. Verify the TCAD agent workflow

Open a repository workspace and paste the prompt in
`examples/prompts/al-pn-al-equilibrium.md`. Ask the agent to inspect the request, prepare the
portable specification, check DEVSIM capabilities, run only the explicit supported subset, and
report the generated evidence.

The local DEVSIM one-dimensional backend now supports the reviewed portable capability set described
in `docs/testing/devsim-1d-expansion-acceptance.md`, including explicit current-density versus
absolute-current semantics, work-function and reviewed Schottky boundaries, Boltzmann and bounded
Fermi transport, mobility models, SRH and Auger recombination, Slotboom band-gap narrowing, band
profiles, temperature and parameter studies, transient and AC studies, and canonical result
validation. Unsupported combinations remain explicit research gates and are never silently removed.

The full request is represented by `examples/al-pn-al-equilibrium.yaml` for the Sentaurus adapter.
Licensed execution must remain unavailable until the remote host passes the Sentaurus integration
and conformance checklist.

Closing Agent Kronig or opening another repository clears the agent chat and activity trail. The
repository and readable experiment projects remain on disk. Immutable compiled inputs, native
outputs, logs, and verified bundles live under Agent Kronig application data instead of cluttering
the selected repository. A later session can inspect the projected artifacts without restoring
earlier chat history.

## 10. Optional Bedrock smoke test

Run this only after loading a valid local credential:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest \
  tests/e2e/test_agentic_repl.py \
  --run-live-bedrock -m live_bedrock -q
```

A model configuration error usually means the credential, region, or inference profile does not match. Provider details are deliberately excluded from researcher-facing error messages so secrets are not leaked.

## 11. Sentaurus connection

Do not install Sentaurus into the Agent Kronig application environment. Follow `docs/operations/sentaurus-integration.md` on the licensed machine. The connection requires an approved HTTPS endpoint, exact release identity, reviewed structure generation, native-result extraction, signing keys, quotas, and cross-backend conformance cases.

Agent Kronig must continue to refuse licensed execution until that integration is explicitly configured and verified.

## 12. Troubleshooting

### Native folder picker does not open

Install `zenity` or `kdialog`, then restart the native development application.

### The model is unavailable

Confirm that `.env` was loaded, the key was created for `AWS_REGION_NAME`, and `LLM_MODEL` names an inference profile available to that account. Do not print the credential while debugging.

### DEVSIM cannot be found

Run the DEVSIM import check directly and set `TCAD_DEVSIM_PYTHON` to the absolute path of the interpreter that succeeds.

### A run waits for approval

Review the exact command or path in the approval card. External paths, package installation, network access, destructive commands, Git mutation, and unknown actions require a decision. Do not approve an action merely to make the run continue.

### A run is paused after restart

Select Resume. Conversation state and events are persisted, but interrupted work is not silently restarted.

### Sentaurus reports unconfigured

This is the safe default. Compilation can be inspected locally, but execution requires the separately licensed and verified remote host.

## 13. Upgrade procedure

Before upgrading, close Agent Kronig and back up `.env` and the application-data directory outside the repository. Then:

```bash
git pull --ff-only
python3.13 scripts/bootstrap_dev.py
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest -q
```

On Windows, use `py -3.13 scripts\bootstrap_dev.py`. Unchanged dependency stages are skipped. Restart the native application only after the verification suite passes. Do not weaken dependency pins or validation checks to force an upgrade through.
