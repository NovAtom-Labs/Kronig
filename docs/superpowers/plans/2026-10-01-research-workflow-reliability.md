# Agent Kronig Research Workflow Reliability Design and Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task by task. Every behavior change starts with a failing test. Check each checkbox only after the named verification passes.

**Goal:** Turn the current chat-driven experiment flow into a reliable repository-native research workflow with correct scientific clarification, deterministic plan artifacts, one coherent approval boundary, bounded unattended execution, useful live progress, trustworthy validation, and a clean results handoff.

**Architecture:** Keep `ExperimentSpec` as the simulator-neutral product contract. Prompt preparation resolves researcher-owned intent. The deterministic experiment service prepares and digests the exact plan. A supervisor-owned plan gate persists the prepared object and audit artifacts, records exact consent, then resumes the same logical run. Simulator adapters remain responsible only for simulator syntax and normalization. Canonical results drive validation, reporting, and visualization.

**Tech Stack:** Python 3.13, Pydantic, SQLite, FastAPI, OpenHands SDK, Amazon Bedrock, DEVSIM 2.9.1, vanilla JavaScript, CSS, SVG, pytest, and the Node test runner.

**Spec:** This document is the approved design and implementation plan. It combines the previously identified 21 workflow fixes with the scientific and operational defects observed in the live implanted-silicon run.

## 1. Non-negotiable engineering constraints

- `ExperimentSpec` remains the portable contract shared by DEVSIM and future Sentaurus adapters.
- Product behavior must never branch on a named device such as diode, MOS capacitor, or MOSFET.
- Simulator syntax and simulator-specific defaults remain inside the relevant adapter package.
- Unsupported physics or missing consequential researcher inputs cause clarification or refusal, never silent approximation.
- Numeric reports, plots, comparisons, and conclusions derive from canonical result fields only.
- Every plan, execution, result, and report preserves source, version, hash, compiler, simulator, and validation provenance.
- No proprietary Sentaurus documentation or credentials enter the repository.
- The UI may show concise operational summaries, but it must never expose private chain-of-thought.
- A run may proceed unattended only under explicit, narrow, run-scoped consent.
- One writer remains the default for a workspace. Read-only inspectors may be parallel only when their access and output are bounded.

## Review focus

- Selecting an empty folder must produce a readable research project, not an exposed runtime bundle.
- Completed simulator execution with failed validation must remain viewable but must never be presented as scientifically passed.
- Repeated runs must preserve history without multiplying opaque directories or overwriting researcher files.
- Every supported canonical dataset shape and value type must either have an in-app renderer or an explicit unsupported-view state.
- Scientific PDF and data export must work offline across packaged macOS, Linux, and Windows builds.
- Closing the desktop application must never be blocked by a generic API failure, an unreachable backend, a stale session, or incomplete internal cleanup.
- Errors must be safe for researchers and useful for recovery. Credential redaction must not erase the error category, affected operation, recovery actions, or diagnostic identity.
- Results Workbench quality must be verified as scientific application software across representative data sizes, display sizes, accessibility settings, and all three supported operating systems.

## 2. Live-run findings that this plan must correct

The observed natural-language research request asked for a compensated 1D silicon structure with a Gaussian phosphorus implant, three exact bias points, broad field and transport outputs, interactive plots, validation, and absolute terminal current.

The current system did several important things correctly:

- It asked for implant center, Gaussian width, and driven contact rather than inventing those values.
- It preserved the requested voltage order of -1.0 V, 0 V, and +0.6 V.
- DEVSIM converged at all three operating points.
- The canonical bundle contained 34 axis-aware datasets.
- It reported terminal current density in A/m² and did not fabricate an absolute current.
- Current conservation, requested study order, finite values, nonnegative carrier densities, and electric-field consistency passed.

The run also exposed these concrete defects:

1. The researcher replied `approved`, but prompt preprocessing treated that as a brand-new explanation request. The old OpenHands conversation history happened to recover the intended plan, which is accidental behavior rather than a valid state transition.
2. Plan approval was represented as an ordinary assistant message, so the database had no typed pending-plan state or exact structured approval record.
3. The agent asked again for simulation permission after the researcher had already approved the exact plan.
4. Read-only inspection was performed through complex shell and inline Python commands, which caused repeated approval pauses.
5. The live run is currently blocked on `pip show plotly || pip install plotly`. Runtime dependency installation is not an acceptable way to produce a standard result view.
6. The deterministic bundle finished, but validation marked it failed because of validator defects.
7. `expected-point-count` expected one point for a three-value `dc_points` study because `expected_bias_points()` handles only `DCStudy`.
8. `band-ordering` rejected physically compatible datasets because it compares axis identifiers rather than axis semantics and coordinate values.
9. `recombination-component-balance` failed for the same class of axis-identity mismatch.
10. The agent attempted to pass the bundle envelope to `validate_result`, which accepts a `CanonicalResult`, then fell back to ad hoc shell inspection.
11. The agent promised absolute current without requesting contact cross-sectional area.
12. The plan rendered `maximum_retries = 6` for a fixed-point strategy even though fixed points do not use adaptive retry controls that way.
13. The plan was dumped into chat as a large Markdown block. The current renderer does not support tables, so raw pipe syntax and horizontal overflow damaged the interface.
14. Live progress remained too sparse during model inference and too noisy during terminal inspection.
15. Completed or stale thinking/progress indicators remained visually active after assistant output.
16. `build_report` returned `invalid_report_inputs`, but the supervisor still marked the run completed.
17. The agent wrote `make_plots.py` and `interactive_plots.html` into a finalized bundle after its manifest hashes were created. Those artifacts are absent from the manifest and therefore lack bundle integrity provenance.
18. The final response declared `Simulation Complete` and described the evidence as sound even though the authoritative bundle state and validation status were failed.
19. The final response substituted current density for the requested absolute current without identifying the unmet deliverable.
20. The qualitative interpretation called holes minority carriers in p-type material. Holes are the majority carriers in p-type material, so this is a scientific reasoning error.
21. The response made an unvalidated comparison to a typical uniformly doped junction and claimed a one-to-two-order field enhancement without a computed control case or cited evidence.
22. The full scientific report was again placed in chat rather than written as a repository artifact and opened in the central viewer.
23. `execute_experiment` hardcodes the bundle root as `<selected-workspace>/runs`, which confuses simulator internals with researcher-owned project files.
24. A successful execution leaves `<selected-workspace>/runs/.work/<run-id>` behind because cleanup currently occurs only on exceptions.
25. The visible run directory exposes `compiled`, `logs`, `native`, `validation`, opaque run IDs, and adapter-generated code to researchers who only selected a folder for their work.
26. The repository browser returns every filesystem entry and has no concept of human-facing artifacts versus application-managed internals.
27. The assistant response is rendered by a deliberately small Markdown parser that lacks tables and horizontal rules. Pipe tables are collapsed into paragraphs and long rows create horizontal overflow.
28. Free-form assistant output is currently allowed to act as the run-status UI. This is why a large report, validator warnings, and final status are mixed into one difficult-to-read message.
29. `WorkspaceResultReader` refuses every bundle whose manifest is not `completed`, so converged canonical data with failed validation cannot open in the normal Results Workbench. The agent worked around this by creating a separate HTML dashboard.
30. The live desktop status endpoint reports `active: false`, yet closing Agent Kronig fails. The selected session still contains two `prompt_preparations` rows whose foreign keys reference completed runs.
31. `SqliteIDEStore.delete_conversation_tree()` deletes approvals, permission grants, change baselines, and change manifests before deleting runs, but omits `prompt_preparations`. SQLite foreign-key enforcement therefore rejects deletion of the completed runs during shutdown.
32. The global FastAPI `Exception` handler converts that local database integrity failure into `The request failed without exposing provider or credential details.` This provider-oriented fallback is technically unrelated, gives no recovery path, and hides the component that failed.
33. Electron treats any failed `prepare-shutdown` request as a reason to cancel the quit indefinitely. The warning dialog offers no retry, diagnostic details, safe stop-and-quit path, or explicit quit-anyway escape hatch.

These observations are acceptance fixtures, not isolated special cases. The fixes must generalize across any valid one-dimensional study and future simulator adapters.

## 3. Scientific decision: current density versus absolute current

### 3.1 Why cross-sectional area is required

A one-dimensional drift-diffusion solution determines current density normal to the terminal. The canonical base quantity is therefore:

```text
J_terminal [A/m²]
```

Absolute terminal current requires a physical contact area:

```text
I_terminal [A] = J_terminal [A/m²] × A_contact [m²]
```

The current `Contact.area` field is optional. The DEVSIM normalizer emits `absolute_terminal_current__<terminal>` only when an area exists. This behavior is physically honest. The defect is that `Observable.TERMINAL_CURRENT` and the capability text do not distinguish current density from absolute current clearly enough, so prompt preprocessing failed to ask for the missing area while the generated plan claimed the absolute quantity would be delivered.

### 3.2 Required contract behavior

- Add an explicit `terminal_current_density` observable as the canonical base quantity.
- Add an explicit `absolute_terminal_current` observable as a derived quantity.
- Preserve backward compatibility for `terminal_current` by migrating it deterministically to `terminal_current_density`, with a schema-versioned warning until the legacy value is removed.
- `absolute_terminal_current` requires `Contact.area` for every terminal whose absolute current will be reported.
- The requirement is device independent and expressed as an observable dependency, not as a device-name condition.
- Prompt preprocessing asks one focused question when absolute current is requested and area is absent.
- The clarification offers two scientifically valid choices in plain language:
  - provide the contact cross-sectional area and report amperes
  - report normalized current density in A/m² instead
- No default area may be invented from mesh length, display width, or a typical fabrication value.
- `prepare_experiment` refuses an unresolved absolute-current request before execution.
- Plan artifacts and results display the exact unit next to every current quantity.
- Sentaurus will use the same portable distinction. Only its adapter implementation changes.

### 3.3 General scientific completeness engine

Cross-sectional area is only one dependency. The system must not depend on an LLM remembering an unbounded collection of hidden scientific prerequisites. Add a deterministic scientific completeness engine that evaluates the composed `ExperimentSpec`, requested deliverables, and backend capability descriptors before a plan can become ready.

Every input used by a plan receives one authority class:

| Authority class | Meaning | May the system fill it automatically? |
|---|---|---|
| Researcher-owned | Changes the physical structure, experiment, comparison, or interpretation requested by the researcher | No |
| Platform-reviewed default | A versioned, documented numerical or solver default approved by the product | Yes, with provenance and plan disclosure |
| Deterministically derived | Computed exactly from confirmed values, units, topology, or a declared mathematical relation | Yes, with derivation provenance |
| Evidence-backed expert suggestion | A literature or manual value that may be appropriate but is not implied by the request | No, unless the researcher explicitly accepts it |
| Simulator implementation detail | A numerical choice that preserves the approved physical contract and is owned by the adapter | Yes, with adapter provenance |
| Unsupported or unknown | No reviewed implementation or no defensible source exists | No, refuse or ask for a supported alternative |

Add an `InputResolutionRecord` for every consequential field:

```python
class InputResolutionRecord(StrictModel):
    path: str
    quantity: str
    value: JsonValue | None
    authority: InputAuthority
    source: ProvenanceReference | None
    derivation: str | None
    required_by: tuple[str, ...]
    status: Literal["resolved", "clarification_required", "unsupported"]
```

Capability descriptors and portable contract validators declare dependency rules. Representative examples include:

