# Agent Kronig Desktop Application

Agent Kronig Desktop is the only supported interactive application for researchers. It presents the repository, agent, activity, changes, file viewer, and TCAD workflow in a native window. No browser is required, and the application does not expose a network service to other machines.

The desktop application is built for Linux first and is also packaged for Windows, Intel Mac, and Apple Silicon. Each release contains the user interface, private local backend, reviewed Python runtime, and fixed DEVSIM runner. A researcher does not need to install Python, Node.js, pnpm, Electron, DEVSIM, or a browser.

## Choose the correct installer

| System | Artifact | Installation |
| --- | --- | --- |
| Linux workstation | Linux AppImage | Mark the file executable and open it. No root access is required. |
| Debian or Ubuntu | `.deb` package | Install with the system software center or `sudo apt install ./Agent-Kronig-*.deb`. |
| Windows 10 or 11 | Windows installer | Run the NSIS `.exe`, choose the destination if needed, then launch Agent Kronig from the Start menu. A portable `.zip` is also produced. |
| Intel Mac | x64 `.dmg` | Open the disk image and drag Agent Kronig into Applications. |
| Apple Silicon | arm64 `.dmg` | Open the disk image and drag Agent Kronig into Applications. |

Install only an artifact produced by the project release workflow and verify it against the release checksum manifest. Alpha 12 packages are unsigned, so Windows SmartScreen and macOS Gatekeeper can warn before opening them. Signing and notarization are required before broader distribution.

## First launch

1. Start Agent Kronig from the operating system application launcher.
2. The application starts a private backend on an operating-system-selected `127.0.0.1` port. The port is not exposed to other machines.
3. Select `Open folder`. The native operating-system folder dialog appears.
4. Choose a local repository. Agent Kronig operates directly on those files. It does not copy the repository to a remote service.
5. Send a task in Chat. The temporary workspace session is created automatically, and repository edits appear on disk and in the file tree.

Only one Agent Kronig window can own its local application data at a time. Starting a second copy brings the existing window forward. A repository remains ordinary local data and can be opened with other tools when Agent Kronig is not writing to it.

## Configuration and credentials

Open `Settings` in the application header to configure the AWS region, Bedrock model identifier, reasoning effort, and Bedrock API key. Saving settings restarts only the private local service and returns to the workspace. The API key is encrypted with the operating system's protected credential storage and is never returned to the renderer after saving. On Linux without a working secret service, the key stays only in memory for the current application session and must be entered again after restart.

Development runs also load the repository's ignored `.env` through `scripts/run_desktop_dev.sh`. A managed deployment may inject configuration through its approved launch environment.

At minimum, online agent operation needs a valid Bedrock credential, region, and model identifier. No credentials, `.env` files, private keys, proprietary Sentaurus material, or licensed examples are included in installers. The release workflow inventories every artifact and rejects application-owned credential material.

The packaged DEVSIM runner is fixed and reviewed. It accepts a compiler-produced job manifest, verifies paths and hashes, and does not execute arbitrary shell text. Sentaurus is not bundled. Licensed Sentaurus execution remains a separate restricted integration and must stay disabled until its host, exact simulator release, extractor, signing, quotas, and conformance tests are approved.

## Local data and session lifecycle

Agent Kronig keeps settings, protected credentials, update configuration, and startup logs in the normal per-user application-data directory:

| System | Default application-data location |
| --- | --- |
| Linux | `~/.local/share/Agent Kronig` |
| Windows | `%APPDATA%\Agent Kronig` |
| macOS | `~/Library/Application Support/Agent Kronig` |

Agent chat, run state, approvals, activity events, and OpenHands runtime state are not durable user data. Every launch creates a locked process-scoped directory under `sessions/`. Closing the application cancels active agent work, denies pending approvals, and removes that directory. Opening another repository after the current run finishes also clears the current session. After a crash, the next launch removes any stale session directory before opening a workspace.

Repositories are never stored inside the application-data directory unless the researcher explicitly selected a repository there. Readable experiment plans, reports and result links appear in the selected repository; immutable simulator internals and protected bundle data can live in application data. Preserve both locations when backing up research evidence. Backing up application data does not preserve or restore chat history. Copy persistent data only while Agent Kronig is closed so its remaining SQLite files are consistent.

Startup failures are shown in a small recovery window with Retry and Quit actions. The diagnostic log contains bounded, sanitized backend output and removes values labelled as tokens, passwords, secrets, and API keys. The exact log directory follows the operating system's Electron log location.

