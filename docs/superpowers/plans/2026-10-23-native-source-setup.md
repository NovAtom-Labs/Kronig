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

Second hosted run (`39974098407`, revision `762c37c`): all three platforms again passed clean bootstrap and native smoke. Linux and Apple Silicon completed the scientific suite but reported abrupt-process cleanup failures in the pre-existing owner-monitor tests. Repeated local runs initially passed because resuming the monitor raced backend exit. Requiring backend exit before resume made the existing assertion fail deterministically with an owned worker surviving. The monitor's stopped process group became orphaned and POSIX sent SIGHUP followed by SIGCONT, terminating the default-SIGHUP monitor before it could clean up. See the [POSIX exit specification](https://pubs.opengroup.org/onlinepubs/009695299/functions/exit.html).

Bounded lifecycle correction: the independent POSIX monitor ignores SIGHUP before readiness, while EOF and process identity still trigger owned cleanup. The test now forces the previously hidden ordering, preserves the same eight-second cleanup assertion, reports fixture process roles, and tolerates a process exiting between inspection and teardown. Unrelated fixture processes must still remain alive. No scientific source module or Windows ownership policy changes. A fast native shutdown gate precedes the long full suite so a lifecycle defect is diagnosed early rather than after numerical tests. Complete local and hosted re-verification follows.

Lifecycle verification: the deterministic pre-fix test failed with the worker still alive; all 34 focused setup/lifecycle checks passed after the bounded signal fix. The complete suite then passed: 1,348 passed, 32 skipped in 664.65 seconds. Strict mypy remains at the unchanged 268 pre-existing errors. Default clone commands now use the public HTTPS URL, avoiding unnecessary SSH-key setup for a new developer; authorized SSH remains documented as an alternative.

Third hosted run (`39979119340`, revision `ad88801`): Ubuntu Linux and Apple Silicon macOS passed every setup, native-runtime, abrupt-shutdown, complete Python and desktop gate. Windows passed clean bootstrap and native smoke but stalled inside the crash-test fixture, before numerical regression. The fixture previously used an unbounded stdout readline. It now uses a 15-second startup read, retains fixture-only stderr/stage/PID diagnostics, and terminates the exact Windows fixture tree on failed startup. This is test infrastructure, not a claim that the Windows cause is fixed. The local complete suite passed with that diagnostic change: 1,348 passed, 32 skipped in 716.66 seconds. Windows qualification remains pending its fresh run.

Fourth hosted run (`39982652281`, revision `8dafb3d`): the Windows gate now fails promptly with diagnostics. Both normal ownership fixtures establish the monitor and then stall starting the worker; this is not a DEVSIM installation or scientific validation failure. Additional fixture-only worker-stage/launcher diagnostics and a five-second backend/worker stack dump will distinguish child creation, child startup and stdout waiting. No Windows runtime workaround is applied before evidence identifies the blocked operation. The complete local suite passed with diagnostic instrumentation: 1,348 passed, 32 skipped in 637.18 seconds.

Fifth native diagnostic run (`39985541126`, revision `3515a53`): Windows establishes the monitor, creates the worker launcher, then waits for worker stdout; the worker never reaches its Python code while inheriting the same open input pipe read by the owner monitor. Candidate boundary correction: compiled simulation jobs are non-interactive and now receive DEVNULL stdin in both local and packaged runners, never the private lifetime-control pipe. The native crash fixture uses the same input policy without changing its Job Object, cleanup assertions or unrelated-process checks. Two new real-process regressions hold parent stdin open; both timed out before the guard and complete with empty input after it. All 18 targeted runner/lifecycle tests passed. Complete local suite: 1,350 passed, 32 skipped in 599.91 seconds. Native Windows confirmation is still required; no job breakaway flags or scientific acceptance limits were relaxed.

Sixth native run (`39988426199`, revision `26283b7`): Linux and Apple Silicon passed every gate. Windows clean setup, repeat verification and abrupt-shutdown tests passed, confirming the stdin correction. Its full suite then reported five Fermi failures from a missing solver_callback and five ephemeral-session failures from open SQLite handles. The pinned Windows wheel defaults to native MKL and does not automatically import its bundled UMFPACK callback. SQLite's standard context manager ends transactions but does not close connections; retained cycles keep session files locked on Windows. Both failures were reproduced locally before fixing, using a real DEVSIM reset and retained real SQLite connections. The fixes explicitly supply the bundled callback/select custom conditioning, and close each store operation's connection after preserving transaction semantics. No scientific model or acceptance threshold changes. A short callback/session-cleanup gate now precedes the long numerical suite on all OS jobs. Windows confirmation and final complete-suite evidence follow below.

Windows-boundary fix verification: the missing callback and retained-connection regressions both failed before their fixes. Removing the explicit custom-solver selection also made the new real Fermi regression fail; restoring it passes the complete suite. The broad preliminary targeted run was interrupted deliberately after 45 passes to avoid running the same remaining numerical diagnostics twice; it is not counted as a complete-suite pass. Authoritative complete local run: 1,353 passed, 32 skipped in 543.86 seconds, with 9 existing dependency warnings. Desktop: 60 passed. Ruff, dependency synchronization and whitespace checks passed. Strict mypy remains at the same existing 268 errors in 21 files, with no additional errors. The final Windows candidate is pushed next; its native outcome is still pending, not inferred from these POSIX tests.

Seventh native run (`39994125395`, revision `54749c2`): Linux and Apple Silicon passed all gates. Windows passed clean setup, repeat setup, shutdown and the callback/session regressions. Its full suite exposed further platform boundaries: two JS tests exceeded Windows' command-line limit; a completed knowledge lookup retained a SQLite handle, preventing atomic replacement; two test fixtures silently translated LF to CRLF; cancellation reached the correct cancelled outcome but used the POSIX-only dead-PID exception assertion; and the scheduled transport AC dataset was invalid. JS assertions now run from temporary files, fixture bytes are explicit, PID inspection uses the already-installed cross-platform process library, and knowledge search closes its handle. Retaining real lookup connections reproduced the latter locally before its one-line fix. No cancellation policy or raw-source hash semantics changed.

AC investigation: native AC exceptions were previously converted into invalid points without retaining the error. A real injected-failure regression first failed, then passed after bounded native error text was added to solver events. Invalid points remain invalid and validation is unchanged. A short transport AC regression reproduces the first requested adaptive bias point and, only on failure, records a controlled bundled-callback comparison while still failing the default result. The native cause is not assumed before that comparison. Long CI tracebacks now retain the final driver error as well as their header; a failing regression proved the old report dropped it. These platform/AC checks run before the full numerical suite in the next hosted run.

Platform/diagnostic verification: 47 focused checks passed. The short adaptive AC probe passed locally, as did the injected-error evidence test; neither claims the Windows factorization issue is fixed. Complete suite: 1,356 passed, 32 skipped in 448.71 seconds. Desktop: 60 passed. Ruff, requirements synchronization and whitespace checks passed; strict mypy remains at the unchanged 268 errors. The default Windows AC result and its controlled callback comparison will be observed in the early native gate before selecting a numerical correction.
