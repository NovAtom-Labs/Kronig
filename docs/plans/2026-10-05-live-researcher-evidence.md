# Native researcher workflow evidence

These are actual Bedrock-driven runs through the development Electron application, not scripted model responses. Prompts live under `evaluations/prompts/`. The selected workspace is `/Users/satyagni/Documents/test`. Its previous contents were archived before testing.

## Evidence conventions

- A completed UI workflow is not the same as a scientifically validated simulation.
- Validation failures remain visible. Failed operating points remain masked in plots.
- DEVSIM outputs, reviewed inputs, compiler version, source hashes, and simulator provenance remain in each result bundle.
- Unit and regression tests supplement, but do not replace, native researcher testing.
- Model reasoning itself is not exposed. The UI shows operational summaries, actual tool actions, elapsed work, and artifact paths.

## Initial two workflows

### Nonuniform implanted silicon transport

Prompt: `native-graded-transport.txt`.

Answers: 300 K; drive the right contact and ground the left; Gaussian standard deviation 0.25 micrometre. An early build unnecessarily asked again about aggregate contact and profile information. Descriptor-level completeness checks were corrected so structured inputs do not trigger redundant presence-only questions.

Outcome: four of four bias points converged. Thirty scientific datasets were available in the in-app workbench. Interactive dataset selection and zoom were exercised. Bundle: `run-09ff1e716c0c`, under `experiments/gaussian-donor-implant-1d-silicon`.

Validation: 13 passed, one failed, six not applicable. Terminal current conservation failed: maximum imbalance approximately 2.96e-6 A/m2 against the configured near-zero absolute tolerance of 1e-6 A/m2. Do not treat this result as fully validated.

### Bias-dependent small-signal capacitance

Prompt: `native-bias-ac.txt`.

Answers: 300 K, 1 MHz, 10 mV, 0.1 V voltage increment. The researcher explicitly requested spatial profiles at -1, 0, and +1 V. Those voltages survived clarification, compilation, and execution.

Outcome: real small-signal AC execution at the requested DC operating points, not metadata-only AC. Twenty of 21 bias points converged, and the uncomputed final point remained invalid. The C-V curve rendered inside the app. Bundle: `run-04d255359017`, under `experiments/mos-capacitor-cv-1d`.

Validation: 11 passed, five failed, five not applicable. Failures covered missing convergence, incomplete small-signal grid, sweep continuity, and terminal current conservation. Maximum current imbalance approximately 9.66e-6 A/m2. A tighter numerical reference rerun recovered all 21 bias points but not the current residual. A global tighter default was rejected because it regressed advanced-physics reference tests.

## Four additional workflows

1. Dielectric frequency response: `native-dielectric-frequency.txt`. All seven logarithmic frequency samples were valid. Capacitance was 0.00172575 F/m2, matching the parallel-plate reference within floating-point precision for this ideal, nondispersive model. Complex admittance and the 90-degree current phase were verified, including native phase selection and zoom. A malformed ancillary provenance label was corrected with a failing regression test. Another test found that frequency count was incorrectly compared with DC bias count; this was fixed. Fresh validation of the unchanged canonical result passes. A further full native fresh-calculation retest, `native-frequency-fresh-rerun.txt`, produced bundle `run-b462155f07ce`: seven valid frequency samples, 14 passed checks, zero failed, seven not applicable. Capacitance, complex phase, dataset selection, zoom, reset, and animation shutdown were verified in the app. No clarification questions or extra permission gates interrupted that final run.
2. Informal conducting-bar request: `native-short-conductor.txt`. Asked only for temperature; answered `300 K`. All three points converged, all requested datasets were available, and 12 checks passed with zero failed and eight not applicable. Current at 0.1 V was twice that at 0.05 V within numerical precision. Native dataset selection, zoom, and reset worked.
3. Informal asymmetric-junction request: `native-short-junction.txt`. Asked only for temperature; answered `300 K`. All three points converged and all requested outputs were satisfied. Thirteen checks passed, one failed, six were not applicable. Current-conservation imbalance was approximately 2.36e-6 A/m2 against a 1.17e-6 A/m2 bound. Results are viewable, but not fully validated.
4. Equilibrium temperature dependence: `native-temperature-study.txt`. The first attempt exposed a legacy current-name mismatch between preprocessing and normalized ExperimentSpec, causing repeated scope refusals. The loop was stopped; alias compatibility and an unambiguous public catalog were corrected with failing tests. A native retest then exposed legacy voltage-only accounting in validation and the Results operating-point table. The canonical temperature points and current maps were already present. After correcting generic operating-point accounting, a fresh native run converged at all three temperatures, displayed all requested profiles, and passed 13 checks with zero failed and seven not applicable. Maximum terminal current density was 6.65e-7 A/m2. Bundle: `run-b447f9446e09`. Temperature selection, terminal-current selection, zoom, reset, and a separate native Results window were exercised. One preparation rerun unnecessarily asked for a nominal temperature despite the supplied temperature list; a further descriptor-driven regression fix removes that redundant question without changing the requested temperature points.

