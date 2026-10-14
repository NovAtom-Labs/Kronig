# Fermi Klaassen Convergence Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkbox tracking. Preserve the existing dirty worktree and do not create another worktree or publish without a request.

**Goal:** Execute the original Schottky, Fermi, Klaassen, SRH 1 microsecond, Auger and Slotboom request at equilibrium and both 2 V polarities, with full scientific validation and interactive canonical results.

**Architecture:** Keep ExperimentSpec unchanged. Correct inconsistent statistical primitives inside DEVSIM, and solve carrier densities in positive logarithmic coordinates. Preserve weak physical source terms using an equivalent integrated continuity row with a data-derived pivot. Bound Newton directions without changing physical equations or final density convergence thresholds.

**Tech Stack:** DEVSIM 2.9.1 native extended model/equation evaluation, existing custom UMFPACK callback, Python, pytest, canonical ValidationEngine and result workbench.

**Spec:** This plan implements the user's latest Schottky Fermi Klaassen request and the engineering rules in AGENTS.md.

## Global Constraints

- No device-name branching, silently dropped models, invented physical area, changed doping, lifetimes, contact work functions or requested voltages.
- No relaxed scientific checks, manufactured zero residuals, hardcoded result fields or substituted simulation outcomes.
- Keep native potential convergence errors and actual per-node density update norms. Require both original global absolute and relative convergence limits.
- Numerical predictors alter starting guesses only. Retain native model-to-model checkpoints and restore every failed trial.
- Do not commit secrets or proprietary documentation. Record runtime/compiler/statistical-kernel versions and source provenance.
- Full test suite and an original live-API researcher workflow are required before completion claims. A prototype passing does not complete a task.

## Review Focus

1. Interfaces and contact endpoint orientation must conserve the original signed finite-volume balance, including every source term.
2. Equation numbers change after Poisson-only initialization: obtain them only after full assembly, and never cache stale indices.
3. A weak minority row is a bad conservation-row pivot: choose a physical row by actual matrix diagonal strength, not region or device labels.
4. New statistical branches must be continuous, differentiable, monotone and independently benchmarked against the normalized Fermi integral.
5. Partial convergence or failed scientific checks must remain failures with diagnostic results, never turn into successful-looking plots.

## Evidence and Decisions

- Native InvFermi has mismatched Joyce and Sommerfeld constants, a discontinuity near density ratio 8.46296 and a high-branch derivative inconsistent with its value. Native forward Fermi does not reliably invert that discontinuous function.
- Independent quadrature of the corrected Joyce-Dixon approximation gives sampled forward-density error below 0.22 percent and derivative error below 0.62 percent over the tested domain. This remains an approximation and must be identified as such.
- Native extended assembly is exported as a double CSC matrix to UMFPACK. In a measured diagnostic, the exported hole common-mode anchor differs from independent source/contact terms by 47.8 percent. Accurate LU backward residuals do not prove an accurate physical Newton direction here.
- The integrated carrier row is an exact algebraic row combination in exact arithmetic, not new physics. Prototype verification must prove RHS, Jacobian, interface and source equivalence before promotion.
- The midpoint minority pivot caused huge local corrections. The maximum-diagonal physical pivot removes that diagnostic construction defect.
- A bounded native Newton solve is preferable to the expensive prototype line search if the complete original validation suite passes. Numerical execution budget is not a scientific validation tolerance, but retain the original 300 second native regression target first.

### Task 1: Statistical primitives and independent references

**Files:** Create adapter-owned `statistics.py`; modify runtime statistics construction and parameter provenance; add unit and native integration benchmarks.

**Interfaces:** `inverse_fermi_expression(ratio, derivative=False)` returns native syntax; `fermi_models(prefix, eta)` returns named forward and analytic derivative models. Runtime must use the same statistical relation in initialization, contacts, transport, recombination, bands and extraction.

- [x] Add red tests for branch continuity, analytic derivatives, positive monotone forward inversion, independent quadrature accuracy, native expression evaluation and low/high degeneracy limits.
- [x] Implement matched Joyce-Dixon/Sommerfeld constants with guarded inactive branches. Use a positivity-preserving forward inversion with verified residuals.
- [x] Build model dependency derivatives explicitly, including contacts and interface projections. Do not rely on undocumented derivative expansion through named model references.
- [x] Verify unit/native tests and independently reference the approximation's measured accuracy in provenance.

### Task 2: Conservative positive-density solver

**Files:** Create adapter-owned `density_solver.py`; modify runtime initialization, DC solves, checkpoints and compiler packaging; add pure CSC and native solver tests.

**Interfaces:** A solver object transforms density unknowns, captures native physical update norms, optionally rebuilds an integrated continuity row, bounds a Newton direction using the thermal scale and exposes a DC solve method. It receives device, physical contacts, region topology and solver limits from the compiled payload, never a device label.