- absolute current requires terminal area
- absolute charge and total capacitance require terminal area
- a voltage sweep requires driven and reference contacts plus an unambiguous bias convention
- small-signal AC quantities require an operating point, perturbation definition, and frequency or frequency schedule
- quasi-static C-V and AC C-V must be distinguished because they are different studies
- a transient study requires a time schedule and an excitation definition
- a temperature study requires temperature values and model support over that range
- a generic parameter study requires an exact target path and values
- a metal work-function boundary requires work function and compatible material or contact semantics
- thermionic Schottky transport may require reviewed emission parameters and cannot be inferred from the word `metal`
- interface charge requires interface identity, sign convention, and density
- tabulated profiles require coordinates, units, and interpolation semantics
- comparison requests require a controlled variable, invariant inputs, and a comparison metric
- integral or total quantities require the geometry measure needed to convert a density
- calibration or experimental matching requires an objective, reference data, and accepted fit parameters
- derived quantities require all source observables and compatible axes

The rule system is compositional. It evaluates field paths and scientific relationships, not device names. A new backend or observable adds a descriptor and tests rather than a new hardcoded prompt branch.

Before producing clarification questions, the completeness engine generates an assumption ledger with:

- confirmed researcher inputs
- explicit exclusions
- platform defaults that will be used
- deterministic derivations
- unresolved consequential inputs
- unsupported requests
- warnings that affect interpretation

The LLM may phrase and prioritize questions, but it may not decide that a missing required dependency is unimportant. Deterministic validation is the final gate.

Question behavior must remain usable:

- Ask only about unresolved consequential inputs.
- Combine closely related missing values into one clearly structured question when safe.
- Do not ask for simulator-owned numerical implementation details.
- Do not ask for values already supplied or deterministically derivable.
- Offer a scientifically valid normalized or scoped alternative where one exists.
- Ask in bounded rounds, not an arbitrary fixed total. Prefer one focused round, allow a second only when an answer reveals a new dependency, and stop with a precise block if the request remains unresolved.
- Show why each answer matters and what output it controls.
- Never fill unanswered fields with a plausible value merely to continue unattended.

The prepared plan includes a readable `Scientific input ledger` section. This lets a researcher see every nontrivial value, where it came from, and whether it was supplied, derived, or defaulted.

### 3.4 Hybrid model reasoning and deterministic safety

The completeness engine is a guaranteed minimum, not a replacement for model reasoning. TCAD research is open ended, and no static registry can enumerate every scientifically consequential dependency in advance.

Use two complementary passes:

1. **Deterministic requirement pass:** Evaluate all known contract, capability, unit, topology, observable, derivation, and backend dependencies. These requirements cannot be waived by the model.
2. **Model scientific reasoning pass:** Ask the configured model to reason over the complete researcher objective, confirmed inputs, repository evidence, local TCAD knowledge, backend capabilities, and deterministic requirement report. The model identifies additional assumptions, experimental ambiguities, comparison confounders, validity limits, or missing inputs that the registered rules did not capture.

The model reasoning pass must be genuinely useful rather than a keyword mapper. It may:

- notice an ambiguity created by the interaction of otherwise valid choices
- identify that a requested comparison changes more than one physical variable
- detect that a requested conclusion needs an additional observable or control case
- recognize that a material, interface, or model parameter is outside the evidence range
- determine that an unusual boundary condition needs a researcher decision
- consult bounded local knowledge and, when allowed, authoritative external sources
- propose a new scientific requirement candidate with a concise rationale and evidence

The model may not:

- override a deterministic missing requirement
- invent a researcher-owned physical value
- silently convert an evidence-backed suggestion into an accepted input
- weaken or delete requested physics to make execution easier
- treat its own unverified memory as provenance

Represent model-discovered requirements as typed records with a stable run-local ID, target field or decision, rationale, consequence if unresolved, supporting evidence, and confidence. The system deduplicates them against deterministic requirements and applies these outcomes:

- a consequential, well-supported missing input becomes a focused clarification
- a noncritical modeling choice becomes a visible plan assumption or warning
- an unsupported or weakly supported claim becomes a request for evidence, a bounded research action, or a refusal to claim certainty
- an implementation detail owned by the adapter does not burden the researcher

The prepared plan therefore needs two forms of assurance:

- `contract_complete`: every registered hard dependency is resolved
- `scientifically_reviewed`: the model completed its contextual scientific review and all consequential discoveries are resolved or explicitly blocked

Both are required before execution. The researcher sees concise rationales and the resulting assumption ledger, not hidden chain-of-thought.

### 3.5 Intent-to-result traceability and scientific claim grounding

Scientific completeness does not end when a plan is approved. The system must prove that the executed result fulfills the confirmed intent and that the final interpretation does not outrun the evidence.

Create an intent-to-result traceability matrix that maps every requested deliverable through:

```text
confirmed researcher intent
  -> prepared ExperimentSpec field or derived deliverable
  -> backend capability and implementation
  -> canonical dataset or deterministic derived metric
  -> validator evidence
  -> report section and viewer representation
```

A missing link is an unmet deliverable. The system must state it plainly. It may not silently substitute a normalized quantity, omit the item, or mark all observables present merely because the reduced `ExperimentSpec` is internally complete.

Model-generated scientific interpretations use typed `ScientificClaim` records:

```python
class ScientificClaim(StrictModel):
    text: str
    kind: Literal["observed", "derived", "inference", "comparison", "limitation"]
    evidence_paths: tuple[str, ...]
    validator_ids: tuple[str, ...]
    source_references: tuple[ProvenanceReference, ...] = ()
    status: Literal["supported", "qualified", "unsupported", "contradicted"]
```

Rules for claims:

- Numeric claims come from canonical fields or deterministic derived metrics, never terminal text or copied model arithmetic.
- A claim that depends on a failed required validator cannot be presented as established.
- The model cannot relabel a deterministic validation failure as an infrastructure bug during the same run. The software defect must be fixed and the validator rerun.
- Comparative claims require a computed control case or authoritative evidence.
- Carrier-type, sign, unit, and majority or minority terminology pass deterministic domain checks where possible.
- Interpretive inferences remain welcome, but they are labeled as interpretations and cite the exact evidence supporting them.
- Unsupported claims are removed or presented as hypotheses requiring further study.

The final assistant message is generated from the traceability and claim records. It remains concise and links to a repository report containing the detailed interpretation.

## 4. Product workflow after the correction

The intended sequence is:

```text
Researcher prompt
  -> bounded prompt preparation
  -> focused clarification only when consequential inputs are missing
  -> confirmed intent
  -> deterministic ExperimentSpec preparation
  -> PLAN.md and plan.json written into the selected repository
  -> plan gate
       -> Review before run
       -> or Run automatically after validation
  -> same logical run executes the exact plan digest
  -> canonical bundle is validated
  -> concise chat conclusion
  -> Results Workbench opens the canonical bundle
```

The chat is the control surface and research log. It is not the primary storage location for long plans, raw tool transcripts, result arrays, or large reports.

### 4.1 Selected-folder contract

Selecting a folder means: `use this as my research project root`. It does not mean: `show me the simulator's temporary build tree`.

Use two storage planes.

**Researcher-facing project files inside the selected folder:**

```text
selected-folder/
  experiments/
    compensated-silicon-implant/
      PLAN.md
      experiment.json
      REPORT.md
      results.json
      data.csv
      figures/
```

Rules:

- Use a stable, readable slug derived from the research objective. Resolve collisions with `-2`, `-3`, and so on, never an opaque hash.
- Keep the default experiment folder flat. `figures/` appears only when exported figures exist.
- `results.json` is the portable canonical result. `data.csv` is a convenient tabular export when applicable.
- `PLAN.md`, `REPORT.md`, and `experiment.json` are normal repository files that can be edited, reviewed, diffed, and committed.
- Do not create `runs/`, `.work/`, `compiled/`, `native/`, or `logs/` in the selected folder.
- Do not write ad hoc scripts into the experiment output directory.
- Repeated executions of the same approved experiment are represented as run history in the application. They do not create researcher-visible `run-<hash>` folders unless the researcher explicitly exports a reproducibility bundle.

**Application-managed runtime files outside the selected folder:**

```text
<platform-application-data>/Agent Kronig/
  workspaces/<workspace-id>/
    runs/<run-id>/
      manifest.json
      compiled/
      logs/
      native/
      results/canonical.json
      validation/report.json
```

Use the native platform data directory on macOS, Linux, and Windows. The IDE store records the association among workspace, experiment slug, prepared plan, and immutable run bundle. Internal bundles remain hash-verified and reproducible without polluting the repository.

Provide an explicit `Export reproducibility bundle` action when a researcher needs the complete compiled input, logs, native result, validation evidence, manifest, and canonical data. Export uses a human-readable archive name and a user-selected destination.

Existing repositories with the legacy `runs/` layout require a recoverable migration:

- detect valid legacy manifests without changing files
- verify every recorded artifact hash
- import verified bundles into application-managed storage
- create the readable experiment project projection
- mark incomplete `.work` directories as recoverable leftovers
- offer `Clean up legacy run folders` only after verified import
- move removed legacy folders to the operating-system trash when available rather than deleting them permanently

### 4.2 Repository browser behavior

The left repository pane shows real project files only. It does not need to fake or hide internal directories because normal internal runtime files no longer live in the repository.

Add an `Experiments` grouping above the ordinary file tree when experiment records exist. Each experiment row exposes:

- readable title
- current status
- last execution time
- `Plan`, `Report`, and `Results` shortcuts
- run history available from the experiment detail view

The ordinary file tree remains a truthful representation of the selected folder. Generated researcher-facing files appear immediately through filesystem refresh events.

### 4.3 Run outcome and response presentation

Do not compress execution, validation, deliverable completeness, and agent completion into one ambiguous word.

Use a typed outcome:

```python
class ResearchRunOutcome(StrictModel):
    execution: Literal["not_started", "running", "completed", "failed"]
    validation: Literal["not_run", "passed", "needs_attention", "failed"]
    deliverables: Literal["not_evaluated", "complete", "incomplete"]
    reporting: Literal["not_started", "completed", "failed"]
    overall: Literal["running", "completed", "needs_review", "failed", "cancelled"]
```

For the observed run, the honest presentation would be:

```text
Run needs review

Simulation: completed, 3 of 3 operating points converged
Validation: 3 checks did not pass
Deliverables: incomplete, absolute terminal current was not produced
Report: failed to build through the structured report tool
```

The phrase `validation failed` is technically accurate for the current bundle, but it must be accompanied by scope and explanation. The UI must not imply that the simulator crashed, and it must not hide or overrule the failed checks.

Chat conclusions follow a bounded response contract:

- one clear outcome heading
- two to five concise evidence bullets
- explicit unmet deliverables and limitations
- primary actions such as `Open results`, `Open report`, and `View validation`
- no raw digest, full artifact inventory, giant Markdown table, or entire report body

Detailed tables and interpretation belong in `REPORT.md` and the central Results Workbench.

### 4.4 First-class in-app Results Workbench

Interactive results are a native Agent Kronig product surface, not a generated HTML file. The existing Results Workbench becomes the authoritative viewer for every supported canonical result.

The default experience is:

- a completed execution emits `result_ready`
- the central workspace switches to Results Workbench automatically
- the left repository pane remains available but may be collapsed
- the right research pane shows validation and interpretation context
- a `Pop out` action opens the same trusted local Results Workbench in a dedicated native application window
- no external browser is launched
- no HTML file is written to the selected repository

The Results Workbench is driven by canonical dataset metadata, not by device names, filenames, or backend-specific output syntax. Add a renderer registry selected from axis count, axis kind, unit, value type, shape, and centering.

