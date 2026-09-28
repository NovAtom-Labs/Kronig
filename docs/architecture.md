# Architecture

## Design objective

The stable product is the simulator-neutral experiment and evidence workflow. DEVSIM and Sentaurus are replaceable execution backends. LLM output never becomes simulator code or a shell command.

The core flow is:

```text
research request
  -> ExperimentSpec
  -> schema and semantic validation
  -> backend capability decision
  -> researcher approval
  -> deterministic adapter
  -> bounded runner
  -> canonical result
  -> validation
  -> immutable evidence bundle and report
```

Retrieval supports specification and explanation, but it cannot override the schema, capability manifest, approval gate, compiler, or validators.

## Native repository IDE

The primary application shell is an Electron desktop application for Linux, Windows, and macOS.
Electron owns a private authenticated FastAPI service on an operating-system-selected loopback
port and renders the interface inside the native window. There is no supported standalone browser
launcher. Repository paths, Git inspection, simulator execution,
knowledge, and credentials remain on the researcher's machine.

The repository IDE establishes these contracts:

```text
repository path
  -> canonical WorkspaceRecord
  -> one process-scoped WorkspaceSessionRecord
  -> temporary ordered message and IDEEvent records
  -> workspace-scoped HTTP resources and Server-Sent Events
  -> three-panel native workspace
```

`WorkspaceManager` accepts Git and non-Git directories. It canonicalizes each path before using it
as workspace identity, reports Git branch and dirty state when available, and lists directory
entries without traversing external symlinks. Reopening the same canonical path reuses its stable
workspace UUID, but not an earlier agent session.

Each application process creates a locked runtime root containing a temporary SQLite database and
OpenHands state. Exactly one agent session belongs to the currently open workspace. The public IDE
routes are workspace-scoped and expose no conversation list, conversation selector, or restoration
endpoint. An SSE client resumes strictly after its last event identifier during that live session,
so renderer reconnection does not duplicate earlier activity.

Opening a different repository is refused while the current session has an active run. After a run
finishes, switching repositories deletes the current chat, approvals, events, run records, and
OpenHands state before creating a clean session for the next workspace. Graceful shutdown cancels
active agent work, denies pending approvals, and deletes the process runtime root. If the process
crashes, the next launch removes the stale runtime root before opening a workspace. Settings,
protected credentials, update configuration, repository files, and generated repository artifacts
remain outside this lifecycle and persist normally.

The authenticated root route serves only the Electron-owned renderer. The underlying typed request
and simulator APIs remain available to the agent, CLI, and approved integrations. They are not a
public application service.

The IDE exposes repository-confined OpenHands file operations, search, bounded terminal execution,
typed TCAD tools, and delegated subagents. Eligible UTF-8 text files can also be edited directly in
the central workspace through atomic, hash-checked saves. External-path access, package or network
commands, destructive actions, Git mutation, and remote mutation stop at an auditable approval
request. Session refresh is available manually and resynchronizes automatically after stream
reconnection, browser visibility changes, and during active runs.

## Stable contracts

### ExperimentSpec

`ExperimentSpec` is the only scientific intent passed into a backend. It contains one-dimensional ordered regions, dimensional quantities, profiles, boundary contacts, equations and models, a study, and requested observables. It rejects unknown fields and invalid units. It intentionally has no `device_type` field.

This gives researchers composability without a script per device. The existing PN and PIN files differ only in their data. A three-region detector-like stack, asymmetric junction, or other supported structure uses the same path.

### CapabilityManifest

Each backend publishes dimensions, equations, models, materials, profiles, contacts, studies, observables, and resource limits. Capability decisions return `supported`, `needs_input`, `backend_unsupported`, or `platform_unsupported`, with exact issue paths. `execution_state` is separate from scientific capability so an unavailable license is never misreported as unsupported physics.

### Adapter

Every adapter implements three operations:

```python
manifest -> CapabilityManifest
compile(spec, workspace) -> CompiledJob
normalize(native_run) -> CanonicalResult
```

The compiler is deterministic. Its job records the exact entrypoint, arguments, environment, input files, input digest, runtime digest, and compiler version. Free-form generated simulator syntax is forbidden.

### Runner

Runners execute a `CompiledJob` under a `RunBudget` and return a `NativeRunResult`. They use argument arrays, never a shell. The local runner applies timeout and file boundaries. The remote runner accepts only signed, backend-specific job artifacts and an allowlisted service endpoint.

### CanonicalResult and validation

All native output is normalized before scientific checks or reporting. Validators check execution, convergence, point count, finite values, sweep order, terminal conservation, carrier bounds, and provenance. A mandatory failure forces a failed bundle state.

### Experiment bundle

Bundle creation is atomic. A completed run contains:

```text
<run-id>/
  experiment.json
  compiled/               generated backend inputs
  logs/stdout.log
  logs/stderr.log
  native/native_result.json
  results/canonical.json
  validation/report.json
  report.md
  manifest.json           versions, state, digests, and artifact SHA-256 values
```

The bundle `report.md` is a compact evidence summary generated for every run. A separate narrative research report is optional and intent-driven. Both read structured data only. Logs remain evidence, not a source of numeric claims.

### Results Workbench

The desktop workspace treats `results/canonical.json` as the entry point for a scientific result. A workspace-scoped reader derives the bundle root, loads `experiment.json`, `validation/report.json`, and `manifest.json`, validates all four typed contracts, and verifies manifest byte counts and SHA-256 values before returning a result view.

