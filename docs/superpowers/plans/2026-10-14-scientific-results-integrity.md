# Scientific results integrity implementation plan

> For agentic workers: use superpowers:executing-plans inline with test-driven development and a final independent review.

**Goal:** Make physics applicability, requested presentation units, and physical validation reliable for arbitrary supported one-dimensional experiments.

**Architecture:** Keep ExperimentSpec simulator-neutral and canonical values in SI. Capture independent validation evidence inside the adapter, evaluate physical relations in shared validators, and project display units only at presentation boundaries. Choose physics during planning with source-backed reasoning, never silently change explicitly requested physics after execution.

**Tech stack:** Python, Pydantic, Pint, DEVSIM, OpenHands, JavaScript workbench and pytest.

## Requirements and design decisions

- No branches on device names, prompt text, geometry, bias ranges or particular numerical examples.
- Preserve existing uncommitted clarification changes. Work on the current feature branch without a worktree. Do not commit or push unless requested; run the entire suite before any future commit.
- Carrier-statistics applicability uses solved carrier densities, recorded effective density of states and local temperature, not substrate doping alone. Explicit Boltzmann selection is retained but out-of-domain results cannot receive an unqualified physical pass. Fermi calculations retain their approximation provenance.
- Intake/planning should recommend supported Fermi statistics when carrier degeneracy can occur under applied bias. Unsupported combinations remain refused, not silently downgraded.
- Canonical SI data remains unchanged. A typed display-unit mapping belongs to the portable spec. Validate dimensional compatibility, then use one projection for plot values, tooltips, tables, CSV/PDF presentation and comparison. Absolute capacitance still requires area; a unit request cannot invent it.
- Poisson, field-gradient, carrier-statistics and integrated charge checks receive required evidence even if the user requests only capacitance or terminal current. Additional evidence is identified as validation evidence, not falsely attributed to researcher requests.
- Integrated charge includes bulk charge, region boundaries, actual interface sheet/trap charge and all terminal charges using documented signs. Check each operating point with existing tolerances, not a global maximum masking low-charge errors. Missing, malformed or incomplete evidence is explicitly reported.
- Mesh verification compares identical physical studies on refined meshes. Retain the refinement input, compiler and simulator provenance, comparable observable metrics and acceptance criteria. No passing claim without an actual second solve; timeout or failure remains visible. Never weaken original validation limits.
- Do not mutate the running user app or its research repository. Live tests use isolated ignored directories and actual configured Bedrock credentials without printing secrets.

## Review focus

1. Explicit Boltzmann requests at high carrier density must not silently become Fermi or pass unchecked.
2. Display units with incompatible dimensions, absolute-versus-density differences, affine conversions and complex data must fail safely or convert correctly.
3. Multi-region duplicate interface coordinates and sheet/trap charge must not be integrated twice or omitted.
4. A failed operating point or refinement cannot be treated as a validated complete sweep.
5. Changes must work with varied region/contact names, multiple study types and both bias directions, not only a MOS example.

## Task 1: Physics applicability and mandatory diagnostic evidence

Files: adapters/devsim/runtime.py, adapters/devsim/compiler.py, validation/statistics.py, validation/physics.py, validation/engine.py, prompting/gateway.py, agent/runtime.py; corresponding unit/integration tests.

- [ ] Write failing tests for diagnostic evidence when observables omit fields, low-density versus degenerate Boltzmann applicability, explicit Fermi provenance, and integrated semiconductor charge with independent hand-derived fixtures.
- [x] Emit diagnostic potential, electric field, displacement flux, bulk charge, carrier densities and local effective density of states at solved points. Preserve centering, units and region/interface boundaries.
- [x] Evaluate statistics and charge balance from canonical evidence with per-point checks. Preserve explicit physics and record out-of-domain model failure distinctly from numerical convergence.
- [x] Add general planning guidance, with no device-name rules, for statistics selection and verification.
- [ ] Run focused physics tests and actual Fermi bias-sweep benchmarks, including the full requested gate range and a differently parameterized study.

## Task 2: Portable presentation units

Files: domain/models.py, results/presentation.py, ide/results.py, web/static/results-workbench.js, reporting/markdown.py, agent/runtime.py; unit, JS and integration tests.

- [ ] Write failing tests for F/m2 to F/cm2, m-3 to cm-3, eV conversion, incompatible requests and unchanged canonical evidence.
- [x] Add typed display_units mapping and dimensional verification using Pint. Produce explicit value projection records from verified spec/result.
- [x] Apply projection to all workbench datasets and exports without altering canonical data or validation inputs. Expose canonical units and conversion provenance.
- [x] Preserve user unit choices from compiled intent into the spec. Validate missing/incompatible presentation requirements rather than silently ignoring them.
- [ ] Run Python and JS tests, including rendered real-result graph selections and exports.

## Task 3: Mesh verification and truthful validation coverage

Files: validation/mesh.py, experiments/service.py, reporting/markdown.py, bundles/models.py and writer.py as needed; unit/integration tests.

- [ ] Write failing tests for mismatched physical inputs, stable/unstable curves, nonconverged refinements and provenance retention.
- [x] Execute bounded refinement and compare approved terminal curves and spatial evidence without changing physics, schedule or acceptance limits.
- [x] Record applicability, residual metrics and mesh stability separately. Missing comparisons stay explicitly unverified, never passed.
- [x] Confirm reports present C-V and requested display units rather than only large current tables.

