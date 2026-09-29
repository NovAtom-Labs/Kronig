<p align="center">
  <img src="desktop/assets/icon.svg" width="112" alt="Agent Kronig logo">
</p>

<h1 align="center">Agent Kronig</h1>

<p align="center">
  A native scientific workspace for agentic TCAD research, repository work, simulation, validation, and reproducible evidence.
</p>

<p align="center">
  <a href="https://github.com/NovAtom-Labs/Quiloo/releases/tag/v0.1.0-alpha.12">Alpha release</a>
  · <a href="INSTALLATION.md">Installation</a>
  · <a href="docs/architecture.md">Architecture</a>
  · <a href="docs/operations/desktop-application.md">Desktop operations</a>
</p>

> **Alpha software:** Agent Kronig 0.1.0 Alpha 12 is an early research pilot. Packages are currently unsigned, updates are manual, and scientific output must be reviewed by a qualified researcher before it informs device, process, or fabrication decisions.

## Download the native application

Agent Kronig is a self-contained Native desktop application. A release includes the private local backend, the repository agent, and the reviewed DEVSIM runtime. End users do not need Python, Node.js, Electron, DEVSIM, or a browser.

| Platform | Installer | Portable package |
| --- | --- | --- |
| Linux x86-64 | [AppImage](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-linux-x64.AppImage) or [Debian package](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-linux-x64.deb) | AppImage is self-contained |
| Windows x86-64 | [NSIS installer](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-win-x64.exe) | [ZIP](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-win-x64.zip) |
| Intel Mac | [DMG](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-x64.dmg) | [ZIP](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-x64.zip) |
| Apple Silicon | [DMG](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-arm64.dmg) | [ZIP](https://github.com/NovAtom-Labs/Quiloo/releases/download/v0.1.0-alpha.12/Agent-Kronig-0.1.0-alpha.12-mac-arm64.zip) |

Verify a download against `SHA256SUMS.txt` from the same release. See the [installation guide](INSTALLATION.md) for platform instructions and unsigned-package warnings.

## What Agent Kronig does

Agent Kronig combines an agentic repository IDE with a constrained scientific execution system:

- Opens a local Git or non-Git repository and edits its real files.
- Creates one temporary agent session for the open repository and clears its chat, run, approval, and activity state when the application exits or another repository is opened.
- Reads, previews, and safely edits code, text, Markdown, JSON, CSV, TSV, images, and PDFs.
- Runs allowlisted repository commands and deterministic validation inside the selected workspace.
- Delegates bounded analysis or review to registered specialist agents while one primary agent owns the final write sequence.
- Converts research intent into a strict, simulator-neutral `ExperimentSpec`.
- Checks a backend capability manifest before generating any simulator input.
- Compiles supported DEVSIM and Sentaurus jobs through deterministic adapters.
- Normalizes simulator output into canonical result fields and validates numerical evidence.
- Builds an evidence summary for every run and creates a separate narrative report only when the research task calls for one.
- Retrieves reviewed TCAD context from pinned DEVSIM documentation, source, examples, and portable physics guidance with source metadata and citations.
- Escalates to bounded public web research only when local evidence is missing, stale, conflicting, or insufficient, with run-scoped network approval and hashed source records.

The selected repository is the default authority boundary. Repository-local reads, edits, tests, and validation are allowed by policy. External paths, network activity, package installation, destructive commands, Git mutation, and remote mutation require an explicit approval. Category approval applies only to the current run.

## Research workflow

```text
Research request
      |
      v
Bounded repository context and local TCAD evidence
      |
      v
Intent preparation and consequential questions, when needed
      |
      v
Deterministic compiled agent request
      |
      v
Simulator-neutral ExperimentSpec
      |
      v
Schema, semantic, and backend capability checks
      |
      v
Researcher plan review and approval
      |
      v
Deterministic DEVSIM or Sentaurus adapter
      |
      v
Bounded simulator runner
      |
      v
Canonical result and mandatory validation
      |
      v
Evidence summary, hashes, provenance, and run bundle
```

The language model interprets intent and operates tools. It is not the authority for units, simulator syntax, supported physics, or numerical acceptance. Schemas, capability manifests, adapters, runners, and validators own those decisions.

### Intent preparation

Before an agent run begins, Agent Kronig prepares the research request with the same configured model that performs the work. The preparer receives the exact researcher message, a bounded inventory of the open repository, backend capabilities, and a small set of locally retrieved TCAD passages. It can either mark the request ready, ask a short batch of consequential questions in the chat, or block an unsupported request with a specific reason.

The researcher message is never rewritten in place. Answers are stored separately and a deterministic compiler produces a canonical JSON request with source labels and SHA-256 hashes. Geometry, materials, doping, contacts, applied conditions, study bounds, fixed parameters, and requested deliverables must come from the researcher. Local evidence may guide expert choices such as physics models, meshing, numerics, solver recovery, diagnostics, and validation, but it cannot fill in missing research intent. Operational defaults may select presentation and canonical output details only.

Question count is adaptive rather than fixed. The normal target is three to five questions and the hard limit is seven. Complete requests proceed without ceremonial questions. If local evidence is insufficient, the compiled request can authorize the execution agent to request bounded web research through the existing network approval policy.

## Current capabilities

| Area | Alpha capability |
| --- | --- |
| Workspace | Native three-pane repository, file, chat, activity, and changes interface |
| Agent runtime | Process-scoped OpenHands execution, repository file tools, bounded terminal commands, tasks, approvals, and delegated agents |
| Intent preparation | Same-model structured preparation, bounded repository and TCAD context, adaptive clarification, deterministic compilation, and provenance hashes |
| Scientific contract | Strict simulator-neutral `ExperimentSpec` with dimensional quantities, typed axes and datasets, and unknown-field rejection |
| Geometry | Up to 32 ordered, contiguous silicon, silicon-dioxide, or researcher-parameterized dielectric regions with bounded mesh controls and automatic profile landmarks |
| Profiles | Constant, piecewise, linear, Gaussian, error-function, and tabulated donor or acceptor profiles plus fixed bulk charge |
| Interfaces | Explicit material interfaces, electrostatic continuity, mesh refinement, and fixed interface charge |
| Physics | Poisson and drift diffusion, Boltzmann statistics, constant or Klaassen mobility, high-field saturation, SRH, Auger, Slotboom band-gap narrowing, and canonical band energies |
| Studies | Equilibrium, exact or ranged DC, adaptive recovery, quasi-static C-V, small-signal AC, frequency, transient step, ramp, or pulse, temperature, and registered parameter studies |
| DEVSIM | Local deterministic compilation, execution, normalization, validation, reporting, and evidence bundles |
| Sentaurus | Deterministic command compilation, source maps, signed remote protocol, canonical result contract, and conformance rules |
| Knowledge | Manifest-gated retrieval over pinned official DEVSIM documentation and source plus source-grounded portable TCAD guides, with review state, backend/version filters, hashes, and citations |
| Results | Dataset-driven metrics, curves, indexed profile families, heatmaps, complex-response views, compatible overlays, linear, log, and signed-log scales, operating points, validation, provenance, zoom, pan, crosshair inspection, contact and interface markers, and CSV, SVG, or PNG export |
| Provenance | Source versions, hashes, compiler identity, simulator identity, validation records, and atomic bundle manifests |

### Backend boundary

| Capability | DEVSIM pilot | Sentaurus adapter |
| --- | --- | --- |
| Execution | Local and packaged | Disabled until a licensed host passes integration checks |
| Dimension | 1D | 1D |
| Material | Silicon, silicon dioxide, and generic dielectric with explicit permittivity | Silicon |
| Regions | Up to 32 ordered regions | Up to 32 ordered regions |
| Contacts | Semiconductor ohmic, dielectric ideal-gate or work-function boundaries, insulating boundaries, offsets, and optional area | Endpoint ohmic or explicit metal work-function contacts |
| Statistics | Boltzmann | Boltzmann or Fermi |
| Mobility | Constant, Klaassen, and reviewed one-dimensional high-field saturation | Constant and reviewed Sentaurus mappings |
| Recombination | SRH and Auger | SRH and Auger |
| Band-gap narrowing | Reviewed Slotboom implementation | Supported by the adapter contract |
| Studies | Equilibrium, DC, charge or C-V, AC or frequency, transient step, ramp, or pulse, temperature, and registered parameters, with a 10,000-point resource limit | Equilibrium and DC sweep, up to 10 points |

Unsupported physics is refused. It is never silently approximated or removed from the research request.

### Adaptive scientific research

The repository agent follows a local-first evidence loop. It searches the packaged,
versioned corpus before consulting the public web. If a claim still needs support, it
can search for official documentation or primary literature after one network approval
for the active run, fetch a bounded HTTPS text source, and retain the URL, title,
retrieval time, authority class, backend, version, and SHA-256 content hash.

Search snippets are discovery aids, not evidence. Retrieved pages are treated as
untrusted data and cannot override product policy, request credentials, or issue tool
instructions. Private network targets, non-HTTPS URLs, nonstandard ports, unsupported
content types, oversized responses, and unsafe redirects are refused. Evidence guides
the agent's compile, run, inspect, repair, and validate loop, but deterministic schema,
capability, simulator, and validation checks remain authoritative.

The model must ask for scientifically essential missing intent. It may choose bounded
numerical implementation details, but it must not invent geometry, doping, materials,
contact behavior, temperature, or sweep endpoints from typical values.

## Known limitations

This alpha is for workflow evaluation and small exploratory drift-diffusion studies. It is not a calibrated fabrication prediction system.

- One spatial dimension, silicon and silicon dioxide, reviewed analytic profile primitives, and endpoint contacts.
- No arbitrary model-written simulator syntax.
- No process simulation, noise, optical, thermal, mechanical, quantum, hydrodynamic, ballistic, or arbitrary circuit co-simulation.
- No automated calibration against fabrication measurements.
- Direct metal-semiconductor Schottky transport and coupled Fermi-Dirac drift diffusion remain disabled research gates. Metal work function is supported only as a reviewed electrostatic boundary on dielectric contacts.
- Philips-style surface mobility is outside the one-dimensional adapter because the pinned DEVSIM implementation requires two-dimensional element fields. Surface recombination, interface traps, spatial temperature profiles, coupled Fermi transport, and direct Schottky transport remain evidence-backed research gates.
- Parameter studies are restricted to the registered model-parameter paths. Arbitrary runtime paths and arbitrary material values are rejected.
- DC sweeps retain every requested terminal operating point plus bias-indexed spatial profiles. Failed solves remain explicit and are masked as gaps in the scientific viewer.
- Licensed Sentaurus execution remains unavailable until a separate host, exact simulator version, extractor, signing keys, quotas, and conformance cases are configured and verified.
- Windows and macOS can warn about unsigned alpha packages.
- Updates are manual for this alpha.
- Repository commands run as the current operating-system user. The alpha does not provide a VM or per-researcher OS sandbox.
- Agent chat and activity are intentionally ephemeral. Repository files and generated artifacts persist, but reopening a repository starts a clean agent session without cross-session repository memory.

Adding a new material, model, profile, contact, study, or observable requires a schema decision, capability declaration, deterministic adapter mapping, normalization, validation, and tests. A new structure that already fits the portable concepts should require only data, not a named product path.

## Architecture

The stable product boundary is the experiment and evidence workflow. DEVSIM and Sentaurus are replaceable backends.

| Layer | Responsibility |
| --- | --- |
| `domain` | `ExperimentSpec`, units, geometry, profiles, contacts, physics, studies, and requested observables |
| `capabilities` | Exact backend support, resource limits, refusal reasons, and execution availability |
| `experiments` | Stable preparation digests and the single compile, run, normalize, validate, and bundle sequence |
| `knowledge` | Authorized ingestion, retrieval, review metadata, and citations |
| `adapters` | Deterministic simulator input generation and native result normalization |
| `runners` | Bounded local execution and signed licensed-host submission |
| `validation` | Numerical, physical, conservation, provenance, and completeness checks |
| `bundles` | Atomic reports, manifests, artifacts, and SHA-256 hashes |
| `agent` | OpenHands tools, repository policy, normalized events, and bounded delegation |
| `ide` | Workspaces, temporary sessions, runs, approvals, messages, activity, and changes |
| `desktop` | Electron-owned native window, authenticated private loopback backend, and packaged sidecars |

The runtime always loads Agent Kronig's built-in scientific skills and packaged knowledge index, even when the researcher opens an empty repository. Repository-local skills may add laboratory conventions but cannot replace built-in product policy. The skills guide scientific decisions and route detailed questions into retrieval instead of trying to place an entire simulator manual in the model prompt.

Every controlled TCAD bundle contains `report.md` as a compact evidence summary. It is an audit artifact, not an unsolicited research paper. A separate narrative report is produced only when requested or when durable comparative analysis is the stated deliverable.

### Scientific results in the workspace

Completed experiment bundles open in the center pane as a Results Workbench. Selecting a repository artifact whose path ends in `results/canonical.json` shows structure, canonical metrics, interactive one-dimensional fields, operating points, validation evidence, and manifest provenance. The underlying JSON remains available through the Evidence view.

When a foreground agent run creates or modifies a canonical result, Agent Kronig finds it through that run's immutable Changes manifest and opens the workbench automatically. Ordinary JSON files continue to use the generic file viewer.

The workbench reads only verified `ExperimentSpec`, `CanonicalResult`, `ValidationReport`, and `BundleManifest` artifacts. DEVSIM and Sentaurus therefore share the same interface after their adapters normalize native results. It discovers scalar metrics, curves, profile families, heatmaps, and complex responses from canonical axes, shape, unit, and centering. Direct TDR or PLT extraction remains a responsibility of the Sentaurus exporter and canonical schema, not the UI.

Every simulator adapter implements the same conceptual boundary:

```python
manifest -> CapabilityManifest
compile(spec, workspace) -> CompiledJob
normalize(native_run) -> CanonicalResult
```

Read the [architecture document](docs/architecture.md) for the full contract and [desktop operations guide](docs/operations/desktop-application.md) for data locations, recovery, and packaging.

## Develop from source

Source development uses the same native Electron application as an installed release. There is no supported standalone browser interface.

Prerequisites are Python 3.13, Node.js 24, pnpm 11.19, Git, and a graphical desktop session. Then:

```bash
git clone git@github.com:NovAtom-Labs/Quiloo.git
cd Quiloo
python3.13 scripts/bootstrap_dev.py
scripts/run_desktop_dev.sh
```

On Windows, replace the last two commands with `py -3.13 scripts\bootstrap_dev.py` and `.\scripts\run_desktop_dev.ps1`. The bootstrap creates isolated application and DEVSIM environments, installs desktop dependencies, and caches dependency fingerprints so unchanged reruns finish quickly. Configure Bedrock through Settings after launch.

The launcher loads an ignored local `.env` when present, starts Electron, and lets Electron supervise the authenticated private backend. Credentials, proprietary Sentaurus material, private signing keys, and licensed examples must never be committed.

For the full setup, DEVSIM environment, Bedrock configuration, validation, and test-workspace procedure, follow [INSTALLATION.md](INSTALLATION.md).

## Verify a checkout

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
.venv/bin/mypy --strict src
pnpm --dir desktop test
.venv/bin/python scripts/sync_requirements.py --check
git diff --check
```

Live Bedrock and licensed Sentaurus tests are opt-in. Ordinary local verification does not require either service.

The synthetic scientific suite exercises complete, incomplete, ambiguous, contradictory,
and unsupported natural researcher prompts. Real DEVSIM coverage spans mixed silicon and oxide
compositions, analytic profiles, equilibrium, exact and adaptive DC, terminal charge,
quasi-static capacitance, AC and frequency response, transient schedules, temperature and
registered parameter studies, immutable provenance, deterministic validation, and graphable
canonical datasets:

```bash
.venv/bin/pytest -q \
  tests/unit/evaluations/test_scientific_cases.py \
  tests/integration/test_scientific_research_workbench.py
```

Live Bedrock behavior tests are intentionally opt-in because they incur API cost. The unified suite
checks a real DEVSIM run, unsupported-physics refusal, and an ordinary repository edit through the
same desktop agent runtime:

```bash
set -a && source .env && set +a
.venv/bin/pytest -q \
  tests/e2e/test_live_unified_backend.py \
  tests/e2e/test_live_expanded_devsim.py \
  --run-live-bedrock
```

## Project documents

- [Installation and source setup](INSTALLATION.md)
- [Desktop application operations](docs/operations/desktop-application.md)
- [Architecture and scientific contracts](docs/architecture.md)
- [DEVSIM operations](docs/operations/devsim.md)
- [Sentaurus integration](docs/operations/sentaurus-integration.md)
- [Pilot acceptance testing](docs/testing/pilot-acceptance.md)
- [Alpha 12 release notes](docs/releases/v0.1.0-alpha.12.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## License

This project is licensed under the [Apache License 2.0](LICENSE). Third-party simulators, models, services, data, and documentation retain their own licenses and access restrictions.
