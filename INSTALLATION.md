# Agent Kronig Installation and Setup

Use the source setup below to develop or run the current `main`. Published installers are fixed release snapshots, not live copies of this repository. The existing Alpha 12 installers predate the latest source fixes and are not rebuilt by these steps.

The interface is a native Electron application on Linux, macOS and Windows. A graphical desktop is required, but a browser is not. Sentaurus and its license are not installed or supplied by this setup.

## 1. Install prerequisites once

| Requirement | Version or purpose |
| --- | --- |
| Python | CPython 3.13.x, including `venv` and pip |
| Node.js | 24.x |
| pnpm | 11.19.x, matching `desktop/package.json` |
| Git | Clone and retrieve pinned public knowledge sources |
| Network | Python/npm packages and the public DEVSIM source repositories |
| Graphical session | Required to open Electron, including on Linux workstations |

Install prerequisites through your approved operating-system package manager or official installers. With Node available, `npm install --global pnpm@11.19.0` installs the pinned package manager. The bootstrap does not install operating-system packages or request administrator privileges.

- Linux: install OpenBLAS and the libraries needed by Electron for your distribution. Debian/Ubuntu package names include `libopenblas-dev`, `libgtk-3-0`, `libnss3`, `libgbm1` and `libasound2` or its distribution-specific replacement. Python may require `python3.13-venv`. A C/C++ toolchain is useful if a dependency needs a source build. `tmux` is recommended for agent terminal sessions. No `zenity`, `kdialog` or browser is required for the Electron folder picker.
- macOS: install a native Python 3.13 and Node 24 for your CPU architecture. Avoid mixing Intel and Apple Silicon environments. Command Line Tools may be needed for source builds.
- Windows: use Python 3.13 and Node 24 x64. The bootstrap installs DEVSIM's pinned MKL runtime into its isolated simulator environment; the launcher supplies its library path. A managed workstation may restrict PowerShell scripts. Follow your organization's policy rather than disabling security controls globally.

Check `git --version`, `node --version` and `pnpm --version`. Python should report 3.13.x through `python3.13 --version` on macOS/Linux or `py -3.13 --version` on Windows.

### Dependency ownership by operating system

| Layer | Linux | Windows | macOS | Source of truth |
| --- | --- | --- | --- | --- |
| Application Python packages | Shared pins | Shared pins plus required platform transitives | Shared pins plus required platform transitives | `pyproject.toml`, generated `requirements.txt` and `requirements.lock` |
| Simulator Python packages | DEVSIM and NumPy | DEVSIM, NumPy and pinned MKL | DEVSIM and NumPy | `requirements/devsim.txt`, with a Windows environment marker; NumPy uses the shared constraint |
| Simulator native math | System OpenBLAS | MKL DLL inside simulator environment | Native macOS math runtime | OS prerequisites; Windows MKL installed by bootstrap |
| Desktop packages | Native Electron binary | Native Electron executable | Native Electron application | `desktop/package.json` and `desktop/pnpm-lock.yaml` |
| Agent terminal | Bash; tmux recommended | PowerShell available on PATH | Bash; tmux recommended | Pinned OpenHands native terminal backend |
| Developer tools | Python 3.13, Node 24, pnpm 11.19, Git | Same, native x64 installs | Same, matching CPU architecture | Version checks in bootstrap |

Do not install the simulator requirements into the application environment. Do not make a full hand-maintained requirements copy for each OS. The bootstrap applies the platform marker automatically and uses two intentionally separate Python environments. The Linux lock constrains shared packages on every OS; Windows/macOS-only transitives are resolved on their native platform, not claimed to be an identical Linux environment.

### Linux workstation prerequisites

The native source-setup verification target is **Ubuntu 24.04 x64**. After obtaining Python 3.13, Node 24 and pnpm 11.19 from an approved source:

```bash
sudo apt-get update
sudo apt-get install -y git build-essential libopenblas-dev libgtk-3-0t64 libnss3 libgbm1 libasound2t64 tmux
```

