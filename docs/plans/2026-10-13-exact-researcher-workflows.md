# Exact researcher workflows and latency implementation plan

> For agentic workers: use test-driven development and executing-plans. Keep independent numerical and presentation work scoped to their own files.

Goal: verify the user's exact forward/reverse 2 V junction and -5 to +5 V MOS C-V requests through live preparation, researcher answers, agent planning, actual DEVSIM execution, verified results, and presentation. Correct root causes of delay, numerical failures, and review UX, then test additional previously discussed requests.

Architecture: use the existing simulator-neutral ExperimentSpec, prompt-preparation service, OpenHands supervisor, API routes, and canonical workbench. A headless researcher driver calls those real interfaces rather than constructing a spec to bypass agent behavior. Record stage durations and call/action counts. Fix numerical accuracy within the adapter and retain unchanged scientific acceptance limits. Use headless renderer checks for presentation and only use the native window if necessary.

Tech stack: existing Python, pytest, FastAPI TestClient, live Bedrock, OpenHands SDK, DEVSIM, JavaScript and optional Playwright.

Spec: this document and the user's October 13 request, plus AGENTS.md engineering rules.

## Global constraints

- Work on devsim-1d-expansion from f7bc6d1. No worktree, main merge, installer build, automatic push, or credential output.
- User approves implementation and test-run approvals. Do not pause to request more approval. Test harness grants only scoped local scientific plan execution, not arbitrary network/install/system actions.
- Interpret this test's oxide as 10 nm by explicit user direction, not by a production typo rule.
- Original junction context is supplied in a researcher context file: Al / p-Si / n-Si / Al, 300 K, both dopings 1e17 cm^-3, work function 4.10 eV, Fermi statistics, mobility, SRH, Auger and BGN, and original requested outputs. Dimensions/contact boundary choices remain researcher clarification answers.
- No production matching on device names or sample prompt text. No silent missing-input choices or physics substitutions.
- Keep initial failed runs and diagnostic evidence. Do not change validation limits to create a pass. Tests do not certify arbitrary 1D physics.
- Do not clear the user's existing test folder. Use isolated evaluation folders and managed run storage.

## Review focus

1. Repeated clarification or repair loops must preserve explicit answers and end with a meaningful bounded outcome.
2. A reference to a prior problem must actually consume supplied context rather than invent its parameters.
3. Precision mode must be explicit and recorded, with no silent unsupported-platform fallback.
4. Large review content and plot controls must remain usable at small viewport sizes without focus loss or overflowing actions.
5. A converged solver result with missing or inconsistent output cannot be labelled scientifically validated.

## Task 1: Isolated live researcher evidence and latency

Files: new scripts/verify_live_research_workflows.py, evaluations/prompts, tests/e2e/test_live_research_workflows.py, targeted prompting/supervisor regressions as defects are reproduced.

Interfaces: existing IDEServices, AgentSupervisor, create_app API, PromptPreparationService and OpenHandsRuntimeFactory. Driver records prompt, answers, stage times, statuses, plan/bundle identities, validation checks, dataset and operating-point coverage.

- [x] Reuse the real live-provider setup and add deterministic driver answer-routing regressions without bypassing clarifications or plan review.
- [x] Run both exact prompts with concise researcher answers and record baseline timings/errors.
- [x] Reproduce identified preparation/agent delay loops with failing tests; fix generic cause and retest.
- [x] Run additional concise graded-profile, finite-frequency AC, and temperature requests through the same pipeline.

## Task 2: Accurate numerical execution

Files: adapter runtime/payload/compiler, domain SolverControls if required, solver/reference tests. Task 2 owns these files; root does not edit them concurrently.

Interfaces: validated numeric controls in ExperimentSpec -> adapter payload -> native solver settings -> canonical provenance. Existing validation limits remain unchanged.

- [x] Pin the demonstrated standard-precision conservation failure with a failing real solver regression.
- [x] Introduce general explicit higher-precision execution with fail-closed availability and recorded provenance.
- [x] Verify original/finer mesh junctions, actual +/-2 V ohmic reference context, complete -5..+5 V MOS points, and advanced Fermi/BGN reference cases. Original Schottky/Fermi combination still refuses; no silent substitution or acceptance weakening.

## Task 3: Presentation and whole-workflow verification

Files: existing web/static presentation helpers/styles and headless UI tests only when a concrete defect is reproduced. Keep file ownership separate from Task 1 backend work.

- [x] Exercise clarification/plan/result rendering headlessly with actual workflow payloads and small/large layouts.
- [x] Fix concrete focus, sizing, state/progress or result-control defects with failing-first regressions.
- [x] Run full pytest, desktop Node suite, lint, diff checks and fresh final review; fix findings with failing regressions and rerun the complete final-state suite.
- [x] Write researcher transcripts and timing/scientific evidence report, including unresolved boundaries, and copy it to Downloads.

## Execution ledger

Pre-flight: Task 1 consumes Task 2's adapter through existing interfaces; no shared file edits. Task 3 consumes real API result and preparation payloads; root supplies recorded evidence. Numeric provenance changes must be coordinated with domain/prompting consumers.
Ruling: skip approval handoffs and new worktrees because the user explicitly requests continuous execution on the latest branch. Keep changes local until a new push request. Cost if wrong: review or publication can be requested separately.

### Review and verification ledger

- Numerical owner implemented native precision, rollback, bounded continuation, and restored-equation warm starts. Actual references pass without relaxed limits. Schottky/Fermi remains refused.
- Independent sweep diagnostic replaced the unsuitable global slope ratio with a local secant anomaly check, preserving the threshold and spike failure regression.
- Presentation owner reproduced short-window plan revision clipping, fixed only that defect, and verified actual results headlessly.
- Root fixed bounded reference-data availability, citation normalization, typed work-function completeness, scientific outcome gating, requested capability preservation, and missing-result API handling.
- Initial review found credential redaction and retention/outcome boundary gaps. Failing regressions now cover researcher/repository model provenance, contact-only answers, geometry and frequency answers, explicit analysis changes including an existing study-kind field, and chat-only simulation finishes.
- A schema-size hypothesis was rejected after inspection: compiled native plans, not the schema, exceeded 50k. Full typed plans remain intact; only model-facing tool text is compact.
- Quantity schema now advertises already-supported unit strings. Canonical serialization and dimensional rejection remain intact.
- Five latest live cases passed: PN ohmic reference187.313s, MOS quasi-static156.033s, MOS1MHz149.561s, graded117.250s, temperature83.447s.
- Focused latest regressions52 passed; desktop60; headless3. Final exact-state suite916 passed,28 skipped in233.90s, recorded in output/exact-final-complete-suite.log.
- Strict mypy51 errors in9 files are reproduced on the clean base commit as well as the checkout. Do not claim a clean whole-source type check.
- Report: docs/verification/2026-10-13-exact-researcher-workflows.md. Download copy follows final evidence recording. No automatic commit/push or installer rebuild.
- Final review continuation findings were reproduced and repaired: changing analysis kind no longer restores the old kind field, and repository-origin model fields retain their provenance with their capabilities. Both regressions pass. All five latest payloads passed all dataset selections and plot controls at560px/1440px, with no active animation after completion.