Required generic renderer families:

- scalar value and metric cards
- one-dimensional curves
- multi-series overlays across bias, time, temperature, frequency, or parameter values
- spatial profile comparisons
- two-dimensional heatmaps for datasets with two continuous axes
- complex-valued Bode, phase, real-imaginary, and Nyquist views
- time traces and transient comparisons
- categorical or operating-point tables
- validation and convergence timelines

Each renderer supports, where scientifically applicable:

- zoom, pan, hover values, crosshair, and reset
- axis selection and unit-aware labels
- linear, logarithmic, and signed-log transforms without changing stored data
- series visibility and legend controls
- operating-point or parameter selection
- comparison of compatible runs
- validity masks and failed-point markers
- provenance and derivation inspection
- direct links to the plan, report, input ledger, and validation evidence

Large datasets use bounded server-side slicing or downsampling while preserving extrema and validity markers. The canonical artifact remains the source of truth.

### 4.5 Scientific export contract

Viewing and exporting are separate concerns.

Default export formats:

- scientific results PDF
- CSV for selected tabular or curve data
- JSON for canonical structured data
- SVG or PNG for selected figures
- full reproducibility bundle when explicitly requested

The PDF contains:

- experiment title and objective
- simulator, compiler, model, and parameter provenance
- structure, contacts, study, physics, and scientific input ledger
- selected publication-quality plots with captions and units
- requested derived metrics
- convergence and validation summary
- unmet deliverables, warnings, and limitations
- artifact hashes and run identity in an appendix

Generate the PDF through a trusted packaged renderer. In the desktop application this may use Electron's local `printToPDF` over the Results Workbench print layout, provided tests prove offline operation and deterministic content. Do not export a raw chat transcript. Do not require an installed browser.

Standalone HTML is not a normal export format. It may exist only as an explicitly requested developer diagnostic, never as the primary researcher result.

### 4.6 Professional Results Workbench quality contract

Results Workbench is a first-class scientific instrument panel. It must not feel like an embedded demo, a generic dashboard, or a collection of independently styled plots.

The default layout has four coherent regions:

- a compact result and operating-point navigator
- one dominant central canvas for plots, tables, and comparisons
- a contextual inspector for units, derivations, validation, and provenance
- a restrained command bar for view, compare, export, and pop-out actions

Panels are resizable and collapsible without changing their spacing rhythm, clipping controls, creating white scrollbar corners, or shrinking the scientific canvas below a usable minimum. The central result remains visually dominant. Loading, empty, unsupported, partial, validation-needs-review, and failed states each have a deliberate layout and a useful next action.

Scientific display rules are mandatory:

- axis labels always include quantity and canonical or selected display unit
- unit conversion changes only the view and records the transform visibly
- logarithmic views identify masked, zero, negative, non-finite, and invalid samples
- interpolation, smoothing, normalization, downsampling, and derived curves are never applied invisibly
- original sample values remain accessible through the data table and hover inspection
- compatible views use linked cursors and shared operating-point selection
- incompatible comparisons explain the axis, unit, shape, or centering conflict
- failed operating points and invalid regions remain visible and cannot be silently omitted
- validation warnings stay attached to the affected datasets and claims
- colors are perceptually distinct, colorblind safe, and never the only carrier of meaning

Professional interaction requirements:

- mouse, trackpad, keyboard, and screen-reader navigation
- predictable zoom, pan, reset, focus, and series-selection behavior
- persistent view configuration within the open app session
- no decorative motion, pulsing indicators, layout jumps, or unnecessary gradients
- compact native-feeling controls with consistent hit targets and focus states
- a readable dark theme at 100, 125, 150, and 200 percent scaling
- correct operation from 1280 by 720 through 4K displays

Performance rules:

- catalog and summary requests are bounded and paginated
- large-array parsing, reduction, and downsampling do not block the renderer main thread
- extrema, discontinuities, invalid masks, and requested operating points survive downsampling
- only visible plots render, and inactive views release expensive resources
- repeated interactions reuse immutable cached query results keyed by artifact hash and view parameters
- measured performance budgets and reference hardware are recorded in acceptance evidence instead of relying on subjective claims

Visual and scientific acceptance includes screenshot regression tests for representative scalar, profile, multi-series, heatmap, complex, transient, convergence, and validation views. Tests cover long units, scientific notation, negative values, invalid values, large legends, many operating points, narrow windows, expanded panes, collapsed panes, PDF layout, and both passed and needs-review outcomes.

### 4.7 Desktop lifecycle and error-reporting contract

Application lifecycle is independent of model-provider availability. Closing Agent Kronig must not call the LLM, require valid credentials, or depend on a provider-specific error path.

Every close source uses one coordinator:

- window close button
- macOS `Command+Q`
- Windows and Linux application quit
- updater restart
- operating-system logout or shutdown where the platform permits a grace period

The coordinator follows this bounded state machine:

```text
close requested
  -> inspect local lifecycle state with a short timeout
  -> idle: commit shutdown, stop the backend, close
  -> active: offer Keep working or Stop agent and quit
  -> status unavailable: offer Retry, Open diagnostics, or Quit anyway
  -> drain requested: cancel approvals and active work idempotently
  -> wait for a bounded grace period with visible progress
  -> terminate the owned backend process tree
  -> close even if internal session cleanup must be repaired on next launch
```

The user must never be trapped in the application. `Quit anyway` is always available after a lifecycle check or cleanup failure. It terminates only processes owned by this Agent Kronig instance, preserves repository files, retains recoverable diagnostic state, and never deletes a researcher-selected folder.

Session cleanup is transactional and complete. Every run-owned table, including `prompt_preparations`, is included in the deletion graph or uses an explicit reviewed cascade policy. A schema-level ownership test fails whenever a new foreign-key table is added without cleanup coverage. Cleanup of temporary app state is not a prerequisite for operating-system process termination.

Replace the global provider-oriented fallback with a typed safe error envelope:

```python
class ErrorEnvelope(StrictModel):
    code: str
    category: Literal[
        "input", "scientific", "provider", "simulator", "filesystem",
        "permission", "network", "lifecycle", "internal"
    ]
    severity: Literal["info", "warning", "error", "fatal"]
    user_message: str
    recovery_actions: tuple[str, ...] = ()
    retryable: bool = False
    diagnostic_id: str
```

Safe researcher-facing messages preserve what failed and what the researcher can do next. Provider and credential redaction applies only at provider and secret-bearing boundaries. It never replaces unrelated lifecycle, SQLite, simulator, filesystem, or validation failures with provider boilerplate.

Detailed diagnostics remain local by default and contain:

- diagnostic ID and timestamp
- application, backend, schema, simulator, compiler, and operating-system versions
- component, operation, HTTP route or IPC channel, and run or workspace identity where safe
- exception type, causal chain, and redacted stack trace
- recent bounded lifecycle and run events
- retry count and final recovery decision

Secrets, authorization headers, API keys, cookies, prompt bodies marked sensitive, and credential-store payloads are redacted before persistence. The error surface offers `Copy diagnostic summary` and `Open logs`, never a raw secret-bearing traceback. Remote telemetry remains opt-in and is not required for local diagnosis.

Errors appear where they are actionable:

- lifecycle failures use a native blocking dialog with recovery choices
- run failures attach to the run card and Activity evidence
- model configuration errors link to Settings
- simulator and validation failures link to Results Workbench evidence
- file operations fail inline beside the affected file
- nonblocking transient errors use a compact notice and bounded retry

Retries are allowed only for classified, idempotent operations. Every retry has a limit and visible final outcome. A failed error renderer, log writer, or backend response must itself degrade to a minimal native dialog while preserving the ability to quit.

## 5. Plan artifacts and exact approval

Each prepared experiment writes:

```text
experiments/<experiment-slug>/PLAN.md
experiments/<experiment-slug>/plan.json
```

`PLAN.md` is a readable scientific review document. `plan.json` contains the exact normalized prepared object, plan digest, capability digest, backend, warnings, and provenance needed for deterministic execution.

The plan gate has a dedicated state named `waiting_for_plan_approval`. It is not represented as a generic tool approval and it is not inferred from conversation history.

The UI provides:

- `Open plan`
- `Approve and run`
- `Request changes`
- `Run automatically after validation`, when the researcher selected that mode earlier in the run

Plain messages such as `approved`, `approve`, `looks good`, or `run it` map to `Approve and run` only when all of these are true:

- exactly one plan is pending in the active run
- the pending plan belongs to the current workspace and conversation
- its digest is unchanged
- there are no unresolved clarifications
- there is no competing approval request

Otherwise the message remains ordinary researcher input. The researcher never needs to copy a digest or repeat the full plan. The server records the digest internally when it converts contextual text into a structured approval.

## 6. Bounded unattended execution

Researchers need to be able to answer clarifications, leave the computer, and return to completed work. Blanket approval is too broad, while approval for every internal read is unusable. Implement two per-run modes.

### 6.1 Review plan before run

This remains the default. The system prepares and validates the plan, writes the artifacts, then pauses once for exact plan approval. Approving the plan also authorizes one execution of that exact digest on the selected local simulator backend. There is no second simulation-execution dialog.

### 6.2 Run automatically after validation

The researcher may explicitly select this before leaving. The resulting `ExecutionConsent` is scoped to:

- the current run
- the canonical selected workspace root
- one selected backend
- the compiled researcher-intent hash
- one deterministic plan derived from that confirmed intent
- at most one simulator execution
- expiration at terminal run state

It permits the system to prepare, persist, validate, and execute the plan without another pause only when:

- all consequential researcher-owned inputs are resolved
- the plan passes capability and semantic validation
- no unsupported physics is requested
- no warning requires human scientific judgment
- the plan has no semantic delta from the confirmed intent
- execution stays inside the selected repository and configured local simulator
- no network access, remote execution, package installation, system change, Git mutation, credential access, external file access, or destructive action is required

Network research has a separate optional run-scoped toggle and defaults to off. It must never be implied by unattended simulation consent.

If a consequential ambiguity or unsafe action appears, the run pauses with one clear notification. The system must not invent a value merely to remain unattended.

### 6.3 Consent contract

Add a typed immutable model with at least:

```python
class ExecutionConsent(StrictModel):
    run_id: UUID
    workspace_id: UUID
    canonical_root: Path
    backend: str
    compiled_intent_hash: str
    mode: Literal["review_plan", "run_after_validation"]
    max_executions: Literal[1] = 1
    allow_simulation_execution: bool
    allow_network_research: bool = False
    allowed_permission_categories: tuple[PermissionCategory, ...] = ()
    expires_on_terminal: bool = True
```

Persist consent with its creation time, source action, and consumed state. It is never reusable by another run.

## 7. Approval policy

The permission system distinguishes scientific workflow operations from genuine machine-risk operations.

### 7.1 Operations that do not ask

- prompt preprocessing and local capability inspection
- local skill invocation
- local knowledge retrieval
- reading files inside the selected repository, except known sensitive paths
- reading an Agent Kronig bundle through typed bounded result tools
- validating an `ExperimentSpec`
- preparing a deterministic experiment
- validating a canonical bundle
- rendering a report or plot through packaged dependencies
- executing the exact plan when covered by exact plan approval or unattended consent

### 7.2 Operations that may ask once per run category

- explicitly requested web research
- explicitly allowed remote execution
- access outside the selected repository

These grants expire with the run and are never promoted to global trust.

### 7.3 Operations that always ask at the exact action

- package installation or update
- system configuration change
- credential or sensitive file access
- destructive command
- Git history mutation or remote push
- any action that cannot be classified deterministically