Python 3.13 is not provided by every Ubuntu package source. If your approved Python distribution already supplies pip/venv, do not install a second Python just to satisfy that package name. Distribution package names vary. Older RHEL/Rocky/CentOS HPC hosts are not certified by the Ubuntu job: verify their C library, desktop libraries and available Python/Node versions rather than treating all Linux distributions as equivalent. A machine without a graphical session cannot display the workspace. CI uses a virtual display only for automated qualification where needed.

Use the OpenBLAS development package here because reviewed DEVSIM 2.9.1 probes the unversioned `libopenblas.so` name. A runtime-only `.so.0` package can leave that loader name unavailable even though OpenBLAS is installed.

### Windows workstation prerequisites

Use native x64 Python 3.13, Node 24 and Git for Windows. The source job runs on **Windows Server 2025 x64**, while researchers should use a graphical Windows workstation. The code does not require WSL, Linux OpenBLAS packages or a separately installed browser. Install pnpm from PowerShell after Node installation:

```powershell
npm install --global pnpm@11.19.0
py -3.13 --version
node --version
pnpm.cmd --version
git --version
```

Keep Linux and Windows checkouts/environments separate when also using WSL. Do not reuse a WSL `.venv` or `node_modules` from native Windows. On policy-managed machines, use an approved PowerShell policy. If `.ps1` execution is restricted, the equivalent native launch after setup is `.\.venv\Scripts\python.exe .\scripts\run_desktop_dev.py`; it does not require changing the policy.

The pinned agent SDK selects a native PowerShell terminal on Windows, so PowerShell must remain available on PATH even when you launch through Python. It does not require WSL or Git Bash. Linux and macOS use the Unix terminal backend, with tmux recommended and a subprocess fallback when tmux is absent.

## 2. Clone and prepare

macOS or Linux:

```bash
git clone https://github.com/NovAtom-Labs/Kronig.git
cd Kronig
python3.13 scripts/bootstrap_dev.py
```

Windows PowerShell:

```powershell
git clone https://github.com/NovAtom-Labs/Kronig.git
cd Kronig
py -3.13 scripts\bootstrap_dev.py
```

The public HTTPS URL needs no SSH-key setup. If you already have authorized GitHub SSH access, `git clone git@github.com:NovAtom-Labs/Kronig.git` is an alternative. Use your own authorized account if the repository is private. Never put a personal access token in the URL or a tracked file.

One bootstrap command prepares:

| Location | Contents |
| --- | --- |
| `Kronig/.venv` | Editable application and pinned Python dependencies |
| `devsim/.venv`, beside `Kronig` | DEVSIM 2.9.1, matching NumPy and Windows MKL when needed |
| `Kronig/desktop/node_modules` | Locked desktop dependencies and the actual Electron executable |
| `devsim/source` and `devsim/documentation` | Shallow public checkouts at the reviewed commits in the source manifest |
| `Kronig/knowledge-sources/index/knowledge.sqlite3` | One generated index of repository guides and pinned public resources |
| `Kronig/.tcad-agent-dev/bootstrap.json` | Small, credential-free setup receipt |

The two Python environments are intentional: simulator and application dependencies stay isolated. Setup does not create a new environment for each launch or build release installers. It does not copy credentials, research runs or this machine's caches.

Repeated bootstrap checks dependency fingerprints and Python package identities, reuses healthy stages and leaves an unchanged knowledge index untouched. A changed lockfile invalidates the relevant stage. `--force` reinstalls dependency stages in place; it does not delete your repository, settings or research outputs. Pinned public source checkouts are verified and never reset over local modifications.

`pyproject.toml` owns dependency constraints. `requirements.txt` contains generated direct pins; `requirements.lock` contains the generated complete Linux/Python 3.13 resolution. Setup installs the direct list constrained by the full lock. OS-specific dependencies still differ across platforms. Do not hand-edit either generated file or refresh the Linux lock on macOS.

## 3. Launch the current development application

Run from the checkout, or use the macOS shortcut directly:

| System | Launch command |
| --- | --- |
| macOS | `./"Launch Agent Kronig Dev.command"` |
| Linux | `./scripts/run_desktop_dev.sh` |
| Windows PowerShell | `.\scripts\run_desktop_dev.ps1` |