## Task 4: End-to-end verification

- [ ] Run the original research request through live intake, researcher-like clarification answers, approved plan, real DEVSIM Fermi simulation and Results Workbench payload/rendering.
- [ ] Run a varied layer/bias/unit request through the same pipeline and an explicit Boltzmann out-of-domain case to verify the refusal/warning path.
- [ ] Check independent dQ/dV, capacitance bounds, charge integration, field-gradient, mesh comparison, artifact hashes and exact requested units.
- [ ] Run complete Python suite, desktop/JavaScript suites and lint. Record live timings and any warnings, skips or limitations honestly.
- [x] Obtain final independent code review and address important findings with failing tests first.

## Execution ledger

- Start: preserved eight existing local clarification files. No user session modifications. User explicitly waived approval checkpoints and authorized live API usage.
- Independent review identified material-interface interpolation, omitted series provenance, unrefined automatic profile landmarks, lost original-mesh evidence, incomplete-report failure and failed/complex sample presentation. Addressed each with focused regression evidence. Original and refined files are hashed in the bundle.
- Native Poisson control-volume integration replaces naive double-counting of Dirichlet endpoint source volume. This is discrete Gauss consistency, not a claim that a trapezoidal bulk integral or unrefined solution is accurate.
- Added conditional evidence requirements to the intake schema and early dimensional validation of requested display units. Portable carrier-unit groups expand into electron and hole fields; unknown or incompatible quantities still fail closed.
- A live seven-point explicit Boltzmann study completed numerically, passed mesh checks and was correctly blocked by local statistics applicability at ratio 3.8488 versus the unchanged engineering limit 0.1. Its actual result passed isolated browser unit, profile, zoom/reset, CSV and viewport checks.
- A live varied Fermi study converged all 31 points and passed the second mesh comparison. The dimensionless sweep screen falsely flagged approximately 1e-15 A/m2 roundoff. Added regressions retaining the 1000 outlier limit above the existing current absolute tolerance; below-scale windows are explicitly excluded, not claimed accurate.
- Original 101-point Fermi run required a second refinement and exceeded the old 600-second total budget. Default agent allocation now reserves a bounded 1200 seconds for solving plus mandatory verification; explicit caller budgets remain authoritative. No equations, models, physical inputs or acceptance tolerances were changed to manufacture a passing result.
- Latest focused tests: 183 passed. Desktop tests: 60 passed. Fresh live Fermi reruns and the complete Python suite are in progress. Earlier failed and interrupted attempts are retained as diagnostic evidence, not counted as successful verification.
- Scope freeze after the user's code-growth concern: no further architecture expansion in this pass. Remaining work is live verification, complete-suite results, isolated browser checks and necessary localized corrections only. No commit or push is authorized this turn.
- Final current-code Python suite: 1167 passed, 26 skipped, 6 dependency/runtime warnings, 1082.77 seconds. Desktop: 60 passed. Configured Chromium headless suite: 15 passed. Ruff and diff whitespace checks passed.
- Fresh varied live Fermi workflow passed all applicable checks across 31 requested points, including requested nF/cm^2, cm^-3 and mV display units. Real-result browser interactions and all 42 artifact hashes passed verification.
- The 101-point Fermi/constant-mobility/SRH approved-specification retry completed in 1084.09 seconds. All applicable scientific checks passed, the second mesh comparison met the unchanged 3 percent limit at 2.5502 percent, and all 54 artifact hashes matched. Physical inputs were unchanged. However, the repository-reuse handoff omitted the display-unit mapping and showed canonical F/m^2 instead of retaining F/cm^2. Do not mark end-to-end presentation retention complete.
- At the previous checkpoint, remaining issues were repository unit loss, raw-model provenance mistakes and a refined high-bias Fermi-only singularity. A fresh-symbolic-only trial did not fix the singularity and was removed.
- Targeted follow-up: fixed the bounded reference-reader cutoff and extended the existing native conservation conditioner to retain weak Ohmic anchoring while excluding Dirichlet rows/sources. No new architecture, device-name rules, physics changes or relaxed scientific thresholds were added. Both defects were reproduced with failing tests before correction.
- Two live repository workflows now pass all applicable checks across 101 points each. The Fermi/SRH repeat retained F/cm^2 (952.145 seconds); the final Fermi-only repeat retained F/cm^2, cm^-3 and mV without adding recombination (588.225 seconds). Independent workbench interactions, dQ/dV checks and all 96 artifact hashes passed. The final Fermi-only bundle's adapter hashes match the final source. A mixed-contact regression found by the full suite was corrected by retaining its original assembly path, not relaxing conservation. Raw-model provenance fragility remains separate and is not marked resolved.
- Final narrowed-source verification: complete suite 1169 passed, 26 skipped, 8 warnings in 849.02 seconds; desktop 60 passed; explicitly configured headless UI 15 passed; focused preparation/tool/presentation 162 passed. Both requested defects are resolved and the full-bias Fermi/Klaassen regression remains passing. No commit, push, installed-app replacement or user-session mutation was performed.