Unknown actions remain fail closed, but normal `invoke_skill` calls and typed TCAD inspection operations must be classified explicitly rather than falling into `unrecognized_action`.

Package installation must not occur during a research run. Plotting and report dependencies belong in the application package and installation manifests. A missing packaged dependency produces a deterministic product error with remediation, not a runtime `pip install` request.

## 8. The 21 required product fixes

1. **Real plan state:** A prepared plan transitions the same run to `waiting_for_plan_approval`; the run is not marked complete.
2. **Contextual plain approval:** `approved` resolves the single pending plan directly and does not start prompt preprocessing as a new explanation task.
3. **One approval boundary:** Exact plan approval authorizes its single simulation execution, eliminating the second execution dialog.
4. **No approval spam:** Internal read-only operations, skill reads, result inspection, and packaged rendering do not ask repeatedly.
5. **Repository-native plans:** Every nontrivial simulation plan is written to `PLAN.md` and `plan.json` inside the selected repository.
6. **Concise chat:** Chat shows a short plan summary and a link to the artifact, not the full plan body.
7. **Safe plan revision:** Requested changes create a new prepared object and digest. An approved digest is immutable.
8. **Useful live activity:** Replace counters with named stages, current operation, elapsed time, last update, and meaningful completed actions.
9. **Visible quiet time:** During model inference, show a safe phase label and elapsed time without exposing hidden reasoning.
10. **Intelligible retries:** Group repair attempts and validation retries under the operation they are repairing.
11. **Chat and Activity separation:** Chat contains researcher messages, assistant conclusions, clarification cards, and a compact run card. Activity contains detailed tool and validation evidence.
12. **Correct Markdown:** Render headings, lists, code, links, horizontal rules, and GitHub-style tables safely.
13. **Correct scrolling:** Eliminate nested horizontal overflow, white scrollbar corners, and competing chat scroll regions.
14. **Scientific plan validation:** Require cross-sectional area for absolute current and reject contradictory solver controls such as retry counts on a fixed strategy.
15. **Same-run handoff:** Plan approval resumes the same logical run exactly once instead of creating a new run with the word `approved`.
16. **Natural results opening:** Successful execution selects and opens the new canonical bundle in Results Workbench automatically.
17. **Regression coverage:** Add unit, integration, JavaScript, API, and end-to-end tests for every state transition and scientific dependency.
18. **No stale thinking indicator:** Stop and remove live inference animation after a tool starts, an approval is requested, clarification appears, an assistant response arrives, or the run becomes terminal.
19. **Collapsed completed trail:** After completion, show a compact research record in chat with full technical detail available in Activity.
20. **Distinct message roles:** User prompts and assistant responses have clearly different alignment, surface treatment, metadata, and typography.
21. **Progress is not a message:** Research progress components are separate DOM structures and never masquerade as assistant chat turns.

## 9. Additional fixes discovered by the live run

22. **Typed bundle inspection:** Add domain operations that return bounded bundle summaries, validation evidence, and canonical dataset metadata without shell access.
23. **Correct validation API:** `validate_result` must accept only a canonical result. Add `validate_bundle` or `inspect_bundle` for bundle envelopes and document the distinction in the tool schema.
24. **Correct point accounting:** `expected_bias_points()` must use the generic study expansion for `DCPointsStudy` and every supported study type.
25. **Semantic axis compatibility:** Scientific validators compare axis kind, unit, centering, length, and coordinate values, not merely axis IDs.
26. **Packaged plotting:** Results Workbench must not depend on the agent installing Plotly. Use the existing browser plotting implementation or package every required renderer.
27. **Truthful result state:** A run with converged simulator points but failed validation is presented as `Execution completed, validation failed`, not simply success or generic failure.
28. **No duplicate post-validation:** `execute_experiment` already writes a validation report. The agent reads that result and only requests revalidation when a new canonical result is supplied.
29. **Retry-plan consistency:** Fixed-point studies omit adaptive retry claims. Adaptive strategies expose retry and minimum-step controls explicitly.
30. **Result evidence first:** The final answer must cite bundle-relative artifacts and canonical metrics rather than raw terminal output.
31. **Scientific completeness gate:** Every composed study passes deterministic dependency resolution before plan readiness.
32. **Assumption ledger:** Every consequential input records authority, source, derivation, and the requirement that introduced it.
33. **No model-only gap filling:** The LLM phrases questions and maps natural language, but deterministic rules decide whether required inputs are resolved.
34. **Model scientific review:** The model actively searches for consequential requirements beyond the static registry and records its discoveries as typed, evidence-bearing candidates.
35. **Two-pass readiness:** Execution requires both deterministic contract completeness and completion of contextual model scientific review.
36. **Intent-to-result traceability:** Every requested deliverable must map to canonical evidence or be reported as unmet.
37. **Scientific claim grounding:** Final interpretations remain model-generated but every claim is typed, evidence-linked, and validation-aware.
38. **Immutable finalized bundles:** Agents and viewers may not edit a finalized bundle outside the atomic bundle writer and manifest process.
39. **Terminal-state integrity:** A run cannot be marked completed when required validation, report generation, or declared deliverables failed.
40. **Researcher-facing project layout:** The selected folder contains readable experiment artifacts, not opaque runtime bundles.
41. **Externalized runtime storage:** Compiled input, native output, logs, ledgers, validation internals, and run IDs live in the platform application-data directory.
42. **No successful-work leaks:** Temporary `.work` and staging directories are removed after both success and failure.
43. **Typed outcome semantics:** Execution, validation, deliverables, reporting, and overall status remain separate.
44. **Bounded assistant conclusions:** Chat receives a concise structured conclusion while detailed reports open in the central pane.
45. **Workbench access for review states:** Hash-valid canonical data remains viewable when execution completed but validation needs attention.
46. **Explicit reproducibility export:** Full internal bundles enter a researcher-selected location only through an export action.
47. **Universal in-app result viewing:** Every supported canonical dataset opens in the native Results Workbench without an external browser or generated HTML.
48. **Data-driven renderer registry:** Plot selection follows canonical axes, units, shape, centering, and value type rather than named devices.
49. **Scientific PDF export:** Researchers can export a structured PDF with plots, provenance, validation, and limitations.
50. **No default HTML artifacts:** Interactive behavior stays inside the application; repository output remains scientific data and documents.
51. **Complete session deletion graph:** Temporary-session cleanup deletes every run-owned record, including prompt preparations, in a tested transaction.
52. **Schema ownership enforcement:** Adding a foreign-key table without declaring its lifecycle ownership fails an automated migration and cleanup test.
53. **Typed error envelopes:** Every API, IPC, simulator, provider, filesystem, validation, and lifecycle failure has a stable code, category, safe message, recovery actions, and diagnostic ID.
54. **Scoped secret redaction:** Credential-safe handling redacts sensitive values without replacing unrelated failures with provider boilerplate.
55. **Actionable close failures:** A failed shutdown explains that local cleanup failed and offers Retry, Open diagnostics, and Quit anyway.
56. **Unblockable application exit:** Backend unavailability, stale state, internal exceptions, and log failures cannot trap the researcher in Agent Kronig.
57. **One shutdown coordinator:** Window close, application quit, updater restart, and supported system shutdown share one idempotent lifecycle state machine.
58. **Recoverable cleanup:** Forced local exit preserves researcher files and enough internal evidence for safe startup repair.
59. **Local diagnostic trail:** Redacted structured logs correlate Electron, HTTP, supervisor, simulator, and run events without requiring remote telemetry.
60. **Contextual error presentation:** Errors appear beside the affected operation and never masquerade as an assistant scientific response.
61. **Professional workbench acceptance:** Results Workbench passes scientific correctness, accessibility, resizing, visual regression, performance, export, and cross-platform quality gates.
62. **Truthful view transformations:** Unit conversion, log scaling, interpolation, smoothing, normalization, masking, and downsampling are always visible and never mutate canonical data.
63. **Large-result resilience:** Bounded queries, worker-side processing, virtualization, caching, and extrema-preserving reduction keep large results interactive.
64. **Deliberate workbench states:** Loading, empty, unsupported, partial, needs-review, and failed results each provide a stable layout and useful next action.

## 10. Data model changes

### 10.1 Run states

Add:

```python
WAITING_FOR_PLAN_APPROVAL = "waiting_for_plan_approval"
```

Keep generic `WAITING_FOR_APPROVAL` for machine-risk permission requests. These states have different UI and API behavior.

### 10.2 Prepared plan record

Add an immutable `PreparedPlanRecord` containing:

- run ID
- normalized `PreparedExperiment`
- plan digest
- capability digest
- backend
- compiled intent hash
- Markdown path
- JSON path
- state: prepared, approved, rejected, superseded, executed
- creation, approval, and execution timestamps
- execution count constrained to zero or one
- approval source: button, contextual message, or unattended consent

### 10.3 Database tables

Add versioned SQLite migrations for:

```text
prepared_plans
execution_consents
```

Do not modify tables through one-off startup assumptions alone. Add a small schema-version table and idempotent migrations so existing desktop sessions upgrade safely.

### 10.4 Observable dependency metadata

Extend capability descriptors so an observable can declare:

- required spec paths
- unit and quantity kind
- base or derived status
- backend support maturity
- required validators
- plain-language clarification template

This lets preprocessing ask for area because of the requested observable rather than because it recognizes a specific device.

### 10.5 Composed dependency rules

Add a registry of portable `ScientificRequirement` objects that can target any field path, study type, boundary primitive, physics selection, observable, derivation, or requested deliverable. Each rule contains:

- stable rule ID and version
- triggering predicate over typed contract data
- required input paths
- authority class for each input
- deterministic derivation when available
- supported alternatives
- clarification rationale
- severity: required, warning, or informational
- capability and evidence references

The engine returns a typed `ScientificCompletenessReport`. A plan is ready only when every required record is resolved and no unsupported record remains.

### 10.6 Experiment project and run registry

Add an `ExperimentProjectRecord` that separates the human project projection from the internal immutable bundle:

- workspace ID and canonical root
- experiment ID and readable slug
- title and objective summary
- relative researcher-facing directory
- current plan and report paths
- active prepared-plan ID
- latest run ID and outcome
- creation and update timestamps

Add a `RunArtifactLocation` containing the platform-managed bundle root and optional exported bundle path. API responses expose workspace-relative researcher files and stable experiment IDs. They do not expose platform application-data paths to the model or UI unless a diagnostic export is explicitly requested.

Persist `ResearchRunOutcome` and derive the visible status from its component states. Never derive overall completion solely from an OpenHands finish event.

### 10.7 Lifecycle, ownership, and diagnostic records

Add a declarative persistence ownership registry. Each table declares whether its rows are workspace-owned, session-owned, run-owned, artifact-owned, or application-global. Migrations and cleanup services use the same registry, and a schema inspection test compares it with actual SQLite foreign keys.

Add a process-scoped `ShutdownSnapshot` containing:

- lifecycle state: idle, inspecting, draining, stopping, blocked, forcing, or complete
- owned backend process identity
- active run IDs and safe phase labels
- in-flight mutating request count
- pending approval and clarification counts
- cleanup status and retryability
- last diagnostic ID
- timestamps and bounded deadlines

Add a local `DiagnosticRecord` containing the safe `ErrorEnvelope`, redacted technical context, causal chain, component versions, correlation identifiers, and recovery outcome. Diagnostic retention is size and age bounded. It is stored under platform application data and is never committed to a repository.

## 11. HTTP and event contracts

Add endpoints:

```text
GET  /api/runs/{run_id}/plan
POST /api/runs/{run_id}/plan/approve
POST /api/runs/{run_id}/plan/revise
GET  /api/runs/{run_id}/consent
PUT  /api/runs/{run_id}/consent
GET  /api/runs/{run_id}/result-summary
GET  /api/workspaces/{workspace_id}/experiments
GET  /api/experiments/{experiment_id}
POST /api/runs/{run_id}/export-bundle
GET  /api/runs/{run_id}/results/catalog
POST /api/runs/{run_id}/results/query
POST /api/runs/{run_id}/exports/pdf
POST /api/runs/{run_id}/exports/figure
POST /api/runs/{run_id}/exports/data
GET  /api/desktop/shutdown-status
POST /api/desktop/drain
POST /api/desktop/commit-shutdown
GET  /api/diagnostics/{diagnostic_id}/summary
```

The approve request includes the expected plan revision, not a user-entered digest. The server verifies the stored digest and records it atomically.

Desktop lifecycle endpoints require the private shell control token. `drain` is idempotent. `shutdown-status` has a short bounded response time and never performs cleanup. `commit-shutdown` closes the mutation gate only after status is quiescent or the shell explicitly records a force-exit recovery decision. Ordinary renderer sessions cannot invoke force exit or retrieve a technical diagnostic record.

Every unsuccessful API response uses the typed safe error envelope. Framework validation errors are normalized into the same contract. The renderer never extracts meaning by parsing arbitrary exception strings.

Add events:

```text
plan_prepared
plan_artifacts_written
plan_approval_required
plan_approved
plan_revision_requested
execution_consent_created
execution_consent_consumed
result_bundle_created
validation_completed
result_ready
experiment_artifacts_updated
run_outcome_changed
shutdown_state_changed
diagnostic_created
recovery_action_completed
```

Every event includes `run_id`. Plan and result events include only workspace-relative paths in UI payloads.

## 12. Progress presentation model

Use a finite set of safe phases:

```text
Understanding request
Reviewing workspace context
Consulting local TCAD knowledge
Resolving scientific intent
Preparing experiment plan
Waiting for research details
Waiting for plan approval
Compiling simulator input
Running simulation
Normalizing results
Validating scientific output
Preparing results
Complete
```

Each phase exposes:

- start time
- elapsed duration
- last meaningful update time
- state: pending, running, waiting, completed, failed
- optional short evidence description
- optional artifact path

If no event arrives for a bounded interval, the UI changes to `Still working` and shows elapsed time. It does not invent new activity text. Tool actions remain visible in Activity. Chat shows only the current phase plus the two most recent meaningful milestones.

## 13. UI behavior

### 13.1 Chat

- User messages use a restrained tinted surface and right-aligned role treatment.
- Assistant messages use a neutral surface with clear `Agent Kronig` attribution.
- Scientific progress appears as a compact notebook-style run card between turns.
- The run card auto-collapses after a terminal assistant response.
- The composer remains fixed to the bottom of the pane.
- New content autoscrolls only while the researcher is already near the bottom. Manual scroll position is respected.

### 13.2 Plan review

- The chat card shows plan title, backend, study type, number of operating points, warnings, and artifact path.
- `Open plan` loads `PLAN.md` in the central editor or preview pane.
- Approval is a clear primary action, not a generic permission modal.
- `approved` in the composer invokes the same structured server action when a plan is pending.

### 13.3 Activity

- Show prompt-preparation phases, tool calls, validation checks, approvals, retries, and artifacts.
- Group repeated related operations.
- Do not show raw hidden reasoning.
- Show why a true approval is required in plain language, with technical details collapsed.

### 13.4 Markdown and scrollbars

- Parse safe GitHub-style tables into semantic `<table>` elements.
- Add horizontal-rule support.
- Wrap long inline code and digests.
- Keep preformatted code horizontally scrollable inside its own bounded block.
- Set `min-width: 0` on grid and flex children.
- Hide horizontal overflow on the chat transcript.
- Style or eliminate `::-webkit-scrollbar-corner` artifacts.
- Use one vertical scroll owner for the transcript.

## 14. Typed result operations

Extend `TcadDomainAction.operation` with:

```text
inspect_bundle
read_canonical_summary
validate_bundle
```

`inspect_bundle` returns:

- bundle state and backend
- simulator and compiler versions
- artifact inventory
- canonical dataset IDs, labels, units, shapes, centering, and axes
- operating-point states
- validation status and failed-check summaries
- report and viewer paths

It does not return every numeric array by default.

`read_canonical_summary` accepts selected dataset IDs and bounded slices or reductions. This avoids arbitrary inline Python.

`validate_bundle` reads the canonical result and approved experiment from a verified bundle, executes the correct validators, and returns the typed report.

All three are read-only, workspace-bounded, low risk, and never request approval.

## 15. Validation corrections

### 15.1 Expected point count

Replace the `DCStudy` special case with generic accounting based on supported study contracts. For `DCPointsStudy`, the expected count is exactly `len(study.values)`. For sweep studies, use the same `expand_study_points()` function used by compilation. Where a study yields multiple dimensions, the expected operating-point count is the deterministic product defined by that study contract.

### 15.2 Semantic axis equivalence

Add a shared `axes_compatible()` helper that checks:

- same number of dimensions
- same axis kind
- convertible or exact canonical unit
- same values within a strict deterministic tolerance
- same dataset shape
- compatible centering

Axis IDs may differ because normalizers currently create dataset-specific position axes. Validators must compare the actual scientific coordinate system. A later canonicalization improvement may deduplicate identical axes, but validators must remain correct either way.

Use the helper for band ordering, recombination component balance, current decomposition, and every other cross-dataset identity.

### 15.3 Validation outcome

Preserve the distinction among:

- simulator execution status
- canonical structural validity
- scientific validation status

The bundle state is failed when required validation fails, but the UI still exposes the converged data with a prominent validation warning. It must not claim scientific completion.

### 15.4 Bundle immutability and completion gate

Once `BundleWriter` finalizes a run directory and manifest, that directory is immutable. Results Workbench reads canonical data directly and does not write viewer assets into the bundle. If export artifacts are requested, create them through a versioned artifact service before finalization or under a separate workspace export directory with its own provenance record.

The supervisor marks a research run completed only when:

- the runtime ended normally
- no required tool action ended in error
- the exact approved plan executed at most once
- all required deliverables have a traceability outcome
- required report generation succeeded
- the final bundle state is consistent with the presented status
- any failed scientific validation is represented as a non-success terminal outcome or a clearly typed `completed_with_validation_failure` state

An assistant response alone is not evidence of completion.

## 16. Implementation tasks

### Task 1: Capture the observed failures as regression tests

**Files:**

- Create: `tests/fixtures/workflows/compensated_gaussian_three_point.json`
- Modify: `tests/unit/experiments/test_service.py`
- Modify: `tests/unit/validation/test_validation.py`
- Modify: `tests/unit/validation/test_physics_validation.py`
- Modify: `tests/unit/prompting/test_capability_context.py`
- Modify: `tests/e2e/test_agentic_repl.py`

- [ ] Add a three-point `DCPointsStudy` fixture with Gaussian donor and constant acceptor profiles.
- [ ] Add a failing test proving expected point count is three, not one.
- [ ] Add failing tests proving semantically equal position axes with different IDs pass band and recombination validation.
- [ ] Add a failing test proving absolute terminal current without area is unresolved.
- [ ] Add a failing supervisor test proving a plain `approved` message must not create a new run when one plan is pending.
- [ ] Run focused tests and confirm each fails for the intended reason.

### Task 2: Make current semantics scientifically explicit

**Files:**

- Modify: `src/tcad_agent/domain/models.py`
- Modify: `src/tcad_agent/capabilities/descriptors.py`
- Modify: `src/tcad_agent/capabilities/models.py`
- Modify: `src/tcad_agent/prompting/context.py`
- Modify: `src/tcad_agent/prompting/gateway.py`
- Modify: `src/tcad_agent/adapters/devsim/compiler.py`
- Modify: `src/tcad_agent/adapters/sentaurus/normalizer.py`
- Modify: `src/tcad_agent/reporting/markdown.py`
- Modify: `src/tcad_agent/web/static/results-workbench.js`
- Test: `tests/unit/domain/test_experiment_spec.py`
- Test: `tests/unit/capabilities/test_descriptors.py`
- Test: `tests/unit/prompting/test_gateway.py`
- Test: `tests/integration/test_devsim_reference_benchmarks.py`
- Test: `tests/js/results_workbench.test.js`

- [ ] Add explicit current-density and absolute-current observables with a versioned legacy mapping.
- [ ] Encode `Contact.area` as a conditional requirement of absolute current.
- [ ] Make preparation ask for area or confirmation of normalized current density.
- [ ] Refuse unresolved absolute-current plans in deterministic preparation.
- [ ] Verify area multiplication and units from canonical results.
- [ ] Render units honestly in the plan, report, and workbench.
- [ ] Run domain, capability, prompting, adapter, reporting, and workbench tests.

### Task 2A: Build the general scientific completeness engine

**Files:**

- Create: `src/tcad_agent/science/requirements.py`
- Create: `src/tcad_agent/science/completeness.py`
- Create: `src/tcad_agent/science/models.py`
- Modify: `src/tcad_agent/capabilities/descriptors.py`
- Modify: `src/tcad_agent/prompting/models.py`
- Modify: `src/tcad_agent/prompting/service.py`
- Modify: `src/tcad_agent/prompting/gateway.py`
- Modify: `src/tcad_agent/experiments/service.py`
- Test: `tests/unit/science/test_requirements.py`
- Test: `tests/unit/science/test_completeness.py`
- Test: `tests/unit/prompting/test_gateway.py`
- Test: `tests/unit/experiments/test_service.py`

- [ ] Define input authority, resolution, requirement, and completeness report contracts.
- [ ] Register portable dependency rules for every currently supported observable, study, contact primitive, profile, interface, derivation, and physics selection.
- [ ] Prove with tests that rules inspect typed composition rather than device names or prompt keywords.
- [ ] Generate unresolved-field records before LLM clarification.
- [ ] Give the model the full confirmed objective, deterministic report, capability context, repository evidence, and bounded TCAD knowledge so it can discover additional scientific requirements.
- [ ] Parse model-discovered requirements into typed records with rationale, consequence, evidence, and confidence.
- [ ] Deduplicate model discoveries against registered rules while preserving genuinely novel concerns.
- [ ] Let the LLM phrase bounded questions from both deterministic and accepted model-discovered requirements.
- [ ] Validate returned answers against the exact unresolved paths and units.
- [ ] Reject model-introduced values that have no researcher answer, reviewed default, deterministic derivation, or adapter-owned provenance.
- [ ] Render the scientific input ledger in `PLAN.md` and `plan.json`.
- [ ] Add a registry completeness test that fails whenever a new capability lacks requirements, provenance, implementation, normalization, and validation metadata.
- [ ] Add adversarial tests where the model finds an interaction-level ambiguity absent from the static registry and where unsupported model speculation is rejected.

### Task 3: Correct generic study accounting and physics validation

**Files:**

- Modify: `src/tcad_agent/experiments/planning.py`
- Modify: `src/tcad_agent/validation/physics.py`
- Modify: `src/tcad_agent/validation/datasets.py`
- Modify: `src/tcad_agent/results/datasets.py`
- Test: `tests/unit/experiments/test_service.py`
- Test: `tests/unit/validation/test_physics_validation.py`
- Test: `tests/unit/validation/test_dataset_validation.py`
- Test: `tests/integration/test_experiment_engine.py`