## Updates

Alpha 12 uses manual updates and does not publish automatic update metadata. Managed updates remain disabled unless a future release administrator supplies an HTTPS feed through `AGENT_KRONIG_UPDATE_URL`. `AGENT_KRONIG_UPDATE_CHANNEL` accepts `stable` or `pilot`; it defaults to `stable`.

Agent Kronig can check for and download an update while idle. It will not install or restart while an agent run or simulation is active. The researcher must finish, pause, or stop active work before applying a downloaded update. If no valid HTTPS feed is configured, update controls report that managed updates are unavailable and the installed application continues to work.

Before managed updates or wider distribution are enabled, release administrators must sign Windows and macOS installers. macOS releases also require notarization. Linux updates require the detached Ed25519 signature generated by the release workflow and verified against the public key pinned inside Agent Kronig. Update metadata, signatures, and packages must be served over HTTPS from infrastructure controlled by NovAtom Labs.

## Native-only interface

Source development and installed releases both use the Electron application. The private loopback backend and embedded HTML renderer are internal implementation details and are not exposed through a standalone browser launcher. A graphical desktop session is required for the interactive workspace. Headless machines can use deterministic validation, compilation, execution, and reporting commands, but they do not host the Agent Kronig workspace interface.

## Supported developer launch

Follow [INSTALLATION.md](../../INSTALLATION.md) for the authoritative current-source setup. Developers need Python 3.13, Node.js 24, pnpm 11.19, Git and a graphical session. From the repository root on macOS or Linux:

```bash
python3.13 scripts/bootstrap_dev.py
./scripts/run_desktop_dev.sh
```

On macOS, the tracked **Launch Agent Kronig Dev.command** shortcut can be double-clicked or launched with `./"Launch Agent Kronig Dev.command"`. On Windows PowerShell, run `py -3.13 scripts\bootstrap_dev.py` followed by `.\scripts\run_desktop_dev.ps1`. Bootstrap prepares isolated application and simulator environments, desktop dependencies, pinned public knowledge sources and one generated index. Healthy unchanged stages are reused. No browser, folder-picker helper or installer rebuild is required.

Published Alpha 12 packages are older release snapshots, not copies of current `main`. Pulling source and using its shortcut updates the development app only; it does not update an installed DMG, AppImage or Windows package.

Both wrappers delegate to `scripts/run_desktop_dev.py`. It loads an ignored `.env` without evaluating shell code or printing values, assigns a desktop-specific workspace when `TCAD_WORKSPACE` is unset, and starts Electron. The private backend is supervised by Electron and is stopped when the application exits.

## Build release artifacts

Release builds are target-native. Linux artifacts are built on Linux, Windows artifacts on Windows, Intel Mac artifacts on Intel macOS, and Apple Silicon artifacts on Apple Silicon macOS. A build machine needs Python 3.13, PyInstaller 6.16.0, DEVSIM 2.9.1, Node.js 24, pnpm 11.19, and the project dependencies.

```bash
.venv/bin/python scripts/rebuild_knowledge_index.py --project-root . --fetch-sources --if-stale
.venv/bin/python scripts/build_desktop_sidecars.py
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop test
pnpm --dir desktop run pack:app
pnpm --dir desktop dist
.venv/bin/python scripts/inspect_desktop_artifacts.py desktop/dist
```

The packaged scientific and agent runtime is intentionally substantial. First launch can take up to two minutes on slower machines while the private backend initializes. Later launches usually benefit from operating-system file caching.

The GitHub release workflow builds every supported target and uploads platform-specific artifacts. Signing secrets belong only in the release system. They must not be written to the repository or a developer `.env`.

## Recovery and uninstall

If the application does not start:

1. Close any existing Agent Kronig process.
2. Start it again and use Retry if the recovery window appears.
3. Inspect the sanitized startup log shown in that window.
4. Confirm that security software has not quarantined a signed sidecar.
5. Preserve the application-data directory before attempting repair if settings or protected credentials are needed.

Uninstall the application through the operating system package manager or by removing the application bundle. Uninstallation does not delete a selected repository or artifacts stored inside it. It also does not automatically delete persistent per-user settings and credentials. Agent chat and activity cannot be restored across launches or reinstallations because they are intentionally ephemeral. Remove the application-data directory separately only when its persistent contents are no longer needed and a backup has been taken.