## Native interaction checks

- Clarification draft and keyboard focus survived eight seconds of background polling.
- Clarification and plan actions stayed inside settled 1024x640, 1280x720, and 1920x1080 viewports. Pane transitions need to settle before measuring layout.
- Plan review opened the actual Markdown artifact in the central viewer. Execution was launched through Run unattended.
- No generic permission-to-review-technical-details prompts interrupted the successful post-fix runs.
- Results sections rendered with mixed validation evidence. A failure in one presentation section does not erase the entire workbench.
- Complex result controls are visible. Current phase is labelled in degrees rather than the source admittance unit.
- Result export and popout controls now use compact, themed buttons rather than browser-default controls.
- A scientifically completed result needing review is labelled Results need review in the research trail, not Research blocked. Genuine agent blockers keep their separate state.
- The final temperature Results screen had no page-level horizontal overflow, offscreen export controls, or rendering alerts at settled 1024x640, 1280x720, and 1920x1080 renderer sizes.
- Temperature operating-point selection changed the rendered graph, as did zoom. The current table and maximum-current summary use canonical temperature records instead of falsely reporting zero points or unavailable currents.
- After completion, the research trail had no active animations. Native result popout rendered the same workbench in a second Electron window. Closing the completed main window and reopening the app worked.

## Independent review findings and rulings

One fresh read-only final review reproduced four important defects. These were fixed with failing regression tests before the final verification pass.

- Cancellation after prompt compilation or during runtime creation could start a cancelled run. Runtime admission and Stop now share a lifecycle guard, cancellation is terminal, and callbacks cannot revive it. Pending permission requests are captured before cancellation and denied during cleanup.
- Output traceability could claim missing absolute currents or charge were delivered just because a bias point existed. Matching canonical evidence, contact coverage, valid masks, requested spatial points, and small-signal grid coverage are now required. Current density never substitutes for absolute current.
- Coupled frequency and voltage analyses could share ambiguous start/stop fields. The voltage schedule now has a distinct input scope. Unit-aware completeness and literal-answer lookup use the selected study, not the first matching descriptor in the entire catalog.
- Confirmed automatic profile sampling could disappear or change its count in the executable plan. Scope enforcement now preserves mode, method, count, labels, and explicit values. Automatic selection without researcher authorization is refused.

Numerical ruling: retain current-conservation thresholds and the reviewed solver defaults. Tightening every experiment globally improved one C-V example but regressed advanced-physics references. Neither acceptance limits nor requested physics were silently changed to produce a passing screenshot.

## Verification boundaries

- These are live model-driven examples and reference checks, not a claim that arbitrary 1D requests are calibrated or guaranteed to converge.
- Initial implanted transport, asymmetric transport, and bias-dependent AC examples retain genuine scientific warnings. They are viewable but are not fully validated.
- Native dialogs for choosing a PDF destination were not automated. The PDF action is present and desktop export handlers are covered by tests, but actual save-dialog interaction is not claimed as verified here.
- Results re-opening through every historical standalone file format was not exhaustively tested. Current-run canonical bundles and native popout were exercised.
- No Git push, branch merge, or installer rebuild was requested for this verification pass.
- An optional repeat of the already completed frequency request chose to reuse existing files and attempted to install a plotting package instead of using the native workbench. The installation was blocked by the permission policy and the run was stopped without approving it. This exposes a remaining agent adherence and historical-results reopening weakness, not a simulator limitation. It is not counted as a successful additional workflow. A natural-language explicit fresh-calculation retest is recorded separately.
- That stopped-run retry exposed a malformed SDK tool-use history rejected by Bedrock. A failing regression now verifies that cancelled or failed runs get a clean SDK execution identity, subsequent healthy follow-ups keep that new identity, and the visible chat remains unchanged. Native Stop followed immediately by the fresh-calculation prompt confirmed the same visible conversation and a different SDK execution identity. No package installation was approved.
- The fresh frequency retest also exposed a false scope refusal for the equilibrium baseline. An unbiased AC/frequency calculation already solves and records that baseline. Scope admission now credits this generic dependency only without a separate biased schedule and with common-potential contacts. A biased small-signal plan still cannot claim an unrecorded equilibrium result. Both cases have regression tests.
- Repeated close/reopen QA found a leftover test backend and a concrete concurrent-shutdown race. The specific test processes were terminated after validating their identities. Concurrent shutdown callers now await the same owned-process-tree cleanup promise. The final completed app close removed both Electron PID 37450 and its backend PID 37456. Forced crashes, power loss, and arbitrary OS display scaling are not certified by this check.