- [ ] Use generic study expansion for point accounting.
- [ ] Implement semantic axis compatibility.
- [ ] Reuse it in band, recombination, and current identities.
- [ ] Verify node and edge centering remain distinct and incompatible where appropriate.
- [ ] Re-run the observed three-point experiment and require all applicable checks to pass.

### Task 4: Add deterministic plan rendering and repository artifacts

**Files:**

- Create: `src/tcad_agent/experiments/artifacts.py`
- Modify: `src/tcad_agent/experiments/models.py`
- Modify: `src/tcad_agent/experiments/service.py`
- Test: `tests/unit/experiments/test_artifacts.py`
- Test: `tests/unit/experiments/test_service.py`

- [ ] Render `PreparedExperiment` into stable Markdown and JSON.
- [ ] Use normalized values from the prepared object, never a second LLM summary.
- [ ] Write atomically under `experiments/<slug>/` and reject traversal or symlink escape.
- [ ] Include digest, capability digest, warnings, unit-bearing contacts, study controls, physics, mesh, observables, and provenance.
- [ ] Omit misleading retry text for fixed strategies.
- [ ] Prove byte-stable output for identical prepared input.

### Task 4A: Separate project artifacts from internal run storage

**Files:**

- Create: `src/tcad_agent/experiments/projects.py`
- Create: `src/tcad_agent/runtime/paths.py`
- Create: `src/tcad_agent/bundles/export.py`
- Modify: `src/tcad_agent/agent/tools.py`
- Modify: `src/tcad_agent/experiments/service.py`
- Modify: `src/tcad_agent/bundles/writer.py`
- Modify: `src/tcad_agent/ide/models.py`
- Modify: `src/tcad_agent/ide/store.py`
- Modify: `src/tcad_agent/desktop/server.py`
- Test: `tests/unit/experiments/test_projects.py`
- Test: `tests/unit/runtime/test_paths.py`
- Test: `tests/integration/test_experiment_engine.py`
- Test: `tests/integration/test_bundle.py`

- [ ] Add a cross-platform application-data resolver for macOS, Linux, and Windows.
- [ ] Store immutable runtime bundles under the application-data workspace record, not under the selected repository.
- [ ] Project the approved plan, portable spec, canonical result, concise report, tabular data, and optional figures into `experiments/<readable-slug>/`.
- [ ] Use stable readable slug collision handling rather than opaque run IDs.
- [ ] Remove `.work` and staging directories in a `finally` path after successful and failed execution.
- [ ] Add explicit full-bundle export with hash verification and a user-selected destination.
- [ ] Add verified legacy `runs/` import and recoverable cleanup without silent deletion.
- [ ] Verify no `runs`, `.work`, `compiled`, `native`, or `logs` directory appears in a newly selected empty repository after a normal run.
- [ ] Verify repeated executions update application run history without multiplying opaque repository directories.

### Task 5: Persist plan state and execution consent

**Files:**

- Modify: `src/tcad_agent/ide/models.py`
- Modify: `src/tcad_agent/ide/store.py`
- Create: `src/tcad_agent/ide/migrations.py`
- Test: `tests/unit/ide/test_store.py`
- Test: `tests/unit/ide/test_sessions.py`

- [ ] Add `WAITING_FOR_PLAN_APPROVAL`.
- [ ] Add typed plan and consent records.
- [ ] Add schema versioning and idempotent migrations.
- [ ] Enforce one active prepared plan and one execution per digest.
- [ ] Expire consent on every terminal run state.
- [ ] Verify safe upgrade from the current database schema.

### Task 6: Capture prepared plans at the supervisor boundary

**Files:**

- Modify: `src/tcad_agent/agent/events.py`
- Modify: `src/tcad_agent/agent/supervisor.py`
- Modify: `src/tcad_agent/agent/runtime.py`
- Modify: `src/tcad_agent/agent/tools.py`
- Test: `tests/unit/agent/test_events.py`
- Test: `tests/unit/agent/test_supervisor.py`
- Test: `tests/integration/test_openhands_repository_runtime.py`

- [ ] Detect a successful `prepare_experiment` observation in the bridge.
- [ ] Persist the exact prepared object and write plan artifacts.
- [ ] Transition the same run to the plan gate before the agent emits a large prose plan.
- [ ] Pause the runtime at a stable continuation point.
- [ ] Resume that runtime with structured approval of the stored digest.
- [ ] Prevent mutation, replacement, or second execution of the approved plan.

### Task 7: Add contextual approval and dedicated plan APIs

**Files:**

- Modify: `src/tcad_agent/web/schemas.py`
- Modify: `src/tcad_agent/web/ide_routes.py`
- Modify: `src/tcad_agent/agent/supervisor.py`
- Test: `tests/unit/web/test_ide_api.py`
- Test: `tests/e2e/test_agentic_repl.py`

- [ ] Add get, approve, and revise plan endpoints with optimistic revisions.
- [ ] Intercept plain approval phrases only under the exact pending-plan conditions.
- [ ] Record button and contextual approvals identically.
- [ ] Resume the same run without prompt preprocessing.
- [ ] Return a clear conflict if the plan changed or more than one action is pending.

### Task 8: Implement bounded unattended execution

**Files:**

- Modify: `src/tcad_agent/ide/models.py`
- Modify: `src/tcad_agent/agent/supervisor.py`
- Modify: `src/tcad_agent/agent/policy.py`
- Modify: `src/tcad_agent/web/schemas.py`
- Modify: `src/tcad_agent/web/ide_routes.py`
- Test: `tests/unit/agent/test_policy.py`
- Test: `tests/unit/agent/test_supervisor.py`
- Test: `tests/unit/web/test_ide_api.py`
- Test: `tests/e2e/test_agentic_repl.py`

- [ ] Add the two per-run autonomy modes.
- [ ] Consume auto-run consent only after deterministic validation.
- [ ] Reject semantic plan drift from confirmed intent.
- [ ] Keep network, package, remote, destructive, system, sensitive, external-file, and Git actions outside auto-consent.
- [ ] Verify consent expires on success, failure, cancellation, stop, and app recovery.
- [ ] Verify a researcher can leave after clarification and receive a completed local run without intermediate safe-operation prompts.

### Task 9: Correct permission classification

**Files:**

- Modify: `src/tcad_agent/agent/policy.py`
- Modify: `src/tcad_agent/agent/events.py`
- Modify: `src/tcad_agent/ide/models.py`
- Test: `tests/unit/agent/test_policy.py`
- Test: `tests/unit/agent/test_events.py`

- [ ] Classify `invoke_skill` as a local read-only action.
- [ ] Classify typed bundle inspection and validation as local read-only actions.
- [ ] Preserve fail-closed behavior for unknown tools.
- [ ] Remove run-scoped grants for ambiguous complex shell.
- [ ] Produce plain-language approval summaries with collapsed technical details.
- [ ] Verify simulation execution covered by plan consent does not generate another approval.

### Task 10: Add typed bundle and result inspection

**Files:**

- Modify: `src/tcad_agent/agent/models.py`
- Modify: `src/tcad_agent/agent/tools.py`
- Modify: `src/tcad_agent/agent/events.py`
- Modify: `src/tcad_agent/ide/results.py`
- Test: `tests/unit/agent/test_tools.py`
- Test: `tests/unit/ide/test_results.py`

- [ ] Add `inspect_bundle`, `read_canonical_summary`, and `validate_bundle`.
- [ ] Bound arrays, text, file count, and output size.
- [ ] Verify all paths remain inside the workspace.
- [ ] Return typed failed-check summaries and viewer-ready metadata.
- [ ] Update tool instructions so the model does not pass a bundle into `validate_result`.
- [ ] Verify post-execution analysis completes without terminal Python or shell inspection.

### Task 11: Remove runtime package installation

**Files:**

- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `requirements-local.txt`
- Modify: `desktop/package.json`
- Modify: `src/tcad_agent/web/static/results-workbench.js`
- Test: `tests/unit/desktop/test_build_sidecars.py`
- Test: `tests/js/results_workbench.test.js`

- [ ] Decide the one packaged plotting path used by the desktop application.
- [ ] Remove agent instructions that suggest runtime plotting package installation.
- [ ] Verify a clean packaged environment opens every supported canonical plot without network or `pip`.
- [ ] Emit a product-level dependency error if a required packaged component is missing.

### Task 12: Replace sparse progress with a typed research timeline

**Files:**

- Modify: `src/tcad_agent/prompting/service.py`
- Modify: `src/tcad_agent/agent/supervisor.py`
- Modify: `src/tcad_agent/agent/events.py`
- Modify: `src/tcad_agent/web/static/ide-events.js`
- Modify: `src/tcad_agent/web/static/ide-agent.js`
- Test: `tests/unit/prompting/test_supervisor_integration.py`
- Test: `tests/js/ide_events.test.js`
- Test: `tests/js/ide_agent.test.js`

- [ ] Emit every safe preparation and execution phase.
- [ ] Track elapsed time and last meaningful update.
- [ ] Add a non-invented `Still working` presentation after a quiet interval.
- [ ] Group retries and repairs under their parent operation.
- [ ] Complete or remove inference indicators at every state boundary.
- [ ] Collapse completed research trails automatically.

### Task 13: Implement repository-native plan review UI

**Files:**

- Modify: `src/tcad_agent/web/templates/ide.html`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/static/ide-agent.js`
- Modify: `src/tcad_agent/web/static/ide-state.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Test: `tests/js/ide_agent.test.js`
- Test: `tests/e2e/test_ide_shell.py`

- [ ] Show a compact plan card with open, approve, and revise actions.
- [ ] Open `PLAN.md` in the central pane.
- [ ] Add the per-run review or unattended choice in plain language.
- [ ] Keep generic risk approvals in their separate modal.
- [ ] Disable duplicate approval actions while a request is in flight.
- [ ] Verify plan approval works by button and by plain `approved` message.

### Task 14: Repair chat semantics, Markdown, and scrolling

**Files:**

- Modify: `src/tcad_agent/web/static/ide-markdown.js`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/static/ide-agent.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Test: `tests/js/ide_markdown.test.js`
- Test: `tests/js/ide_agent.test.js`
- Test: `tests/e2e/test_ide_shell.py`

- [ ] Add safe tables and horizontal rules.
- [ ] Wrap digests and inline code without widening the pane.
- [ ] Use one transcript scroll owner and remove white scrollbar corners.
- [ ] Make user and assistant turns visually distinct.
- [ ] Keep progress cards separate from message elements.
- [ ] Preserve bottom autoscroll without fighting manual review.

### Task 14A: Add structured run outcomes and bounded response cards

**Files:**

- Modify: `src/tcad_agent/ide/models.py`
- Modify: `src/tcad_agent/ide/store.py`
- Modify: `src/tcad_agent/agent/supervisor.py`
- Modify: `src/tcad_agent/web/schemas.py`
- Modify: `src/tcad_agent/web/ide_routes.py`
- Modify: `src/tcad_agent/web/templates/ide.html`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/static/ide-agent.js`
- Modify: `src/tcad_agent/web/static/ide-markdown.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Test: `tests/unit/ide/test_store.py`
- Test: `tests/unit/agent/test_supervisor.py`
- Test: `tests/unit/web/test_ide_api.py`
- Test: `tests/js/ide_markdown.test.js`
- Test: `tests/js/ide_agent.test.js`

