# Research workbench follow-up implementation plan

> For agentic workers: use test-driven development and independent subsystem execution. Every behavior needs a failing regression, targeted verification, and full-suite verification before any commit.

Goal: implement the product recommendations identified in native researcher testing without adding device-specific behavior, repo conversation memory, or silent scientific changes.

Architecture: verified canonical bundles remain the scientific source of truth. A workspace-scoped results catalog survives app sessions independently of chat. Presentation separates execution, scientific checks, and requested output coverage. Recovery is a reviewed new experiment, never mutation of prior evidence. Native backend ownership is supervised independently of graceful UI shutdown.

Tech stack: Python, FastAPI, Pydantic, DEVSIM, browser JavaScript/CSS, Electron, existing pytest/Node/native automation.

Spec: `docs/plans/2026-10-05-live-researcher-evidence.md`, Product improvements identified so far.

## Constraints

- Work on the existing branch and preserve existing dirty edits. No worktree, merge, push, installer build, or credential output.
- ExperimentSpec is simulator-neutral. No device-name or prompt-text matching rules.
- Reject unsupported physics. Do not change validation thresholds to obtain passing results.
- Retain all computed points, highlight requested points, preserve source hashes and old bundles.
- Operational progress is actual status and events, not private reasoning or invented percentages.
- No repo conversation memory. Historical result access is verified scientific artifact access only.
- No new remote services or proprietary manuals. Native desktop remains primary, Linux and Windows logic must remain portable.

## Review focus

1. Closed and reopened app: scientific results must reopen without a chat record.
2. Corrupt, symlinked, or outside-workspace bundle: reject it and never use unchecked JSON for plots.
3. No current, charge, or recombination evidence: no vacuous passing physical checks.
4. Recovery: approved physics and scientific tolerances remain unchanged; both prior and new bundle identities survive.
5. Abrupt Electron death and concurrent restart/close: no orphan backend process tree or stale ownership.

## Task 1: Verified results catalog and explicit actions

Files: `ide/results.py`, new `ide/result_catalog.py`, `web/ide_routes.py`, `web/static/ide.js`, result-reader/API tests.
Interfaces: workspace-scoped catalog entries keyed by verified bundle run ID; GET workspace saved-results and GET saved-result view, never requiring an AgentRun. Recalculate starts a normal reviewed agent request, no implicit execution.

- [x] Write and run failing tests for persistence without chat, corrupt-bundle exclusion, traversal refusal, and reopened dataset access.
- [x] Implement bounded managed-bundle enumeration and verification; include friendly integrity errors, not silent success.
- [x] Expose Reopen results / Recalculate controls and full-name inspection in the repository pane; add agent guidance to reopen using the product rather than installing plotting libraries.
- [x] Verify API, JS behavior, native reopen after restart, and live recalculation.

## Task 2: Scientific status, applicability, recovery, and reference coverage

Files: validation modules, new recovery proposal service, scientific reference tests. Avoid frontend files and `web/ide_routes.py` owned by Task 1.
Interfaces: deterministic result assessment separating execution, numerical status, and output coverage; typed recovery proposals contain changed numeric/mesh fields, original spec digest, preserved physics, and unchanged scientific acceptance limits. No automatic rerun.

- [x] Reproduce empty-evidence physical checks and write failing applicability tests.
- [x] Implement explicit applicability plus residual units, scale, and tolerance evidence.
- [x] Implement reviewed numerical recovery proposals and immutable comparison provenance; use existing ExperimentSpec rather than device presets.
- [x] Add independent reference matrices over doping, length/mesh, bias, temperature, and supported model combinations. Report actual calibration boundaries.
- [x] Run complete scientific validation and reference suites.

## Task 3: Results and research-trail presentation

Files: `web/static/results-workbench.js`, `ide-agent.js`, `ide.css`, their JS/DOM tests. Do not edit `ide.js` or routes owned by Task 1.
Interfaces: consume existing verified view, canonical operating points, input provenance and validation checks. Add pure presentation helpers where testable.

- [x] Write failing tests for three independent status dimensions, distinct bias/frequency counts, empty checks, and meaningful residual details.
- [x] Improve typography and inspectable names/units while preserving graph area and narrow-layout controls.
- [x] Present input ledger by provenance, requested profile highlights and recovery choices without changing science.
- [x] Collapse repetitive preparation stages; actual current operation, elapsed inference/tool work, completed artifacts, and friendly error with copyable diagnostics remain visible. Animations only during active work.
- [x] Verify native resize, labels, selection, phase, zoom, reset, and terminal animation shutdown.

## Task 4: Native ownership and export verification

Files: `desktop/src/backend-supervisor.js`, desktop server/lifecycle modules, desktop lifecycle/export tests. Avoid scientific and frontend files.
Interfaces: backend is owned by exactly one Electron process; an independent owner-loss monitor stops the backend and its owned workers. Concurrent shutdown retains cleanup ownership until confirmed exited.

- [x] Write and run failing tests for abrupt owner loss, restart while stop is pending, failed cleanup retry, and child-worker cleanup.
- [x] Implement portable owner supervision and idempotent shutdown, without killing unrelated processes or storing credentials.
- [x] Verify scientific PDF export contents and native save-path bridge behavior without claiming unavailable OS UI checks.
- [x] Run desktop tests and actual native lifecycle smoke checks.

## Task 5: Integration and delivery evidence

- [x] Integrate independently verified subsystems and run full pytest, JS, desktop, lint, and diff checks.
- [x] Run live researcher workflows through the native app, including one informal request, results reopen, and an explicit fresh calculation. Do not clear the existing test repo or alter scientific tolerances.
- [x] One fresh independent final review; fix important defects with red-green tests.
- [x] Update this ledger and the Downloads evidence report with exact passes, failures, scientific warnings and unverified platform boundaries.

## Execution ledger

Pre-flight: Task 1 owns catalog routes and ide.js; Task 2 owns scientific assessment/recovery; Task 3 owns workbench/trail/CSS; Task 4 owns lifecycle. Root integrates their exported interfaces. No conflicting file ownership.
Ruling: retain changes locally until explicitly asked to commit/push, because this request asks implementation and the existing large dirty tree includes prior work. Cost if wrong: a separate commit/push step.

## Completion evidence

- Fresh full suite with real Electron PDF export enabled: 872 passed, 25 environment-dependent skips, six dependency/runtime warnings, 202.42 seconds. Log: `output/followup-final-verified-suite.log`.
- Desktop Node suite: 60 passed, zero failures. Log: `output/followup-final-desktop-node.log`.
- Fresh native workbench and saved-result DOM suite: eight passed. Log: `output/followup-verified-native-dom.log`.
- Real DEVSIM transport reference matrix: nine passed. Log: `output/scientific-reference-matrix.log`.
- Ruff across source, tests, and scripts passed; scoped mypy passed for four scientific/catalog modules; `git diff --check` passed.
- Actual live provider/native workflows covered informal prompting, concise clarification answers, reviewed unattended execution, interactive graphs, application restart without chat restoration, saved-result popout, fresh recalculation, and reviewed numerical recovery.
- The asymmetric junction completed with full output coverage but a current-conservation warning. Finer-mesh recovery preserved both bundles and unchanged thresholds but did not resolve the warning. This is explicitly retained, not presented as a scientific pass.
- Independent review findings were fixed with failing-first regressions. Native Windows/Linux release qualification and noncooperative detached-tool ownership remain boundaries. No installers were rebuilt and no changes were pushed.
- Detailed evidence: `docs/plans/2026-10-05-followup-verification.md`, with a copy in Downloads/Agent Kronig Fixes.