## Product improvements identified so far

- Group preparation stages into one concise live status rather than repeating several similarly named request rows.
- Separate execution completion, numerical validity, and deliverable completeness in Results. A single red or amber label cannot explain all three.
- Show a compact reason beside the recent result, with one-click navigation to detailed scientific evidence.
- Keep specific requested profile points highlighted, but retain all computed points for further exploration.
- Offer explicit numerical-recovery proposals when convergence fails, with input and provenance comparison. Do not silently alter the user's physics or numerical acceptance limits.
- Display near-zero conservation residuals with their units, absolute tolerance, and scale; a generic failure count is insufficient for scientific interpretation.
- Improve the minimum font size and hierarchy for scientific units, structure ranges, and validation measurements. Avoid adding decorative cards that displace the graph.
- Make result names and contact labels inspectable without truncation, especially at narrow pane widths.
- Add an input-review ledger that clearly separates user instructions, derived values, reviewed model choices, and numerical defaults before approval.
- Provide an explicit recovery choice after a numerical failure: refine mesh, adjust the approved solver settings, or stop. Show changes against the original inputs and preserve both result bundles.
- Keep numeric progress honest. Show elapsed inference time and actual tool/artifact updates rather than invented percentages or fabricated thought text.
- Show a compact friendly error first, with a separate copyable technical diagnostic. SDK support instructions and internal session paths should not dominate the scientific research trail.
- Distinguish DC operating-point count from small-signal frequency-sample count in the Results header and grid table.
- Give validators explicit applicability rules. A check with no relevant physical evidence should be not applicable, not a reassuring green count based on an empty collection.
- Further harden abnormal termination with independent ownership monitoring, particularly before any future real-hardware integration. Graceful concurrent cleanup was tested here; it is not a real-time safety controller.
- Expand scientific reference coverage across doping, bias, mesh density, temperatures, and model combinations before extending the maturity claims of advanced physics.
- Make verified historical result bundles directly reopenable through a product action, without repository conversation memory. Offer a clear Reopen results / Recalculate choice. Do not require the agent to improvise HTML plots or install plotting libraries to inspect existing evidence.

## Short prompts you can repeat

These are intentionally researcher-facing, not instructions mentioning internal contracts or tools.

### Conducting silicon bar

> Check a 1 um silicon bar, n doped 1e15 cm^-3, ohmic ends. Left ground, right at 0, 0.05 and 0.1 V. Plot current density, field and carrier profiles. Doping dependent mobility, drift diffusion, no recombination needed. Ask if you need anything else.

Temperature answer: `300 K`.

Expected: three operating points, carrier and field profiles, and a current-density curve. In the tested small-bias setup, doubling voltage doubled current density within numerical precision.

### Asymmetric junction

> Make a 1D silicon pn study. Left 0.6 um p=3e16, right 0.9 um n=7e16, cm^-3. Ohmic ends, right grounded. Bias left at -0.2, 0, 0.15 V. Need band bending, carriers, field, charge and current density in the app. Use SRH and drift diffusion. Don't guess missing settings.

Temperature answer: `300 K`.

Expected: three operating points, band diagrams and carrier/field/charge profiles. The actual tested result had a small current-conservation failure, which must remain visible.

Question wording and the number of necessary questions can vary with the model and repository context. The software checks whether required scientific inputs and the executable plan remain complete; these prompts are not matching rules in production code.

## Final verification

- Complete offline/reference suite after the final equilibrium-baseline fix: 788 passed, 20 skipped, six dependency/runtime warnings, 140 seconds. Log: `output/complete-suite-final-baseline-fix.log`.
- Optional actual Electron DOM regressions: three passed. Log: `output/native-dom-final.log`.
- Native desktop lifecycle/export/security tests, including concurrent process-tree cleanup: 46 passed. Log: `output/desktop-delivery-tests.log`.
- Ruff checks passed and `git diff --check` passed.
- The skipped tests include opt-in environment-dependent checks. The actual Bedrock researcher runs described above were performed separately; a skipped opt-in test is not counted as a live API pass.
- No claim is made that every scientific run passed validation. Each run's numerical result and failed checks are reported above.