- [ ] Persist execution, validation, deliverable, reporting, and overall outcome components.
- [ ] Render a concise outcome card from typed data rather than trusting free-form assistant status prose.
- [ ] Humanize validation failure as `checks need attention` while preserving the exact failed-check count and technical status.
- [ ] Keep full reports out of chat and open `REPORT.md` in the central pane.
- [ ] Add safe Markdown table and horizontal-rule support for ordinary assistant content that still uses them.
- [ ] Bound long code, digests, paths, and table cells without horizontal transcript overflow.
- [ ] Verify a failed validation cannot display a completed-success card.
- [ ] Verify a simulator failure, validation failure, missing deliverable, and report failure each produce distinct readable outcomes.

### Task 14B: Present experiment projects instead of bundle internals

**Files:**

- Modify: `src/tcad_agent/ide/repository.py`
- Modify: `src/tcad_agent/ide/workspaces.py`
- Modify: `src/tcad_agent/web/ide_routes.py`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Test: `tests/unit/ide/test_repository.py`
- Test: `tests/unit/web/test_ide_api.py`
- Test: `tests/e2e/test_ide_shell.py`

- [ ] Add experiment-list API data sourced from `ExperimentProjectRecord`.
- [ ] Render readable experiment rows with Plan, Report, Results, status, and run history.
- [ ] Keep the ordinary repository tree truthful and immediately refreshed after artifact projection.
- [ ] Do not represent app-data runtime directories in the repository tree.
- [ ] Add `Export reproducibility bundle` to experiment details, not the default file tree.
- [ ] Verify the selected empty folder becomes a comprehensible research project after the first run.

### Task 14C: Replace generic failures with a typed error and diagnostic pipeline

**Files:**

- Create: `src/tcad_agent/web/errors.py`
- Create: `src/tcad_agent/observability/diagnostics.py`
- Modify: `src/tcad_agent/web/app.py`
- Modify: `src/tcad_agent/web/schemas.py`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/static/ide-agent.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Modify: `desktop/src/main.js`
- Modify: `desktop/src/preload.js`
- Test: `tests/unit/web/test_error_contract.py`
- Test: `tests/unit/observability/test_diagnostics.py`
- Test: `tests/js/ide_errors.test.js`
- Test: `desktop/test/main-security.test.js`

- [ ] Start with regression tests proving the current generic handler obscures a lifecycle database failure.
- [ ] Add the stable typed `ErrorEnvelope` contract and an exhaustive category registry.
- [ ] Map known domain, provider, simulator, filesystem, network, permission, lifecycle, and validation failures at their source boundary.
- [ ] Restrict provider-safe redaction to provider exceptions and secret-bearing fields.
- [ ] Generate one correlation and diagnostic ID across Electron IPC, local HTTP, supervisor, tool, simulator, and renderer boundaries.
- [ ] Persist size-bounded and age-bounded local diagnostic records with secrets redacted before disk write.
- [ ] Add contextual renderer components for inline, run, settings, results, and lifecycle failures.
- [ ] Add `Copy diagnostic summary` and `Open logs` without exposing authorization tokens, API keys, cookies, or secret-store contents.
- [ ] Allow bounded automatic retry only for explicitly classified idempotent operations.
- [ ] Verify failure inside the diagnostic writer still produces a minimal native message and never prevents application exit.
- [ ] Verify secret-shaped fixtures are absent from every API response, log, clipboard diagnostic, and screenshot artifact.

### Task 14D: Make desktop shutdown idempotent, recoverable, and impossible to trap

**Files:**

- Modify: `src/tcad_agent/ide/store.py`
- Modify: `src/tcad_agent/ide/sessions.py`
- Modify: `src/tcad_agent/desktop/auth.py`
- Modify: `src/tcad_agent/web/app.py`
- Modify: `src/tcad_agent/desktop/server.py`
- Modify: `desktop/src/main.js`
- Modify: `desktop/src/backend-supervisor.js`
- Modify: `desktop/src/preload.js`
- Test: `tests/unit/ide/test_store.py`
- Test: `tests/unit/ide/test_sessions.py`
- Test: `tests/unit/desktop/test_auth.py`
- Test: `tests/unit/desktop/test_server.py`
- Test: `desktop/test/backend-supervisor.test.js`
- Test: `desktop/test/main-security.test.js`
- Test: `tests/e2e/test_desktop_shutdown.py`

- [ ] Reproduce the live foreign-key failure with a completed run that has a `prompt_preparations` row.
- [ ] Delete `prompt_preparations` and every other run-owned row before deleting `agent_runs`, inside one transaction.
- [ ] Add schema ownership coverage that fails whenever a new foreign key is absent from the cleanup graph.
- [ ] Separate status inspection, run drain, cleanup commit, backend termination, and window destruction into explicit idempotent phases.
- [ ] Use one close coordinator for every desktop quit source and guard against recursive close events.
- [ ] Show `Keep working` and `Stop agent and quit` when active work exists.
- [ ] Show `Retry`, `Open diagnostics`, and `Quit anyway` when lifecycle inspection or cleanup fails.
- [ ] Bound each network wait, agent join, graceful process stop, and forced process stop independently.
- [ ] Make force exit terminate only the process tree launched by this application instance.
- [ ] Preserve selected-repository files and leave recoverable app-data state when cleanup cannot finish.
- [ ] Repair recoverable stale internal state on next launch through an explicit versioned recovery routine.
- [ ] Verify idle close, active close, approval wait, clarification wait, failed run, unresponsive backend, database failure, updater restart, repeated close clicks, and operating-system quit on macOS, Linux, and Windows.

### Task 15: Complete result handoff

**Files:**

- Modify: `src/tcad_agent/bundles/models.py`
- Modify: `src/tcad_agent/ide/results.py`
- Modify: `src/tcad_agent/web/ide_routes.py`
- Modify: `src/tcad_agent/agent/supervisor.py`
- Modify: `src/tcad_agent/web/static/ide-events.js`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/static/results-workbench.js`
- Test: `tests/unit/ide/test_results.py`
- Test: `tests/unit/web/test_ide_api.py`
- Test: `tests/js/results_workbench.test.js`
- Test: `tests/e2e/test_agentic_repl.py`

- [ ] Emit `result_ready` with a verified run identifier and researcher-facing experiment paths, not the platform application-data path.
- [ ] Replace the single bundle `state` meaning with explicit execution and validation states while preserving backward-compatible reads.
- [ ] Resolve result views by stable run or experiment ID through the store instead of requiring a visible `runs/<id>/results/canonical.json` path.
- [ ] Permit hash-valid canonical results to open when execution completed and validation needs attention.
- [ ] Auto-open Results Workbench after successful or validation-failed execution.
- [ ] Show simulator status and validation status separately.
- [ ] Surface failed checks next to plots without hiding converged data.
- [ ] Link back to `PLAN.md`, `report.md`, canonical data, and provenance.
- [ ] Keep the workbench entirely canonical-result driven and backend neutral.

### Task 15A: Add intent traceability, claim grounding, and completion integrity

**Files:**

- Create: `src/tcad_agent/science/claims.py`
- Create: `src/tcad_agent/reporting/traceability.py`
- Modify: `src/tcad_agent/prompting/models.py`
- Modify: `src/tcad_agent/experiments/models.py`
- Modify: `src/tcad_agent/experiments/service.py`
- Modify: `src/tcad_agent/bundles/writer.py`
- Modify: `src/tcad_agent/agent/supervisor.py`
- Modify: `src/tcad_agent/agent/runtime.py`
- Modify: `src/tcad_agent/reporting/markdown.py`
- Test: `tests/unit/science/test_claims.py`
- Test: `tests/unit/reporting/test_traceability.py`
- Test: `tests/integration/test_bundle.py`
- Test: `tests/unit/agent/test_supervisor.py`
- Test: `tests/e2e/test_live_unattended_experiment.py`

- [ ] Persist the confirmed deliverables separately from the reduced simulator contract.
- [ ] Build a traceability matrix from intent through canonical evidence and viewer output.
- [ ] Mark every missing link as an unmet deliverable.
- [ ] Parse model interpretations into typed scientific claims.
- [ ] Reject or qualify claims that contradict validation, units, sign conventions, or domain invariants.
- [ ] Require a control result or source for comparative magnitude claims.
- [ ] Add a regression test rejecting the phrase `minority-carrier hole transport` for a p-type majority-hole interpretation.
- [ ] Prevent writes inside finalized bundles and verify manifest coverage for every bundled artifact.
- [ ] Gate completed run state on required tools, validation status, report generation, and deliverable traceability.
- [ ] Verify a failed `build_report` cannot yield a completed run or a `Simulation Complete` conclusion.

### Task 15B: Make Results Workbench the universal native result surface

**Files:**

- Create: `src/tcad_agent/results/catalog.py`
- Create: `src/tcad_agent/reporting/pdf.py`
- Modify: `src/tcad_agent/ide/results.py`
- Modify: `src/tcad_agent/web/schemas.py`
- Modify: `src/tcad_agent/web/ide_routes.py`
- Modify: `src/tcad_agent/web/templates/ide.html`
- Modify: `src/tcad_agent/web/static/results-workbench.js`
- Modify: `src/tcad_agent/web/static/ide.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Modify: `desktop/src/main.js`
- Modify: `desktop/src/preload.js`
- Test: `tests/unit/results/test_catalog.py`
- Test: `tests/unit/ide/test_results.py`
- Test: `tests/unit/reporting/test_pdf.py`
- Test: `tests/unit/web/test_ide_api.py`
- Test: `tests/js/results_workbench.test.js`
- Test: `desktop/test/main-security.test.js`
- Test: `tests/e2e/test_ide_shell.py`

- [ ] Build a canonical dataset catalog that selects renderer families from axis metadata, shape, centering, units, and real or complex value type.
- [ ] Cover scalar, curve, profile family, heatmap, complex response, time, frequency, parameter, operating-point, convergence, and validation views.
- [ ] Add bounded result-query APIs for dataset selection, slicing, comparison, and extrema-preserving downsampling.
- [ ] Auto-open the central workbench from `result_ready` for passed and needs-review outcomes.
- [ ] Add a secure native pop-out `BrowserWindow` restricted to the same trusted local application origin with sandboxing, context isolation, denied external navigation, and no Node integration.
- [ ] Keep all zoom, pan, hover, crosshair, transforms, overlays, validity markers, and comparison interactions inside Agent Kronig.
- [ ] Remove instructions and code paths that generate or open `interactive_plots.html` as the standard result.
- [ ] Add PDF export using the packaged trusted print layout and a native save dialog.
- [ ] Include plots, captions, units, input ledger, provenance, validation, limitations, and artifact identity in the PDF.
- [ ] Add CSV, JSON, SVG, and PNG exports for selected datasets or figures.
- [ ] Verify the viewer and PDF export work offline on macOS, Linux, and Windows packaging targets.
- [ ] Verify no result-view action opens the system browser unless the researcher explicitly opens an external cited source.

### Task 15C: Qualify Results Workbench as professional scientific software

**Files:**