The center-pane workbench consumes only that verified view. It derives metrics from canonical fields and bias points, displays configured structure from `ExperimentSpec`, and presents checks from `ValidationReport`. It never extracts numeric claims from logs, reports, chat text, or native simulator files.

```text
DEVSIM native result  -> DEVSIM adapter  -> CanonicalResult -> Results Workbench
Sentaurus export      -> Sentaurus adapter -> CanonicalResult -> Results Workbench
```

The browser recognizes only repository-relative paths ending in `results/canonical.json`. A completed foreground agent run may auto-open a result only when that exact path is present as a created, modified, or renamed artifact in the run's immutable change manifest. Other JSON files remain generic repository files.

The current canonical field contract and renderer are one-dimensional. Direct binary TDR or PLT parsing stays on the licensed Sentaurus side. Two-dimensional visualization requires a future canonical mesh contract and is not inferred from one-dimensional samples.

## Agent boundary

OpenHands always receives the packaged Agent Kronig skills, including experiment specification, research method, physics-model selection, mesh design, capability checking, DEVSIM compilation, recovery, validation, citation, artifact intent, reporting, and Sentaurus policy. Repository-local skills may supplement but not replace these built-in policies. Its custom `tcad_domain` tool exposes typed scientific actions. Repository tools remain subject to the workspace security policy and approval broker.

The repository IDE does not weaken this existing boundary. Its workspace-agent profile adds file,
search, terminal, Git, and approval-broker tools around a process-scoped OpenHands runtime.
Supported TCAD studies still pass through `ExperimentSpec`, capability
checks, deterministic adapters, canonical results, and validation rather than directly executing
model-written simulator syntax.

This separation makes the model replaceable. Model reasoning helps interpret intent and choose tools. Deterministic software owns units, support, simulator syntax, execution, checks, provenance, and output.

## Knowledge boundary

Sources enter through a versioned manifest with source ID, title, URL or controlled location, license, access class, trust level, backend, version, review status, and optional local path. Only allowlisted text formats are indexed. Each passage has a content hash and every hit returns a citation.

The packaged public corpus indexes a pinned, unmodified DEVSIM command reference under its documentation licence, the pinned Apache-2.0 simulator source and official examples, and source-grounded portable guides covering semiconductor equations, contacts, transport, mobility, recombination, band-gap narrowing, meshing, convergence, study design, and interpretation. The runtime reads the packaged index rather than expecting each research repository to contain its own copy.

Markdown ingestion keeps each section heading attached to its scientific paragraphs so
retrieval returns usable evidence rather than isolated headings. The index retains the
source identity, version, review state, licence, access class, and a content hash for
every passage. Backend and compatible-version filters are applied before context reaches
the model.

When local retrieval is missing, outdated, conflicting, or insufficient, the
`tcad_domain` tool exposes two additional operations:

```text
search_web(query, preferred_domains, limit) -> ranked discovery records
fetch_source(url, query, backend, version)   -> bounded evidence record
```

Web search and source fetch are classified as network access. The first request pauses
for approval, and category approval covers later network operations only for that run.
The fetcher permits public HTTPS targets on port 443, validates DNS and one redirect,
rejects private or reserved addresses, accepts only HTML or plain text, bounds bytes and
extracted characters, strips active page content, and caches records atomically with a
24-hour TTL. Every record includes retrieval time and SHA-256 content hash and is marked
as untrusted evidence.

The model is instructed to ignore commands and prompt-like text inside a fetched page.
It may use evidence to select a model, numerical strategy, or interpretation, but only
the portable schema, capability registry, deterministic adapter, simulator output, and
validators can authorize or accept an experiment.

Proprietary Sentaurus documents must remain on the licensed machine or another approved restricted store. They must not be committed or sent to a model provider unless the licence and company policy explicitly permit it.

## Scientific evaluation contract

`evaluations/scientific/cases.yaml` defines natural-language research cases without
encoding simulator commands in the prompts. The scorer checks backend, generic region
composition, study type, local and public evidence, required canonical fields,
validation checks, graphability, and immutable provenance. Integration tests execute
the same simulator-neutral specs through real DEVSIM and reopen the bundles through the
same verified reader used by the Results Workbench.

Opt-in live Bedrock evaluations check two distinct behaviors: a complete researcher
prompt must become a schema-valid supported `ExperimentSpec`, while a prompt missing
essential doping concentrations must produce actionable clarification questions rather
than guessed values. The live repository-agent evaluation then exercises file editing,
terminal validation, approvals, delegated review, and deterministic grading end to end.

## Adding scope without hardcoding devices

To add a new material, profile, contact, study, or observable:

1. Extend the portable schema only if the concept is simulator-neutral.
2. Add the capability value to each backend that truly supports it.
3. Add a deterministic mapping inside each supporting adapter.
4. Add normalization and mandatory validation for the new output.
5. Add data fixtures and conformance tolerances.
6. Add reviewed knowledge sources when model guidance is required.

Do not add named-device branches. If a new structure is expressible with existing concepts, add only an example or evaluation case.

## Current boundary

The foundation is intentionally one-dimensional and silicon-first. It is suitable for validating the architecture and automating small exploratory drift-diffusion studies. It is not a calibrated process or device-design authority. Two-dimensional geometry, arbitrary profiles, heteromaterials, advanced transport, process simulation, optical coupling, thermal coupling, and pilot access control require later scoped work.
