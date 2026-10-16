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
- Resolves consequential scientific inputs into an auditable input ledger and refuses unresolved requirements before execution.
- Checks a backend capability manifest before generating any simulator input.
- Writes a deterministic `PLAN.md` and `plan.json`, pauses the same agent run for review, and resumes only the exact approved digest.
- Compiles supported DEVSIM and Sentaurus jobs through deterministic adapters.
- Normalizes simulator output into canonical result fields and validates numerical evidence.
- Stores immutable simulator internals in application data while projecting a readable experiment folder into the selected repository.
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

Plan approval is a product state, not a chat convention. `Approve and run`, `Run unattended`, and a contextual one-word `approved` all resolve the same pending plan record. A plan approval covers its local simulator execution for that run, so the same action is not requested again. Network, external-file, package, Git, remote, destructive, and system mutations remain outside unattended consent.

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
| Interfaces | Explicit material interfaces, electrostatic continuity, mesh refinement, fixed charge, surface SRH, and a single-level donor or acceptor trap |
| Physics | Poisson and drift diffusion, reviewed Boltzmann or Fermi transport, constant or Klaassen mobility, high-field saturation, bulk and surface SRH, Auger, Slotboom band-gap narrowing, Schottky thermionic boundaries, prescribed spatial temperature, current-component diagnostics, and canonical band energies |
| Studies | Equilibrium, exact or ranged DC, adaptive recovery, quasi-static C-V, small-signal AC, frequency, transient step, ramp, or pulse, temperature, and registered parameter studies |
| DEVSIM | Local deterministic compilation, execution, normalization, validation, reporting, and evidence bundles |
| Sentaurus | Deterministic command compilation, source maps, signed remote protocol, canonical result contract, and conformance rules |
| Knowledge | Manifest-gated retrieval over pinned official DEVSIM documentation and source plus source-grounded portable TCAD guides, with review state, backend/version filters, hashes, and citations |
| Results | Dataset-driven metrics, curves, indexed profile families, heatmaps, complex-response views, compatible overlays, linear, log, and signed-log scales, operating points, validation, provenance, zoom, pan, crosshair inspection, contact and interface markers, and CSV, SVG, or PNG export |
| Provenance | Source versions, hashes, compiler identity, simulator identity, validation records, and atomic bundle manifests |

### Scientific results integrity

Carrier-statistics selection considers the full operating range, not just bulk doping.
When Boltzmann statistics are explicitly requested, the choice is preserved, but solved
local `n/Nc` and `p/Nv` above the conservative nondegenerate limit of `0.1` fail the
applicability check. Fermi calculations retain their named approximation and source
provenance. Numerical convergence is not a claim of experimental accuracy.

`ExperimentSpec.display_units` records requested presentation units. Canonical results
and validation stay in SI; dimension-checked projections supply plot values, tooltips,
tables and viewer exports. Carrier-unit groups expand into separate electron and hole
fields. Incompatible units, unknown quantities and density-to-absolute conversions
without physical area are rejected before execution. Missing or failed samples are
shown as unavailable, not zero.

The DEVSIM adapter captures electrostatic and carrier diagnostic evidence even when
only terminal outputs were requested. Integrated charge is checked using native
Poisson control volumes, terminal displacement charge and recorded interface sources.
Contact boundary nodes are not counted twice. A separate mesh check compares identical
physical studies at half spacing, with material interfaces kept separate. Up to four
refinements share the execution budget. Original and refined specifications, native
results, compiled files and comparison metrics are preserved in the hashed bundle.
Budget exhaustion or an unstable comparison remains a failed check. A passing mesh
pair is a numerical error indicator, not proof of asymptotic convergence or calibration.

See the [statistics and evidence guidance](knowledge-sources/curated/scientific-results-integrity.md)
for definitions and limitations.

### Backend boundary

