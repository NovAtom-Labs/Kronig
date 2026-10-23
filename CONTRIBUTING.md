# Contributing to Agent Kronig

Agent Kronig combines a native repository agent with a deterministic scientific execution core. Changes must preserve both software correctness and the simulator-neutral product boundary.

## Engineering rules

- Treat `ExperimentSpec` as the simulator-neutral contract.
- Never branch product behavior on a named device such as a diode, MOS capacitor, or MOSFET.
- Keep simulator syntax inside its adapter package.
- Refuse unsupported physics instead of approximating it silently.
- Derive reported numeric values from canonical result fields.
- Preserve source, version, hash, compiler, simulator, and validation provenance.
- Never commit credentials, private signing keys, proprietary Sentaurus documentation, or licensed examples.
- Add behavior with a failing test first.

## Development setup

Use Python 3.13, Node.js 24, pnpm 11.19, and Git. On macOS or Linux, prepare and launch the native development application with:

```bash
python3.13 scripts/bootstrap_dev.py
./scripts/run_desktop_dev.sh
```

On Windows PowerShell:

```powershell
py -3.13 scripts\bootstrap_dev.py
.\scripts\run_desktop_dev.ps1
```

On macOS, double-click the tracked **Launch Agent Kronig Dev.command** shortcut or run `./"Launch Agent Kronig Dev.command"`. No activation or installer build is needed. Bootstrap checks dependency health, reuses unchanged stages and prepares pinned public knowledge resources and one index. See [INSTALLATION.md](INSTALLATION.md) for the authoritative setup, updates, platform prerequisites and optional test tools. Do not duplicate environments, launchers or machine-local credentials.

Source development uses Electron. Do not add a standalone browser launcher or expose the private loopback backend as a network service.

## Before opening a pull request

Run the complete local gates:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
pnpm --dir desktop test
.venv/bin/python scripts/sync_requirements.py --check
git diff --check
```

Live Bedrock and licensed Sentaurus tests are opt-in. State clearly when a change needs infrastructure that was not available locally.

Also run `.venv/bin/mypy --strict src` and report its outcome. The current source baseline has existing errors in scientific/runtime modules. Do not hide them, introduce new ones or present that audit as an installation prerequisite. Keep this distinct from the passing runtime test gates above.

## Pull-request expectations

- Explain the researcher problem and the exact behavior change.
- Include the failing test that established the defect or requirement.
- Report every verification command and result.
- Identify scientific assumptions, capability changes, and compatibility effects.
- Include screenshots for visible desktop changes.
- Keep unrelated formatting and refactoring out of the change.
- Update public documentation when installation, capabilities, limitations, or release behavior changes.

A pull request must not weaken validation to make a simulation pass. New scientific scope needs schema, capability, adapter, normalization, validation, and conformance coverage.

## Dependency changes

Edit constraints in `pyproject.toml`, then regenerate `requirements.txt` and `requirements.lock` on the supported Linux and Python 3.13 environment:

```bash
.venv/bin/python scripts/sync_requirements.py
```

Never edit generated requirement files by hand. Desktop packages must remain locked in `desktop/pnpm-lock.yaml`.

## Security reports

Do not disclose vulnerabilities, credentials, proprietary simulator content, or sensitive research data in a public issue. Follow [SECURITY.md](SECURITY.md).
