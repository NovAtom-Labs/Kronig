# Research workbench follow-up verification

## Scope and disposition

Implemented on `devsim-1d-expansion`, preserving the pre-existing working changes. No merge, commit, push, installer rebuild, new worktree, or repository chat memory was introduced in this follow-up.

The changes are contract-driven. Device names and prompt wording do not select product behavior. DEVSIM syntax remains in its adapter. Missing scientific evidence does not become a pass, and recovery does not relax scientific thresholds or silently change physics.

## Implemented recommendations

1. Saved scientific results survive an app restart independently of ephemeral conversations. The repository pane lists full inspectable titles, review reasons, reopen actions, and explicit recalculation.
2. Results and plots require verified manifest identities, artifact hashes, sizes, and workspace scope. Corrupt or out-of-scope bundles are rejected rather than plotted.
3. Recalculation creates a fresh reviewed plan. Opening an old result never starts a simulator or an LLM request.
4. Execution, scientific validation, and requested output coverage are separate assessments. Completed execution can coexist with a scientific warning and complete outputs.
5. Physical checks have explicit applicability. Empty current, charge, carrier, or recombination evidence cannot pass a consistency check vacuously.
6. Check details expose residual units, scales, acceptance limits, and applicability. Bias operating points and AC frequency samples have separate counts.
7. Requested profile points are highlighted without deleting other computed points. Metric labels, units, names, and narrow-layout controls are more readable.
8. Input-ledger categories identify review responsibility. They do not falsely attribute every reviewed setting to the researcher's original message.
9. Recovery proposals contain explicit numerical changes, original bundle identity, unchanged physics digest, and recorded acceptance limits. They require a separate plan review and retain both results.
10. Recovery eligibility is derived from recorded failures. Missing or obsolete validation-policy provenance blocks recovery rather than guessing old criteria.
11. Scientific validation policy has a digest covering its implementation dependencies. Recalculation and recovery do not use unstated contemporary defaults in place of recorded limits.
12. Preparation progress shows actual operation and elapsed work. Repetitive stage summaries are reduced. Terminal work stops active animation. Friendly failures retain inspectable, copyable, redacted diagnostics.
13. Results can open in a separate native window. Scientific PDF export includes the selected view, scientific inputs, validation evidence, and provenance, without chat or application buttons.
14. Native backend ownership is independently monitored. Concurrent restart and close keep cleanup ownership until the owned processes have exited. Cancelled plan approvals cannot start a delayed runtime.
15. Desktop simulator workers remain in the owned process group. Tests cover abrupt owner/backend death, cleanup retry, timeout, startup replacement, and unrelated-process survival.
16. Output-coverage checks reject nonfinite currents and incomplete or reordered DC point coverage instead of reporting false delivery.

## Live native researcher evidence

These used the real Electron development application, the configured live provider, actual clarification and review controls, and DEVSIM. Test evidence is in the repository's `output/` directory. No credentials are included in this report.

### Informal conductor request

A short researcher-style request described a 1 micrometer silicon bar, donor density, ohmic end contacts, three voltages, drift-diffusion, requested fields, and no recombination. The app asked for temperature; the answer was simply `300 K`.

The reviewed unattended run produced three converged operating points, complete requested output coverage, 13 passing checks, zero failing checks, and seven not-applicable checks. Finished animation count was zero. Dataset selection, operating-point selection, zoom, and reset were exercised in the native workbench.

Bundle: `run-9373b9fe86be`. Evidence: `output/followup-native-bar-evidence.json`.

### Restart, saved result, and fresh calculation

The application was closed and restarted. The same scientific bundle reopened from Saved Results with zero restored chat messages and no active agent run. The separate native results window showed the same bundle. Recalculate created a fresh plan without running the simulator until approval.

Expanded plan-ledger and review controls were checked at renderer sizes 1024 x 640, 1280 x 720, and 1920 x 1080. After approval, the fresh run produced a distinct bundle, three converged operating points, complete outputs, 13 passing checks, no failing checks, and seven not-applicable checks.

New bundle: `run-bbbac62bb62e`. Evidence: `output/followup-native-reopened-evidence.json` and `output/followup-native-recalculation-state.json`.