On macOS you can also double-click **Launch Agent Kronig Dev.command** in Finder. It is already tracked and executable. `./scripts/run_desktop_dev.sh` is an equivalent macOS terminal launch. No virtual-environment activation is needed. The shortcut resolves its own location, so spaces in the path and a different starting directory are supported.

Launching an older installed application from the Dock or Start menu still opens that installed snapshot. Use the source shortcut above for current development changes. Routine Python/renderer edits need an app restart, not a new installer. Desktop dependency changes need bootstrap again.

Electron owns an authenticated private loopback backend and stops its owned processes on exit. There is no supported standalone browser launcher. Chat, approvals and agent runtime state are temporary for the app session; reopening a repository does not restore an old agent run. Repository files, result bundles, settings and protected credentials persist.

## 4. Configure your own model access

Open **Settings** in the application and supply your approved Bedrock key, region, model identifier and reasoning effort. Access depends on your account and region. A code checkout does not grant model access. Keys use the operating system's protected credential storage when available; on Linux without a secret service they remain in memory for that app session.

An ignored `.env` is optional for developer overrides. Copy `.env.example` only if you need it, then fill your own values. Blank `TCAD_DEVSIM_PYTHON` uses the sibling simulator environment automatically in the desktop launcher. Set an absolute executable path only for a deliberately different installation.

### Optional: run Sentaurus on an HPC over SSH

DEVSIM runs locally with no extra setup. To also run Sentaurus on an HPC you can reach over SSH (and a VPN such as Tailscale if needed), put the HPC address, your login and the Sentaurus release in `.env`, then run `tcad-agent sentaurus-check`. Nothing is installed on the HPC. The simple step-by-step guide is [Run Sentaurus from Kronig over SSH](docs/operations/sentaurus-ssh-setup.md). Both simulators stay available; name the one you want in a request, for example "use Sentaurus".

The desktop launcher and scientific CLI read dotenv configuration without executing shell code. Do not `source .env`. Do not copy another developer's `.env`, credentials or entire virtual environment. Never commit proprietary Sentaurus documentation, licensed examples or private signing keys. Rotate exposed credentials.

## 5. Check the installation

On macOS/Linux, this deterministic smoke run needs no model key:

```bash
.venv/bin/python -m pip check
.venv/bin/tcad-agent validate examples/pn-junction.yaml
.venv/bin/tcad-agent run examples/pn-junction.yaml --backend devsim --approve --output runs
.venv/bin/tcad-agent knowledge search "Schottky contact" --backend devsim --version 2.9.1
```

On Windows use `.\.venv\Scripts\python.exe` and `.\.venv\Scripts\tcad-agent.exe` in place of the Unix executables. For direct CLI simulator execution on Windows, supply the MKL library environment described in [DEVSIM operations](docs/operations/devsim.md); the desktop launcher configures it automatically.

A successful smoke run produces a completed evidence bundle with passed scientific validation. Numerical completion alone is not a validation pass. In the application, choose **Open folder**, select a disposable repository and ask the agent to inspect or edit a file. For a reproducible fixture, run `.venv/bin/python scripts/create_repl_test_repo.py` and open `test-workspaces/pn-junction-research`. Do not regenerate over research work you want to keep.

Developer checks are listed in [CONTRIBUTING.md](CONTRIBUTING.md). Live model tests are opt-in and incur API charges. Licensed Sentaurus tests need separate infrastructure. Strict mypy currently has existing errors in scientific/runtime modules; it is a reported audit, not an installation-success check.

### Native setup verification

After bootstrap, verify the installed runtimes and optionally prove that a second bootstrap reuses them:

```bash
# Linux or macOS
.venv/bin/python scripts/verify_source_setup.py --repeat-bootstrap --output output/source-setup/evidence.json
```

```powershell
# Windows
.\.venv\Scripts\python.exe scripts\verify_source_setup.py --repeat-bootstrap --output output\source-setup\evidence.json
```

