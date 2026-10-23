# Native Source Setup Verification Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, with test-first behavior changes and one independent final review.

**Goal:** Run the actual developer setup on clean Windows and Linux hosts, retain auditable native results, and classify dependencies and installation instructions by operating system.

**Architecture:** Keep shared application pins and one bootstrap. Move simulator Python dependencies into one environment-marked requirements file, constrained by the existing application NumPy pin. Add a source-setup smoke verifier and a non-release GitHub Actions matrix that consumes the same bootstrap rather than duplicating install commands.

**Tech Stack:** Existing Python 3.13, Node 24, pnpm 11.19, GitHub Actions, native Electron backend supervisor, DEVSIM and SQLite knowledge retrieval.

**Spec:** The user's request for clean Windows/Linux setup runs and OS-classified dependency/setup guidance, continuing the already-approved source-setup work. The user opted out of repeated design/approval pauses in this workflow.

## Global constraints

- No scientific equation, ExperimentSpec, prompt or validation-policy changes.
- No new installer, tag, signing secret, provider key or release publication.
- Preserve the existing checkout; no worktree, credential copying or user application shutdown.
- Distinguish real native runner outcomes from path simulations and from visual desktop qualification.
- Keep one shared application dependency list, not hand-maintained copies per OS.
- OS-specific simulator packages use pip environment markers. Linux system libraries remain system prerequisites, not Python requirements.
- Do not label an unavailable native run as passed or hide CI failures.

## Review focus

- Windows native runtime requires MKL discovery in the simulator environment and child PATH propagation.
- Git checkout and executable paths contain spaces in every native source-setup job.
- A second bootstrap must preserve index identity and dependency receipts, not reinstall silently.
- Verifier failures leave a failed evidence record and nonzero exit, never a fabricated passed report.
- CI runs setup without caches of virtual environments or secret credentials and cannot publish releases.

## Task 1: Classify simulator dependencies and verify setup behavior

Files: `requirements/devsim.txt`, `scripts/bootstrap_dev.py`, `scripts/verify_source_setup.py`, `tests/unit/test_bootstrap_dev.py`, `tests/unit/desktop/test_source_setup.py`.

- [x] Add a failing test for platform-marked simulator selection; route bootstrap through that file and include it in the simulator fingerprint without duplicating application pins.
- [x] Add failing tests for proof of repeat-setup reuse and rejection of scientifically invalid/incomplete smoke evidence.
- [x] Implement a bounded verifier that checks pip consistency, native Electron runtime identity, public knowledge retrieval, a real canonical DEVSIM result with passed validation/provenance, and owned native backend startup/shutdown.
- [x] Use temporary run/data directories, sanitized child configuration and a concise OS/architecture/commit evidence JSON. Do not read model credentials.

## Task 2: Native setup jobs and OS-specific guidance

Files: `.github/workflows/source-setup.yml`, `INSTALLATION.md`, `README.md`, `CONTRIBUTING.md`, `docs/operations/devsim.md`.

- [x] Add Ubuntu 24.04, Windows 2025 and current macOS source jobs triggered on main changes, PRs and manual dispatch, with read-only permissions and bounded runtime.
- [x] Install only platform prerequisites; run the actual bootstrap, repeat verifier, existing tests and artifact upload. Linux supplies native desktop libraries. No installer build or release job.
- [x] Document Windows PowerShell and Linux commands separately, including OS math dependencies, shared vs marked Python requirements, launch and update commands, verification command and support limits for older HPC distributions.
- [ ] Run focused tests, the complete local suite and a local native smoke. Obtain one final review, fix important findings test-first, commit and push, then observe actual native Windows/Linux jobs and resolve in-scope failures.

## Execution ledger

Baseline: clean synchronized `main` at `2f53a6b`. Existing release workflow runs only on tags/manual dispatch and installs a different dependency path than the developer bootstrap. Docker daemon is unavailable locally. Public GitHub Actions pages are readable; native setup verification will use hosted OS runners without model/signing secrets.

Ruling: Use one marked simulator requirements file and OS-specific system guidance, not three complete Python lockfiles. Shared pins stay authoritative and OS-only packages remain explicit. Cost: platform-specific transitive packages not present in the Linux lock still need native verification rather than a claim of byte-identical cross-OS environments.