| Capability | DEVSIM pilot | Sentaurus adapter |
| --- | --- | --- |
| Execution | Local and packaged | Disabled until a licensed host passes integration checks |
| Dimension | 1D | 1D |
| Material | Silicon, silicon dioxide, and generic dielectric with explicit permittivity | Silicon |
| Regions | Up to 32 ordered regions | Up to 32 ordered regions |
| Contacts | Semiconductor ohmic, dielectric ideal-gate or work-function boundaries, reviewed silicon Schottky thermionic boundaries, insulating boundaries, offsets, optional area, and optional Richardson constants | Endpoint ohmic or explicit metal-work-function contacts |
| Statistics | Boltzmann and reviewed Fermi transport with statistics-consistent ohmic initialization and metal thermionic reservoirs in equilibrium/DC | Boltzmann or Fermi |
| Mobility | Constant, Klaassen, and reviewed one-dimensional high-field saturation | Constant and reviewed Sentaurus mappings |
| Recombination | Bulk SRH, Auger, surface SRH, and single-level charged interface traps | SRH and Auger |
| Band-gap narrowing | Reviewed Slotboom implementation | Supported by the adapter contract |
| Temperature | Scalar temperature, temperature studies, and prescribed constant, linear, piecewise-constant, or tabulated silicon profiles in the reviewed DC envelope | Scalar temperature |
| Studies | Equilibrium, DC, charge or C-V, AC or frequency, transient step, ramp, or pulse, temperature, and registered parameters, with a 10,000-point resource limit | Equilibrium and DC sweep, up to 10 points |

Unsupported physics is refused. It is never silently approximated or removed from the research request.

### Numerical execution and precision

`ExperimentSpec.solver.precision` is simulator-neutral: `backend_default`, `standard`, or
`extended`. DEVSIM currently resolves `backend_default` to extended model, equation,
and solver arithmetic. A native build without that support refuses the request before
meshing rather than silently falling back. Native and canonical results retain the
requested, resolved, and effective modes, all three native settings, build information,
and precision-policy version. Explicit non-default precision is currently refused by
the Sentaurus adapter until it has an implemented mapping.

Failed DC steps restore native copies of the last converged state and retry bounded
intermediate steps. Eligible stationary stacks with a driven dielectric boundary and
grounded ohmic silicon contacts use an equilibrium initial guess, then restore and solve
the full requested equations before extracting DC or AC results. Interface trap and
surface kinetics do not use that predictor. Numerical initialization does not substitute
for the carrier continuity equations, alter physical inputs, or relax validation limits.

Fixed reported DC points can use internal voltage continuation to construct a
convergent native starting state. The point list and order remain unchanged;
internal points are recorded as numerical initialization, not additional
reported measurements. The positive-density path retains original retry
allowances and final physical acceptance limits.

Biased carrier transport reports separate electron and hole quasi-Fermi levels.
A single Fermi-level request is refused when conducting reservoirs have different
voltages or the study is nonequilibrium, rather than presenting their average as a
physical Fermi level. Stationary dielectric gating with a common carrier reservoir
is distinguished by boundary semantics, not by device name.

The agent-facing quantity schema accepts explicit unit strings such as `4.1 eV` and
`0.1 V`; conversion is deterministic and work function remains an energy, not a voltage.
Compiled plans stay complete in repository artifacts and internal records. Conversational
tool responses reference those artifacts without copying large native meshes into the
model's context. Follow-up answers preserve unrelated confirmed physics and analyses.