The verifier needs no model credential. It checks dependency consistency, unchanged setup receipts/index, the actual platform Electron runtime, pinned public retrieval, a real DEVSIM result with passed scientific validation and artifact hashes, authenticated workspace rendering, and owned backend shutdown. Temporary simulation/data directories are removed afterward; selected research folders and existing app instances are untouched. The JSON records the OS, CPU architecture, application commit and observed results. Native runtime verification is not a claim of visual UI qualification.

The separate [Native source setup workflow](https://github.com/NovAtom-Labs/Kronig/actions/workflows/source-setup.yml) runs this same path in fresh Linux, Windows and macOS jobs, including a checkout path with spaces, then runs Python and desktop tests. Evidence is uploaded per OS. A failed or queued job is not a passed setup. It does not build installers, publish a release or use model/signing secrets. See the job linked to your commit for current native verification status.

Verified reference: source revision `8998e90` passed clean setup and all applicable native runtime, Python and desktop gates on **Windows 2025 x64, Ubuntu 24.04 x64 and macOS 15 Apple Silicon** in [this verification run](https://github.com/NovAtom-Labs/Kronig/actions/runs/40004493585). Windows also passed two repeated complete scheduled AC benchmarks. This identifies the tested source revision, not a newer installer release or certification of every OS version.

Browser-driven test tooling is optional and is not downloaded by bootstrap. To run those additional tests, install `pytest-xdist==3.8.0` and `playwright==1.63.0` into the application environment, then run `.venv/bin/python -m playwright install chromium`. This adds test-only packages and a browser cache. It is not required for the native application or ordinary serial tests.

## 6. Update a developer checkout

Close Agent Kronig first. Keep your own edits safe, then:

```bash
git pull --ff-only
python3.13 scripts/bootstrap_dev.py
```

On Windows use `py -3.13 scripts\bootstrap_dev.py`. Launch with the same shortcut from section 3. No uninstall/reinstall or release build is needed. Healthy dependency stages are reused. A collaborator must pull the same commit and rerun setup; credentials and OS-specific dependencies are their own.

## Troubleshooting and footprint

- Wrong or missing Python/Node/pnpm: fix the reported prerequisite first. Do not relax pins to bypass setup checks.
- Existing `.venv` made with another Python: preserve anything needed, move that exact environment aside deliberately, then bootstrap with Python 3.13. Do not delete the whole project or sibling directory.
- Modified or different-revision public source checkout: setup refuses to overwrite it. Preserve your changes and relocate the checkout deliberately before fetching a clean pin. Never reset someone else's source work as a setup shortcut.
- Electron missing after package installation: rerun bootstrap. It runs Electron's own installer when needed without enabling arbitrary dependency build scripts.
- Linux library error or missing graphical display: install the relevant distribution libraries and use a graphical desktop session. A browser installation is not the solution.
- Slow first setup: Python wheels, Electron and public source files must download once. Later unchanged setup reuses them. Pip/pnpm OS caches are normal; do not copy them into Git.
- Disk usage: `.venv`, `desktop/node_modules`, the isolated simulator, two shallow source checkouts and one index are expected. `desktop/dist`, release sidecars, old environments and research bundles are not required for routine source setup. Preserve existing user outputs rather than deleting them automatically.
- App startup/close failure: retain the sanitized recovery message and logs. See [desktop operations](docs/operations/desktop-application.md) for data locations and recovery. Rebuilding an installer is not a source-development repair step.

## Self-contained native installation

The [Alpha 12 release](https://github.com/NovAtom-Labs/Kronig/releases/tag/v0.1.0-alpha.12) provides Linux AppImage/deb, Windows installer/ZIP and Intel/Apple Silicon macOS DMG/ZIP packages. They contain their own private backend and DEVSIM runtime, so end users do not install Python, Node or a browser. Verify downloads against that release's `SHA256SUMS.txt`.

Alpha packages are unsigned and updates are manual. Use only official artifacts and follow your operating system's security policy. Install through the normal platform workflow, then configure your own Bedrock access in Settings. These packages are older snapshots: use the source workflow for current `main`. This setup change does not publish a new installer. Packaging, updates and uninstall instructions are in [desktop operations](docs/operations/desktop-application.md).