- Create: `src/tcad_agent/results/downsampling.py`
- Create: `src/tcad_agent/results/view_state.py`
- Modify: `src/tcad_agent/results/catalog.py`
- Modify: `src/tcad_agent/ide/results.py`
- Modify: `src/tcad_agent/web/static/results-workbench.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Modify: `src/tcad_agent/reporting/pdf.py`
- Test: `tests/unit/results/test_downsampling.py`
- Test: `tests/unit/results/test_view_state.py`
- Test: `tests/js/results_workbench.test.js`
- Create: `tests/e2e/test_results_workbench_visual.py`
- Create: `tests/e2e/test_results_workbench_accessibility.py`
- Create: `tests/e2e/test_results_workbench_performance.py`
- Create: `docs/testing/results-workbench-acceptance.md`

- [ ] Start with representative canonical fixtures for scalar, profile, sweep, multi-series, heatmap, complex, time, frequency, convergence, validation, invalid-value, and failed-point data.
- [ ] Establish one coherent workbench layout with a dominant scientific canvas, compact navigator, contextual inspector, and restrained command bar.
- [ ] Verify resizing and collapsing panels never clips controls, corrupts spacing, creates extra scroll owners, or hides the primary data surface.
- [ ] Implement explicit loading, empty, unsupported, partial, needs-review, and failed states.
- [ ] Make every display transform visible, reversible, unit-aware, and independent of immutable canonical data.
- [ ] Add linked cursors, compatible-run comparison, operating-point selection, validation overlays, and provenance inspection.
- [ ] Add virtualized tables and worker-side bounded processing for large arrays.
- [ ] Use extrema-preserving downsampling with property tests for discontinuities, masks, endpoint preservation, and non-finite values.
- [ ] Record measured responsiveness budgets on declared reference hardware and fail acceptance when regressions exceed the agreed threshold.
- [ ] Meet keyboard operation, focus visibility, accessible naming, contrast, color-independent meaning, and screen-reader summary requirements.
- [ ] Add deterministic screenshot baselines at representative window sizes and display scaling values on all supported desktop platforms.
- [ ] Verify scientific notation, long units, dense legends, many operating points, negative values, invalid samples, and mixed validation outcomes remain readable.
- [ ] Verify PDF pages have embedded fonts, selectable text, vector plots where supported, captions, units, provenance, validation, limitations, page numbering, and no clipped content.
- [ ] Run a human quality checklist that rejects placeholder copy, inconsistent control sizing, decorative animation, layout jumps, browser-like chrome, and unstyled exceptions.

### Task 16: End-to-end unattended research acceptance

**Files:**

- Modify: `tests/e2e/test_live_prompt_preprocessing.py`
- Modify: `tests/e2e/test_live_unified_backend.py`
- Modify: `tests/e2e/test_live_expanded_devsim.py`
- Create: `tests/e2e/test_live_unattended_experiment.py`
- Create: `docs/testing/research-workflow-reliability-acceptance.md`

- [ ] Run a natural underspecified prompt that requires clarification.
- [ ] Answer the focused questions, including cross-sectional area when absolute current is requested.
- [ ] Select `Run automatically after validation`.
- [ ] Verify no further approval appears for local preparation, execution, inspection, validation, reporting, or plotting.
- [ ] Verify package installation, network access, and external file access still pause.
- [ ] Verify the plan artifact, result bundle, validation report, concise assistant conclusion, and interactive plots all agree.
- [ ] Repeat in default review mode and approve with the single word `approved`.

### Task 17: Full verification and documentation

**Files:**

- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `docs/architecture.md`
- Modify: `docs/testing/research-workflow-reliability-acceptance.md`
- Create: `docs/testing/desktop-lifecycle-acceptance.md`
- Create: `docs/testing/results-workbench-acceptance.md`

- [ ] Run focused Python tests for each task during implementation.
- [ ] Run all Node tests.
- [ ] Run the complete Python suite.
- [ ] Run Ruff and strict mypy.
- [ ] Run desktop tests and a packaged-app smoke test.
- [ ] Run packaged idle-close, active-close, backend-failure, and quit-anyway smoke tests on macOS, Linux, and Windows.
- [ ] Run Results Workbench visual, accessibility, large-data, offline-export, and display-scaling acceptance.
- [ ] Run `git diff --check`.
- [ ] Scan for credentials, proprietary Sentaurus material, device-name branching, and raw absolute-current assumptions.
- [ ] Record exact commands, versions, and results in the acceptance document.

## 17. Required test matrix

| Scenario | Expected clarification | Approval behavior | Expected result |
|---|---|---|---|
| Absolute current requested, no area | Ask for area or normalized density | No plan until resolved | No fabricated amperes |
| Current density requested | None for area | One plan gate or valid unattended consent | A/m² result |
| Plain `approved` with one pending plan | None | Resume same run | One execution |
| Plain `approved` with no pending plan | None | Ordinary chat input | No accidental execution |
| Three explicit DC points | None if complete | One execution boundary | Expected count equals three |
| Identical coordinate axes with different IDs | None | None | Cross-dataset validators run and pass when physics passes |
| Read canonical bundle | None | None | Typed bounded summary |
| Install missing package | None | Exact action approval | Never auto-approved |
| Unattended local validated plan | All questions answered first | No post-plan pauses | Results open on return |
| Unattended run needs web research | Optional network choice | Pause unless explicitly granted | No implicit network |
| Unsupported physics | Focused alternative or refusal | No execution approval | Explicit blocked state |
| Validation failure after convergence | None | None | Plots available with validation warning |
| Any new observable with undeclared dependencies | Not allowed to become ready | No execution | Registry completeness test fails |
| Evidence-backed suggested value | Ask for acceptance | No execution until accepted | Source recorded in input ledger |
| Platform-reviewed solver default | None unless researcher overrides | Normal plan behavior | Version and provenance recorded |
| Novel coupled ambiguity found by model | Focused evidence-backed question | No execution until consequential issue is resolved | Discovery recorded in input ledger |
| Weak model speculation with no evidence | No silent assumption | Research, warning, or explicit uncertainty | No fabricated input |
| Requested absolute current but only density exists | No silent substitution | Run is incomplete or clearly qualified | Deliverable marked unmet |
| Validator failed but model believes it is a validator bug | No model override | Fix and rerun validator | No `evidence is sound` claim |
| Finalized bundle receives a new plot script | Not permitted | Write separate export or rebuild atomically | Manifest remains authoritative |
| Required report tool fails | None | No false completed state | Run reports failed deliverable |
| Researcher selects an empty folder | None | Normal workflow | Only readable experiment project files appear |
| Same experiment is executed twice | None | Per-run policy applies | One project folder with visible run history |
| Execution passes and validation fails | None | None | Results open with a needs-review status |
| Assistant emits a Markdown table | None | None | Semantic table renders without transcript overflow |
| Supported canonical result becomes ready | None | None | In-app Results Workbench opens automatically |
| Researcher chooses Pop out | None | None | Secure native Agent Kronig window opens, not a browser |
| Researcher exports results | Choose destination and content | Native save confirmation | Scientific PDF, CSV, JSON, SVG, PNG, or full bundle |
| Agent attempts default HTML dashboard | None | Refused by workflow contract | In-app renderer is used instead |
| Idle app is closed | None | None | Window and owned backend exit cleanly |
| Completed run has prompt-preparation rows | None | None | Transactional session cleanup succeeds without a foreign-key failure |
| Active local run is closed | None | One lifecycle choice | Keep working or stop the run and quit |
| App is closed during approval or clarification | None | One lifecycle choice | Pending state is cancelled or retained according to the selected action, then exit completes |
| Backend status request times out | None | Native recovery choice | Retry, diagnostics, and quit-anyway remain available |
| Session cleanup raises an internal exception | None | Native recovery choice | Researcher can quit and repairable app state remains |
| Provider exception contains credential-shaped text | None | None | Provider message is actionable, secret is redacted, diagnostic ID is present |
| SQLite lifecycle failure occurs | None | None | Error is classified as lifecycle or internal, never provider |
| Large result exceeds the immediate render budget | None | None | Bounded worker-side query and extrema-preserving reduction keep the UI responsive |
| Result contains invalid or non-finite samples | None | None | Samples are marked, counted, inspectable, and never silently dropped |
| Workbench is resized or panels collapse | None | None | Central canvas remains usable with stable spacing and one intended scroll owner per region |
| Workbench runs at high display scaling | None | None | Controls, labels, legends, focus, and plots remain readable without clipping |
| Validation-needs-review result is exported | None | Native save confirmation | PDF visibly preserves validation status and failed checks |

## 18. Definition of done

This work is complete only when all of the following are true:

- A researcher can submit the implanted-silicon prompt and is asked for area if absolute current remains requested.
- The same dependency mechanism covers all registered studies, observables, boundaries, profiles, physics models, and derived quantities without device-name branches.
- Every plan contains a complete scientific input ledger, and no consequential value has an unrecorded origin.
- The model completes a contextual scientific review and can add novel, evidence-bearing requirements beyond the deterministic registry.
- Every confirmed deliverable has a traceable canonical result or an explicit unmet status.
- Final scientific claims cannot contradict validation and cannot introduce unsupported comparisons or incorrect carrier terminology.
- Finalized bundles remain immutable and every bundled artifact is covered by the manifest.
- A required tool error or failed required deliverable prevents a false completed run.
- The selected folder contains readable experiment projects and no simulator-private run tree.
- Platform-managed bundles and temporary work directories never appear in the repository browser.
- Chat conclusions are short, correctly formatted, and driven by typed outcome data.
- Every supported canonical result is interactively viewable inside Agent Kronig, including validation-needs-review runs.
- Scientific PDF export works without an installed browser and standalone HTML is not a normal result artifact.
- The plan exists as repository files and is not dumped into chat.
- `approved` resumes the same run and executes exactly once.
- Review mode produces one plan approval, not a second simulation approval.
- Unattended mode completes a fully local validated run without pauses for internal reads, skill invocation, shell inspection, plotting, or reporting.
- Genuine machine-risk actions still stop for clear approval.
- The observed three-point DEVSIM case no longer fails point-count, band-axis, or recombination-axis validation for structural reasons.
- The agent never installs plotting packages during a research run.
- Chat distinguishes roles, progress does not masquerade as a message, terminal indicators stop correctly, and the completed trail collapses.
- Results Workbench opens automatically and labels current density versus absolute current correctly.
- Closing Agent Kronig succeeds when idle even when completed runs contain prompt-preparation records.
- Active work produces one clear close decision, and any failed lifecycle request still leaves a functioning `Quit anyway` path.
- No SQLite, filesystem, simulator, validation, or lifecycle error is mislabeled as a provider or credential error.
- Every surfaced error includes a stable code, safe explanation, recovery action, and diagnostic ID while secrets remain absent from responses and logs.
- Results Workbench passes recorded scientific correctness, accessibility, responsive-layout, visual-regression, large-data, PDF, and cross-platform acceptance.
- Canonical samples remain immutable and every view transformation is visible, reversible, and documented in exports.
- All focused, full, desktop, and end-to-end test suites pass with recorded evidence.

## 19. Implementation order and commit boundaries

Implement tasks in the numbered order because the later UI depends on the earlier state and contract changes. Use one focused commit per task or tightly coupled task pair. Suggested commit subjects:

```text
test: capture research workflow reliability regressions
feat: distinguish terminal current density and absolute current
feat: validate scientific completeness and model discoveries
fix: validate generic study counts and equivalent axes
feat: persist deterministic experiment plan artifacts
feat: separate research projects from runtime bundles
feat: add exact plan approval and bounded run consent
fix: classify safe research operations without approval spam
feat: add typed canonical bundle inspection
fix: package results rendering without runtime installs
feat: present typed live research progress
feat: add repository-native plan review
fix: repair chat markdown roles and scrolling
feat: present typed research run outcomes
feat: open validated canonical results after execution
feat: add native interactive results and scientific PDF export
fix: make session cleanup complete and desktop exit recoverable
feat: add typed errors and local diagnostic recovery
test: qualify results workbench scientific UX and performance
fix: ground scientific claims and enforce completion integrity
docs: record research workflow reliability acceptance
```

Do not squash away the regression-first evidence during development. Do not commit generated run bundles, credentials, local SQLite databases, or user-specific absolute paths.
