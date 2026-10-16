# Clarification Guardrails Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation with failing tests first.

**Goal:** Preserve researcher authority across clarification rounds, prevent redundant questions and retry loops, and verify varied live researcher workflows without device-specific branches.

**Architecture:** Extend the existing preparation record and answer contract, not a second backend. Persist server-bound field and question snapshots in existing answers JSON. Reconcile questions against confirmed typed intent, retain justified ambiguity, and make answer submission transactional and replay-safe.

**Tech Stack:** Python, Pydantic, SQLite, OpenHands/Bedrock, existing JavaScript clarification UI, pytest and headless Chromium.

**Spec:** The six guardrails approved in this conversation: authoritative run-local inputs; patch-like intent preservation; justified questions; retry-safe submissions; loop detection; final plan audit. This document records their implementation decisions.

## Global Constraints

- ExperimentSpec remains simulator-neutral. No device-name or researcher-prompt branches.
- Preserve units, entity identity, study identity, explicit physics and outputs.
- Missing scientific intent is not supplied by defaults or evidence silently.
- Keep original raw answers, field scope, question snapshot and preparation revision.
- Do not restore cross-session repository memory or change numerical validation.
- Extend existing revision guards; do not discard contradictory researcher inputs.
- Keep API calls bounded and logs free of credentials.
- Work on the current non-main branch, without a worktree. Commit and push after full verification, as explicitly requested.

## Review Focus

- Reused question IDs for different contacts or quantities must not overwrite answers.
- Rewording a missing-value question must not bypass a confirmed, valid value.
- Real ambiguity, conflicting instructions and invalid units must still ask for correction.
- Duplicate, delayed and concurrent answer POSTs must launch preparation at most once.
- A changed study must invalidate only dependent choices, not unrelated confirmed physics.

### Task 1: Bind and retain answers by scoped field

**Files:** prompting/models.py, prompting/clarifications.py, agent/supervisor.py, prompting/gateway.py, prompting/service.py; unit prompting tests.

**Interfaces:** ClarificationAnswer gains optional server-bound field_path, question_prompt and question_revision. A binding/merge helper consumes previous questions and answer history and returns field-bound history. The model receives all historical question-to-answer bindings.

- [x] Write failing regressions for ID reuse, multiple rounds, wrong client binding and exact entity scope.
- [x] Run the regressions and verify the intended failures.
- [x] Bind snapshots on acceptance; merge by scoped identity, preserving historical corrections rather than replacing unrelated answers.
- [x] Send bound history to the gateway and compiled request; retain existing confirmed IntentFields as the authoritative typed snapshot.
- [x] Verify focused tests and unchanged researcher authority checks.

### Task 2: Justify and reconcile questions

**Files:** prompting/models.py, prompting/completeness.py, prompting/clarifications.py, prompting/service.py, prompting/gateway.py; completeness and service tests.

**Interfaces:** Questions carry a typed reason and optional researcher-source quotations or changed dependencies. Missing-value questions for already complete registered fields are removed irrespective of wording. Conflicts must cite actual researcher input; changed-dependency questions must identify a real change. Structured scientific questions remain model-reasoned.

- [x] Write failing cases for paraphrased duplicates, units, contacts, schedules and genuine conflicts.
- [x] Implement reconciliation using existing capability descriptors and quantity validation, not text matching to particular experiments.
- [x] Preserve confirmed values before recomputing completeness; reject ungrounded changes instead of silently choosing new values.
- [x] Detect unchanged unresolved state after submitted answers and bounded preparation rounds. Surface a readable preparation failure, not another identical question loop.
- [x] Verify legitimate corrections and scientific follow-ups remain possible.

### Task 3: Make clarification submission retry-safe

**Files:** ide/store.py, agent/supervisor.py, web/schemas.py, web/static/ide.js; store, supervisor and browser tests.

**Interfaces:** Store atomically accepts a submitted question-set revision and canonical answer payload. Exact replay acknowledges the existing acceptance even after later preparation changes; a different stale payload is rejected. Only the first acceptance launches work. Server binding rejects forged field metadata.

- [x] Write failing tests for duplicate requests, different stale payloads, concurrent requests and no duplicated messages/model calls.
- [x] Persist acceptance receipts in a run-scoped SQLite table with revision and payload fingerprint.
- [x] Atomically update answers and run admission; preserve existing optimistic revision checks on inference results.
- [x] Keep UI drafts on conflicts and ignore older poll/response state. Verify browser focus, navigation and resubmission behavior.

### Task 4: Audit, live evaluation and final verification

**Files:** existing plan authority guard, tests/e2e live clarification coverage, verification notes and README.

- [x] Verify final prepared plans retain confirmed quantities, study identity, physics, units and requested outputs through existing deterministic authority checks; add regressions for uncovered boundaries.
- [x] Run varied live API prompts with researcher-like short and detailed answers, including a multi-round case and two different contact values. Exercise real native simulation and Results Workbench data for representative supported cases.
- [x] Retain timing, number of rounds, question history, scientific validation and rendering evidence in ignored output; document truthful limitations.
- [x] Run the complete Python suite, desktop tests, frontend tests, lint and whitespace checks.
- [x] Request one independent read-only review, fix important findings with failing tests, and rerun the full suite if code changes.
- [ ] Commit with detailed evidence, push only the current branch, fetch and verify identical heads and a clean working tree.

## Execution record

Baseline: d4d9738 on devsim-1d-expansion. User explicitly authorized live API use and implementation without further approval gates. No simulator equations, acceptance thresholds or installers are changed by this task.

Frozen-source verification: 1,291 Python tests passed across complementary parallel
and isolated native phases, 32 skipped; 189 prompting, 18 headless clarification and
60 desktop tests passed. Five live contract cases, a multi-round invalid-unit
correction, a nested-contact rerun and actual DEVSIM/result-rendering evidence are
recorded in docs/verification/2026-10-16-clarification-guardrails.md. Delivery remains
the final Git operation, as explicitly authorized by the user.