- [x] Add failing tests for original-unit convergence, invalid evidence, strict equality rejection, positivity, row replacement equivalence and stale equation-number refresh.
- [x] Transform n and p to thermal-scaled logarithmic unknowns, regenerate all chain-rule derivatives and interface constraints, and rebind equations by deleting old mappings first.
- [x] Assemble integrated generation and outward boundary flux directly from native individual models. Include all volume and contact signs. Apply only where boundary and interface semantics prove the equivalent row combination; otherwise use the ordinary conservative solver path.
- [x] Choose the strongest eligible physical pivot from the actual assembled matrix. Preserve sparse index types and other rows exactly.
- [x] Capture native prior densities before each update; final acceptance uses actual per-node density changes plus untouched native potential errors, both original strict limits.
- [x] Bound trial steps by thermal voltage and apply a native harmonic predictor for changed end voltages where topology permits. Predictors do not authorize altered physics or earlier acceptance.
- [x] Verify complete native fields and conservation at the original 5 nm mesh and 1 microsecond lifetimes, with no xfail or conditional success.

### Task 3: Product integration and scientific results

**Files:** Runtime, compiler, manifest, curated statistical guidance, integration tests, verification notes and results-workbench checks.

- [x] Package every adapter helper into compiled workspaces and include all bytes in runtime provenance. Bump compiler version only when behavior is actually verified.
- [x] Test mixed/ohmic boundary regressions, asymmetric doping, another temperature and mesh refinement. Preserve dynamic-study capability gates until separately benchmarked.
- [x] Re-run the exact live-API prompt and researcher clarifications; ensure no area is invented and all requested physics and outputs remain present.
- [x] Validate current conservation, field/potential consistency, recombination, positivity, band and quasi-Fermi consistency. Confirm all requested biases and interactive dataset axes, units and labels in the workbench.
- [x] Run full Python suite, desktop tests, formatting/lint and fresh independent review. Keep numerical diagnostic limitations visible until all required tests pass.

## Progress Ledger

Chronological observations below include intermediate failures. The final entry records completion.

- Initial exact native regression: failed after 300 seconds (`output/exact-convergence-red.log`).
- Statistical primitives and density controller are wired into compiled workspaces, included in the composite runtime hash and identified as compiler 0.2.4.
- Native full schedule completed in 238 seconds. Canonical normalization and all 12 applicable validation checks passed with the unchanged policy digest. The original test helper had unvalidated string observables; its revalidated schema now exercises the full validator rather than failing before checks.
- Independent statistics value/slope and unscaled physical acceptance tests pass. Graph manufactured-field and carrier cross-Jacobian regressions pass after replacing obsolete incorrect-native golden values with independently evaluated matched references.
- Fresh review found a Fermi gate predictor regression: temporary Poisson equations entered the carrier certificate, and raw density cache writes did not initialize coordinates. Native readiness dispatch, callback bypass and explicit coordinate reset fixed it; the actual native regression was red then green in 9.85 seconds. Dataset primitive provenance was corrected too.
- Adaptive full-statistics initialization replaced 49 fixed steps. It ends only at blend 1, backtracks native nonconvergence and never accepts partial statistics. Its failure/backtracking tests are green.
- Live original researcher workflow resolved one clarification batch and prepared all requested physics, then timed out at the 300-second simulator limit. Its junction refinement produced 2,424 equations rather than the passing benchmark's 1,206. It was progressing toward the final reverse-bias point, not refusing physics. The exact approved specification is being rerun with a diagnostic 600-second budget to distinguish resource exhaustion from numerical failure.
- The complete Python suite is running; the regular full-bias native regression has passed in that run. Completion still requires the exact live specification's results and actual result-workbench evidence; no publication has been requested.
- The refined exact specification completed all three points and passed 15 applicable checks. Actual canonical data rendered as 33 interactive datasets with all selection/zoom tests passing. Complete suites passed 1,075 and 1,076 tests; desktop tests passed 60.
- A further live plan selected a fixed grid and its initial direct -2 V jump failed. Fixed reported points now use recorded, thermal-scaled internal starting-state continuation in the positive-density path, without changing the requested grid or original acceptance. The native full fixed-grid regression passed in 210.56 seconds. The exact failed specification is being replayed, and the final full suite includes the change.
- The single-level guard now refuses averaging split quasi-Fermi levels under driven carrier transport. Shared stationary carrier reservoirs, including electrostatic dielectric gating, remain supported. The four new boundary/quantity scope tests pass.
- Exact failed fixed-grid specification replay passed in 223.28 seconds with all 15 applicable checks and all 27 outputs. Final live-API workflow passed in 340.08 seconds with one clarification batch and 16 applicable checks. Its actual API result rendered 31 graphable datasets with all selection/zoom tests passing and no renderer errors. Only the fresh final complete suite remains pending.
- Complete suite passed 1,084 tests with 25 skips. Additional asymmetric physical regression passed in 46.04 seconds. Final delta review found a metal-on-dielectric gate wrongly counted as a carrier injector; adjacent-material classification and schema-valid ideal/metal gate regressions fixed it. All 947 unit tests passed after that fix, with 9 skips. Desktop tests passed 60, lint and diff checks passed. All implementation targets are complete. Source publication is requested on devsim-1d-expansion; no main-branch merge, installer rebuild or automatic user-app restart is included.