See the [current Schottky/Fermi/Klaassen verification](docs/verification/2026-10-14-fermi-klaassen-convergence.md)
for convergence, approximation accuracy, live workflow timing and interactive-result
evidence. The [earlier researcher workflow report](docs/verification/2026-10-13-exact-researcher-workflows.md)
records historical behavior and the contact limitation that this work addressed.

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
- Fermi transport includes reviewed one-dimensional silicon ohmic and Schottky equilibrium/DC benchmarks. The ohmic high-doping reference remains `5e19 cm^-3`; this is a benchmark, not a blanket convergence guarantee. Fermi drift/diffusion decomposition is supported using the same native quasi-Fermi-gradient equations, including band-gap-narrowing gradients. Combined Fermi/Schottky AC, frequency and transient response remain refused.
- Silicon Schottky contacts use statistics-consistent Boltzmann or Fermi thermionic reservoirs with the actual local band gap, DOS and BGN reference. Benchmarks include both-metal equilibrium, current conservation, contact passivity, temperature variation and the original Al/p-Si/n-Si/Al study at `0,+2,-2 V`. Image-force lowering, tunneling and distributed contact states are not silently added.
- Agent-driven simulator execution has a bounded twenty-minute default budget shared by the original solve and mandatory mesh verification. An explicit caller timeout takes precedence and is recorded in execution provenance. The budget is a maximum, not a mandatory wait. A timeout or failed solve stays visible; it is not an accepted result.
- Surface physics supports surface SRH and one charged single-level donor or acceptor trap. Trap distributions, tunneling, frequency dispersion, and Philips-style surface mobility remain outside the reviewed one-dimensional boundary.
- Prescribed spatial temperature supports positive constant, linear, piecewise-constant, or tabulated silicon profiles with reviewed local material and transport terms under equilibrium or DC. It is not a heat-flow or self-heating solve, and unbenchmarked model and study combinations are refused.
- Boltzmann drift and diffusion components are continuum diagnostics compared with the native Scharfetter-Gummel current. Fermi components split the native quasi-Fermi-gradient current into electrostatic drift and thermodynamic diffusion, explicitly including band-gradient corrections. The reconciliation residual is calculated from actual currents; it is not a continuity-equation residual or independent proof of physical accuracy. Definitions and references are in [current decomposition guidance](knowledge-sources/curated/devsim-current-decomposition.md).
- Fermi density transport uses an adapter-owned matched Joyce-Dixon/Sommerfeld approximation, correcting native branch and derivative inconsistencies. Independent integral benchmarks show sampled density error below 0.22 percent and derivative error below 0.62 percent; this is not exact quadrature. DC solves use positive density coordinates and conservative matrix conditioning without dropping models or relaxing physical acceptance. The uniform `5 nm`, two-Schottky, Fermi/Klaassen/SRH `1 us`/Auger/Slotboom reference completed `-2,0,+2 V` in 238 seconds with all 12 applicable checks passed. Other meshes, doping and voltages still require their own convergence and scientific checks.
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

Completed managed experiment bundles open in the center pane as a Results Workbench. The application resolves the verified bundle by run identity, so researchers do not need to find or open internal JSON. The workbench shows structure, canonical metrics, interactive one-dimensional fields, operating points, validation evidence, and manifest provenance. The readable repository project retains `PLAN.md`, `REPORT.md`, `experiment.json`, `results.json`, and `validation.json` for audit and collaboration.

When a foreground agent run registers a hash-verified canonical result, Agent Kronig opens the workbench automatically for both passed and needs-review validation outcomes. Three separate assessments describe execution, scientific checks, and requested output coverage. A solver can finish and deliver the requested plots while a physical consistency check still needs review. Missing evidence is not treated as a passing check. Ordinary JSON files continue to use the generic file viewer.

The repository pane has one compact **Browse saved results** entry and a count, not a growing list of run cards. It opens a searchable library in the central workspace, newest first, with 20 studies per page. Results, original plans, reports, and reviewed recalculation remain accessible there. Browsing does not delete saved evidence or discard an unsaved file edit.

Saved results reopen verified scientific bundles after an app restart, without restoring repository chat memory. File sizes, hashes, bundle identity, and workspace scope are checked before plotting. Recalculate prepares a fresh plan and waits for review rather than silently running the old request. Eligible numerical recovery actions likewise produce a separate reviewed plan, preserve the original result, and record the changed numerical settings and both bundle identities. Scientific inputs and acceptance limits remain unchanged. A finer mesh is not a guarantee that a scientific warning will disappear.

The workbench distinguishes bias operating points from AC frequency samples, highlights requested profile points while retaining all computed points, and shows units, residuals, scales, tolerances, and applicability for checks. The plan input ledger separates researcher-reviewed inputs, derived values, expert settings, platform settings, and simulator implementation details. These categories describe review responsibility, not proof of who originally supplied each value.

Results can open in a separate native window. Scientific PDF export includes the selected result view, scientific inputs, validation evidence, and provenance, without chat or application controls. Structured artifacts remain available for reproducibility. Operational progress reports actual activity, not private model reasoning, and animation stops when work stops.

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

Pinned official DEVSIM diode, capacitance, small-signal, and two-region interface invariants are exercised with:

```bash
.venv/bin/pytest -q tests/integration/test_devsim_reference_benchmarks.py
```

Native release CI runs this suite on Linux x64, Windows x64, macOS Intel, and macOS Apple Silicon. Each target uploads a compact scientific evidence record, and a release gate rejects missing targets or disagreement in application revision, DEVSIM version and source revision, invariant fixture hash, or suite identity.

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