Task 1 implementation: targeted setup/verifier/CI-configuration tests 28 passed. Initial local native verifier passed actual Electron 44.4.5, authenticated workspace rendering, owned backend shutdown, pinned retrieval and a real DEVSIM 2.9.1 bundle with all 38 artifact hashes verified and passed scientific validation.

One independent review found an Important receipt-reuse gap and a diagnostic-loss issue initially labelled Minor. Regraded diagnostic loss Important because it prevents diagnosing native setup failures remotely. Both were reproduced before fixing: same-content receipt replacement now fails reuse verification; failed children retain bounded redacted diagnostics and their stage. No deferred minor finding remains.

Clean-copy verification then exposed an inherited-PYTHONPATH defect: the simulator pip check saw application egg metadata and demanded application packages. A real isolated-venv regression failed first; python_ready now removes PYTHONPATH/PYTHONHOME for its subprocess probe. No simulator dependency or scientific check was relaxed. The full setup/verifier target passes after this fix.

Pinned source inspection found DEVSIM probes libopenblas.so rather than only its versioned soname. Ubuntu prerequisites and CI therefore use libopenblas-dev, matching the existing release workflow and providing the unversioned loader name.

Local test scheduling incident: two numerical suites and dependency compilation overlapped, causing the unchanged 90-second contact-Jacobian diagnostic to time out. The redundant pre-review suite was interrupted gracefully (1,339 passed, 32 skipped before interruption). A later suite also surfaced one failure under this load; its exact result and normal-resource reruns must be recorded before publishing. Do not change timeouts or acceptance assertions to hide contention. Authoritative final local results and actual hosted jobs are pending below.

Final local verification: the earlier loaded suite's single failure was the 60-second real Fermi sidecar fixture timing out. After all overlapping setup/test jobs exited, the complete suite ran with two workers: 1,347 passed, 32 skipped in 610.60 seconds, including both unchanged timeout-sensitive fixtures. No test timeout or scientific acceptance limit changed. Desktop tests: 60 passed. Ruff, changed-file formatting, requirements synchronization and whitespace checks passed.

The clean macOS source-copy run passed bootstrap, unchanged repeat setup, pip consistency, actual DEVSIM import, public retrieval, canonical simulation and validation, backend lifecycle and the new repeat verifier. First bootstrap took 156.95 seconds with existing OS download caches; repeat took 4.03 seconds. The verifier independently confirmed reuse in 4.08 seconds and verified all 38 bundle artifact hashes. This is local evidence, not an estimate for Windows/Linux.

Hosted verification is initiated by pushing this source revision. Actual per-OS outcomes must be observed in the Native source setup workflow before claiming Windows/Linux passed. No visible GUI qualification or certification of older HPC distributions is implied. No model calls, credentials, releases or installers were needed for these checks.

Static audit: strict mypy still reports the existing 268 errors in 21 scientific/runtime source files. This change modifies no production source module and neither hides nor treats that audit as a successful gate.

First hosted run (`39971655004`, revision `0d4bb94`): Linux and Apple Silicon bootstrap and native verification passed; subsequent regression runs exposed a CI-export bug. Resolving the POSIX simulator executable dereferenced the venv symlink and exported the base Python without DEVSIM. A new real-venv test reproduced the incorrect sys.prefix before the fix. The CLI now makes its path absolute without resolving the executable symlink, matching the production simulator registry. Focused setup tests: 29 passed. The complete suite is rerunning through the actual CI exporter before the corrected revision is pushed. Windows bootstrap and native verification also passed and its regression suite is running.

Corrected-exporter verification: the entire suite passed through the actual CI environment-export CLI using the relative sibling simulator path: 1,348 passed, 32 skipped in 672.05 seconds. The new test verified the selected executable's real sys.prefix rather than only its spelling. Ruff, formatting and whitespace checks passed. The corrected revision will trigger fresh native jobs; Windows' first full regression job was still in progress, so its earlier bootstrap/native smoke success is not described as a complete-suite pass.