### Asymmetric junction and reviewed recovery

A new request specified unequal silicon region lengths and dopings, three DC biases, ohmic boundaries, drift-diffusion with SRH, and field, charge, carrier, band, and current-density plots. The app asked for temperature and SRH lifetimes. Concise answers were `300 K` and `Both 1 us`.

The initial run completed all three operating points and delivered the requested outputs. Current conservation needed review: the recorded residual was approximately 4.440e-6 A/m^2 against an acceptance limit of 1.049e-6 A/m^2. This is a genuine recorded scientific warning, not an execution failure.

Review finer mesh produced a separate plan with regional spacing reduced from 5 nm to 2.5 nm and the junction anchor from 1 nm to 0.5 nm. Physics, requested points, and all seven scientific acceptance limits were retained. It waited for approval before running and preserved the original bundle and project.

The finer mesh completed but did not clear the warning. Its current-conservation residual was approximately 3.545e-5 A/m^2 against 1.049e-6 A/m^2. The workbench correctly retained Needs review and displayed the recovery comparison. No acceptance threshold was loosened to manufacture success.

Original bundle: `run-eca2507a2c6c`. Recovery bundle: `run-b6b868c0c753`. Evidence: `output/followup-native-junction-evidence.json`, `output/followup-native-recovery-proposal.json`, and `output/followup-native-recovery-evidence.json`.

## Verification and limits

Independent final review identified additional edge cases in policy provenance, ownership, cancellation, and point coverage. These were reproduced with failing regressions and corrected before final verification.

The DEVSIM reference matrix passed nine real solver cases covering selected doping, length, mesh, temperature, low-field bias, and supported model combinations. It is not a full Cartesian matrix and does not certify high-field junction conservation or arbitrary 1D physics. The known DEVSIM charge-constant convention difference is documented, not hidden by relaxing tolerances.

Native UI checks cover resizing, saved-result actions, result controls, labels, graph interaction, and stopped animations. Scientific PDF verification uses real Electron printing with a controlled save destination and inspected two rendered pages. Interaction with the OS save dialog itself was not automated.

macOS development execution and real process cleanup were tested. Linux and Windows native release qualification remains required. Windows Job Object logic is implemented but was not run on a Windows host. Rapidly daemonizing, noncooperative external tools remain an ownership boundary. Existing packaged installers were not rebuilt.

Fresh integrated verification: 872 pytest tests passed, 25 environment-dependent tests skipped, and six dependency/runtime warnings, with real Electron PDF export enabled. All 60 desktop Node tests, eight additional native DOM checks, and nine real DEVSIM reference cases passed. Ruff passed across source, tests, and scripts; scoped mypy passed for four scientific/catalog modules; `git diff --check` passed. Logs are recorded in the implementation ledger.

After verification the QA application was closed, its exact owned process identities were confirmed absent, and the latest source development application was launched again. This updates the development launch, not any previously installed alpha package.

## Publication verification, October 13, 2026

The researcher requested committing and synchronizing the accumulated changes. A fresh fetch found no incoming commits on `origin/devsim-1d-expansion`; the local branch already held four unpublished October 4 commits. The most recent local commit before this publication was `d2de5ae`, October 4 at 20:57 IST. The remote branch was at `1913cb8`, October 1 at 21:48 IST.

Fresh pre-commit verification passed: 872 pytest tests, 25 environment-dependent skips, six warnings, 202.32 seconds, with scientific PDF export enabled; 60 desktop Node tests; 20 explicitly rerun browser-helper tests; Ruff and staged whitespace checks. Secret-pattern and staged-path checks found no credentials or generated runtime artifacts selected for publication. Local `output/` and unrelated `tmp/` renderings remain on disk and are ignored.

The conservation investigation subsequently demonstrated that extended DEVSIM precision removed the recorded mismatch in isolated original-mesh and finer-mesh reruns without relaxing acceptance limits. This is diagnostic evidence only. Production precision controls are not changed by this publication, existing result bundles remain untouched, and platform qualification is still required. The requested synchronization publishes the existing development branch, not a merge into main or an installer release.
