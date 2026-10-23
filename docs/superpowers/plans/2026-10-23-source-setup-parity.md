# Source Setup Parity Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline, with failing tests before behavior changes.

**Goal:** Make the documented clean-checkout setup prepare the current native application, simulator and knowledge resources, then launch through the existing shortcut without redundant installations.

**Architecture:** Extend the existing bootstrap, launcher and atomic knowledge-index rebuild. Keep dependency constraints in their current authoritative files and reuse existing environments and pinned public source checkouts. Do not create another setup framework or copy machine-local state.

**Tech Stack:** Python 3.13, existing pip requirements and constraints, Node 24, pnpm 11.19, Electron, Git, SQLite.

**Spec:** The user's setup-parity request, scoped by the requirements below and the existing `INSTALLATION.md` native-only workflow.

## Global constraints

- Preserve `ExperimentSpec`, simulator equations and scientific validation.
- Support Linux, macOS and Windows paths without claiming unexecuted OS tests.
- Never copy credentials, `.env`, research outputs, existing caches or old environments.
- No installer rebuild, automatic global package installation or destructive cleanup.
- Use existing dependency files, one application environment, one simulator environment and one generated knowledge index.
- Existing source checkouts may be reused only at their declared revision; never overwrite local source changes.
- Keep `Launch Agent Kronig Dev.command` as the macOS convenience shortcut and document the native Linux and Windows launch commands.

## Review focus

- A checkout in a path with spaces must launch without relying on the current working directory.
- A second unchanged setup must reuse dependency stages and the knowledge index.
- A missing Electron binary must be installed despite restricted pnpm build scripts.
- A stale or modified public knowledge checkout must not be silently relabelled as pinned evidence.
- A clean machine must receive the current guides and public DEVSIM resources, not only an empty index path.

## Task 1: Repair the existing setup path

**Files:** `scripts/bootstrap_dev.py`, `scripts/rebuild_knowledge_index.py`, `scripts/run_desktop_dev.py`, `src/tcad_agent/knowledge/models.py`, `knowledge-sources/manifests/sources.yaml`, setup and launcher tests.

- [x] Add failing bootstrap tests for full-lock invalidation, constrained installs, missing Electron installation and platform math-runtime setup.
- [x] Add failing knowledge tests using local Git repositories for exact-revision reuse, refusal of modified sources, first index build and unchanged-index reuse.
- [x] Make the smallest corresponding changes; public fetch targets and index content must follow the existing authorized source manifest.
- [x] Test the actual shortcut from another working directory and confirm no credentials are printed or persisted by setup.
- [x] Verify dependency-file synchronization and installed direct versions; do not upgrade packages merely to change timestamps.

## Task 2: Reconcile public instructions and verify

**Files:** `README.md`, `INSTALLATION.md`, `CONTRIBUTING.md`, `docs/operations/desktop-application.md`, `docs/operations/devsim.md`, development environment template where needed.

- [x] Write one authoritative clean-checkout path in `INSTALLATION.md`; keep other setup introductions short and link to it.
- [x] Separate current source development from older packaged release snapshots.
- [x] Cover prerequisites, one bootstrap command, platform launch shortcuts, Settings, updates, optional tests, disk footprint and non-destructive troubleshooting.
- [x] Remove obsolete persisted-chat, unsupported-physics and browser/folder-picker instructions; preserve historical release notes as history.
- [x] Exercise real setup components in an isolated checkout, repeat unchanged setup, perform a native backend and DEVSIM smoke check, and verify knowledge retrieval.
- [x] Run targeted tests, the complete suite, desktop tests and whitespace/dependency checks. Request one independent final review and record any limits honestly.

## Execution notes

Baseline: `dffb521` on clean, synchronized `main`. The application direct dependency pins already match this machine and `pip check` passes. Setup does not currently prepare its knowledge index. pnpm's script policy can leave Electron's executable absent. Current docs omit the tracked macOS shortcut and contain stale session and physics guidance.

Task 1: complete. Targeted setup, launch, knowledge and retrieval tests: 39 passed. Every added defect was reproduced before its fix, including pip constraints with extras and PEP 440 release spelling exposed by fresh installation.

Ruling: Keep current dependency versions rather than refreshing the Linux lock on macOS. Direct pins already match, and host-specific resolution could change unrelated runtime behavior. Cost if wrong: an independent dependency upgrade must be reviewed later.

