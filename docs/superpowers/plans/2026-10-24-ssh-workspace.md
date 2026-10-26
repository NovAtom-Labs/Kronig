# SSH workspace implementation plan

> **For agentic workers:** Use superpowers:executing-plans. Preserve the existing
> feature branch. No worktree, merge to main, or implicit push.

**Goal:** Keep Kronig/OpenHands local and provide approved remote repository work
and native simulator execution through existing HPC SSH access.

**Architecture:** Generic remote file/terminal tools are separate from simulator
adapters. ExperimentSpec and canonical results stay simulator-neutral. No remote
application server, modern Python or browser installation is required.

**Tech stack:** Existing Python/OpenHands desktop backend, SSH/SFTP and HPC tools.

**Spec:** The SSH workflow agreed in this conversation: inspect, edit, execute,
monitor, repair and retrieve results, with scoped remote permissions.

## Global constraints

- Preserve main's cancellation, results and validation safeguards.
- Reject unknown/changed server keys. Never globally enable legacy algorithms.
- No hidden desktop password prompt or global password persistence.
- No repository credentials or proprietary documentation.
- Local simulation approval does not grant remote or destructive access.
- An SSH working directory is not a remote-shell security sandbox.
- Keep native syntax in adapters; never branch on named devices.
- Licensed-host benchmarks are required before claiming Sentaurus qualification.

## Review focus

1. Unknown/changed server keys fail before commands run.
2. Missing authentication fails without invisible prompts.
3. Paths and symlinks cannot expand an approved file scope.
4. Disconnection is not proof of remote-job termination.
5. Missing exporters cannot produce guessed scientific results.

## Task 1: Rebase and verify

- [x] Fetch/fast-forward SSH branch, then rebase its three commits onto main.
- [x] Resolve overlaps while retaining SSH audit and latest main behavior.
- [x] Repair inherited dependency mismatch without unrelated lock changes.
- [x] Run full Python/desktop suites, dependency, lint and whitespace checks.
- [x] Record tested local state. Do not force-push shared branch history.

## Task 2: Authentication foundation

Files: `src/tcad_agent/runners/ssh.py`,
`tests/unit/runners/test_ssh_audit.py`, `docs/operations/sentaurus-integration.md`.

- [x] Write failing tests exercising real Paramiko missing-host policy and key/agent
  authentication without getpass or password-environment mutation.
- [x] Keep `_connect() -> paramiko.SSHClient`, load known hosts, use RejectPolicy,
  permit existing key/agent authentication and optional explicitly supplied password.
- [x] Verify RED to GREEN, document trust setup and run the full suite.
- [x] Reproduce and fix audit lookup against the current workspace storage layout.
- [x] Reproduce and fix inherited stale result reuse, missing mandatory failure logs
  and fractional budgets accidentally disabling the remote timeout.

## Task 3: Remote agentic workspace

Not delivered by the initial rebase/authentication increment.

- [ ] Bind an explicit approved host, root and remote session identity.
- [ ] Add list/read/create/edit/upload/download with physical path containment,
  bounded reads, binary transport, content hashes and conflict-aware writes.
- [ ] Add bounded concurrent stdout/stderr, timeouts, job identity, output polling
  and verified cancellation, including connection-loss handling.
- [ ] Connect typed OpenHands tools, scoped approvals and truthful activity events.
- [ ] Add native connection controls and remote file/terminal views.
- [ ] Test isolated SSH lifecycle and denied paths, conflicts, output floods and stop.

## Task 4: Native simulator workflow

- [ ] Bind site environment, exact executables, scheduler and license policy.
- [ ] Generate/transfer structure, mesh and device inputs through adapters.
- [ ] Monitor real jobs, preserve errors, support approved repair/rerun loops.
- [ ] Export with existing authorized HPC utilities, retrieve/hash evidence,
  normalize deterministically and open the local Results Workbench.
- [ ] Qualify licensed golden runs before enabling advertised capabilities.

## Execution record

2026-10-24: Started clean at main 3f4d132. Remote SSH tip bf0c043 has three
commits, rebased locally as 4034348, 26c7631 and da17d51. No push or main mutation.

The lock now preserves main's platform closure plus Paramiko 4.0.0 and its three
additional dependencies. No resolver upgrade or unrelated dependency change.

Independent read-only review confirmed preservation of main's cancellation,
bundle staging/cancellation checks and current agent operations. It identified
three inherited bridge defects: stale artifact reuse (P1), absent mandatory logs
(P2), and subsecond timeout truncation (P2). Each was reproduced RED and fixed
GREEN. A unique local run directory preserves previous evidence rather than
deleting it. Remote shell diagnostics are retained if SFTP logs are absent.

Ruling: keep the explicitly configured legacy TCAD_WORKSPACE audit location for
CLI compatibility, but default to RuntimePaths for the selected desktop workspace.
Its regression test failed before the change and passed after it.

Remote REPL, stream draining, verified remote cancellation, mesh/export, scheduler,
SSH-config/MFA and licensed qualification remain Tasks 3-4. This increment does not
claim them implemented or production qualified. No live HPC credentials were used.

Final verification on this Mac: full Python suite 1,381 passed, 32 skipped,
6 dependency warnings in 1,135.90 seconds. The focused integration set passed
114 tests; desktop Node tests passed 61/61. Ruff, requirements synchronization
and git whitespace checks passed. Earlier interrupted exploratory suite runs
were superseded by this complete final-source run, not counted as passing proof.

Live HPC access remains unverified: the supplied hosts timed out before SSH
authentication. Local host-scoped OpenSSH configuration was prepared outside the
repository. No host fingerprint was trusted automatically, no HPC software was
installed and no port forwarding was enabled. Joining the correct network still
requires a usable owner invitation and successful authorized sign-in.