Ruling: Preserve the existing strict-mypy baseline rather than expanding this task into scientific/runtime typing refactors. Fresh audit reports 268 errors in 21 files, unchanged from the initial audit. Cost: this work does not deliver a clean global type audit; documentation states that limit.

Final review: one independent read-only reviewer identified three Important findings and no Critical or Minor findings. All three entered one test-first fix pass: deterministic SQLite closure before Windows rename; refusal of ignored indexable source additions; cached health checks for missing transitive dependencies and installed transitive lock drift. Tests observed failing, then passing. A final complete suite is running after those changes.

Ruling: Native Linux/Windows launch and MKL loading cannot be established on this macOS host. Keep explicit cross-platform path tests and document native verification as unexecuted. Cost: platform-native CI remains necessary before shipping new installers.

Ruling: Scientific behavior, published release binaries and existing typing debt are not modified in this setup task. Preserve scientific tests and perform a real DEVSIM smoke run, but do not infer a new release or scientific capability claim from setup success. Cost: users needing a current installer still need a separate target-native release build.

## Clean-install verification

A temporary tracked-source copy in a path containing spaces was prepared without `.env`, existing environments, node_modules, indexes, model credentials or user settings. Temporary application data and environments were removed automatically afterward. Real package downloads/cache reuse and real pinned Git fetches were used, not simulator mocks.

- Final first setup: 134.46 seconds on this macOS host with package download caches available.
- Unchanged rerun: 5.30 seconds; all three dependency stages reused; knowledge index modification time unchanged.
- New application environment: `pip check` passed, including transitive dependency consistency and installed lock-pin checks.
- New isolated simulator: imported DEVSIM 2.9.1 successfully.
- Knowledge query: returned pinned source and official documentation passages with revision/version/hash citations.
- Real `examples/pn-junction.yaml` run: canonical status completed, validation passed, simulator 2.9.1 and provenance manifest present.
- Native supervisor: authenticated backend readiness/health passed; owned process tree stopped successfully. No researcher window was opened or existing app process stopped by this test.
- Actual tracked macOS shortcut: separate regression launches from a different working directory with spaces and no dotenv file. Linux and Windows paths are covered by unit cases, not native OS execution on this host.
- All 60 desktop tests passed. Targeted setup, launch and retrieval checks: 39 passed. Ruff, formatting of changed Python files, dependency synchronization, current-environment pip check, local documentation links and whitespace checks passed.
- Final strict mypy audit: 268 existing errors in 21 files, matching the initial audit. No errors were suppressed.
- Initial full regression run: 1,332 passed, 32 skipped, 10 warnings; isolated CPU-sensitive contact-Jacobian test passed. A complete final regression run follows the last setup-only review fixes.

Warnings are existing Starlette/httpx deprecation, tmux fallback and Pydantic TypedDict ReadOnly notices. No API-cost tests or licensed Sentaurus tests were enabled for this installation-only task. No scientific acceptance thresholds, equations, prompt semantics or device contracts changed.

## Final gate

Task 2: complete. Final frozen-tree suite: **1,337 passed, 32 skipped, 10 warnings in 512.70 seconds**. The unchanged CPU-sensitive contact-Jacobian check ran separately: **1 passed in 42.49 seconds**. Together these cover the entire collected Python suite without dropping the Jacobian check or changing its timeout/assertions. Desktop tests: **60 passed**.

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python -m pytest -q -n 4 --dist worksteal -k 'not test_native_contact_jacobians_match_finite_differences_at_both_endpoints'
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python -m pytest -q tests/integration/test_devsim_fermi_schottky.py::test_native_contact_jacobians_match_finite_differences_at_both_endpoints
pnpm --dir desktop test
.venv/bin/ruff check src tests scripts
.venv/bin/python scripts/sync_requirements.py --check
.venv/bin/python -m pip check
git diff --check
```

The prior full rerun exposed two documentation-contract mismatches, not scientific failures: the installation section heading was restored and the package-homepage assertion was updated to the verified canonical Kronig repository URL. Both were rerun successfully, then the complete frozen-tree suite above passed. No failed check was deleted or suppressed. The independent review has no unaddressed Important findings or deferred Minor findings.

Integration choice: continue the user's already-approved main/synchronization workflow in the existing checkout. No new worktree, branch, merge, release tag or installer is needed for this setup-only change.
