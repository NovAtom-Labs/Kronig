# Prompt Preprocessing Implementation Plan

> Internal execution plan. The approved design is implemented continuously on `prompt_preprocessing`; no review checkpoint is required.

## Task 1: Add typed preprocessing contracts

Create `tcad_agent.prompting` models for intent values, expert choices, clarification questions and answers, preparation decisions, workspace and knowledge context, preparation records, and compiled agent requests. Enforce origin rules, question count, ready-state consistency, evidence references, bounded strings, and JSON safety in Pydantic validators.

Tests first:

- reject more than seven questions
- reject ready decisions with unresolved critical paths
- reject expert choices without rationale
- accept generic repository and scientific intents
- prove no device discriminator exists in any contract

## Task 2: Build the deterministic compiler

Create a compiler that canonicalizes a validated preparation decision and context into a versioned JSON request envelope. Preserve the original prompt and answers as data. Record compiler version, original hash, compiled hash, context hashes, warnings, exclusions, deliverables, and validation expectations. Prohibit retrieval, model, and filesystem dependencies.

Tests first:

- identical typed inputs produce byte-identical output and hashes
- one changed answer changes the compiled hash
- prompt-injection-like researcher text remains inert JSON data
- unresolved critical intent cannot compile
- only supplied citations may be referenced

## Task 3: Build bounded context collection

Add a workspace context collector that records repository identity, Git state, and a shallow filtered inventory without reading secrets or large/binary files. Add a local knowledge retriever backed by the existing immutable knowledge index with hard limits for searches, passages, characters, and deduplication. Record source, version, URL, review state, and content hash.

Tests first:

- hidden secrets and ignored runtime data do not enter context
- symlinks cannot escape the workspace
- inventory and evidence budgets are deterministic
- local knowledge is used before any external research signal

## Task 4: Add the same-model preparation gateway

Use `llm_from_environment()` so preprocessing and execution resolve exactly the same model, region, credential, and reasoning setting. Send a strict system policy, typed schemas, the exact user message, structured answers, workspace context, and bounded evidence. Parse one JSON decision, retry once with deterministic validation errors, and fail with a sanitized error. Keep model iterations bounded and never persist hidden reasoning.

Tests first:

- scripted model clarification, ready, refusal, malformed JSON, and repair
- provider errors do not expose credentials
- a model cannot introduce unconfirmed researcher-owned values
- already complete prompts do not require questions

## Task 5: Persist preparation lifecycle

Extend SQLite with one `prompt_preparations` row per run. Store original prompt, answers, current decision, compiled request, revision, and timestamps. Add optimistic revision checks and typed getters. Keep this data under the existing ephemeral workspace-session lifecycle.

Tests first:

- create, update, restore, and stale revision behavior
- answer batches append without overwriting prior answers
- compiled requests are immutable after runtime start
- process recovery cancels unresolved runs

## Task 6: Integrate AgentSupervisor

Inject a preparation service into the supervisor. Change `start()` to capture the baseline, create a run, and perform preparation in a background thread before runtime creation. On clarification, transition to `waiting_for_user`. Add `answer_clarification()` to resume the same run. On ready, compile, create the normal runtime, send the compiled request, transition to running, and preserve existing approvals, pausing, stopping, change tracking, and recovery behavior.

Tests first:

- complete prompt executes through the existing runtime
- incomplete prompt waits without creating a runtime
- structured answers resume the same run
- active-writer protection includes preprocessing
- stop works while waiting for answers
- runtime receives compiled JSON rather than raw user text

## Task 7: Add HTTP and chat UI flow

Add typed endpoints to read the active preparation and submit answers with optimistic revision. Render an inline clarification card in the chat pane. Preserve researcher messages, disable the ordinary composer while questions are required, submit one answer batch, show safe phase events, and keep auto-scroll behavior stable. Do not reuse approval UI.

Tests first:

- API lifecycle from message to waiting to answer to execution
- stale and malformed answer responses
- JavaScript renders all questions, rationale, and answer fields
- Continue submits all non-empty answers once
- no question card appears for a ready prompt

## Task 8: Validate canonical results and workbench continuity

Exercise a prepared prompt through the existing TCAD domain tools and `ExperimentEngine`. Verify generated `ExperimentSpec`, adapter execution, canonical result fields, provenance, validation status, and Results Workbench discovery and graph series. Keep the workbench backend-neutral by using the canonical result reader only.

Tests first:

- synthetic prepared workflows for equilibrium, swept, and repository-only tasks
- unsupported physics is refused rather than approximated
- graphable canonical fields are discovered without filename or device hardcoding
- non-result JSON remains a normal JSON preview

## Task 9: Run live Bedrock end-to-end evaluations

Use the configured live API for several natural researcher prompts:

- a complete simulation request that should compile directly
- an underspecified request that should ask focused questions, accept answers, and execute
- a repository repair and validation request that should avoid TCAD-specific interrogation
- an unsupported request that should end explicitly rather than fabricate support

For at least one workflow, let OpenHands create the experiment files, run DEVSIM, inspect the canonical result, and verify the Results Workbench graph payload through the HTTP API. Record only sanitized assertions and usage metadata. Never commit credentials or provider output containing secrets.

## Task 10: Full verification and documentation

Update architecture, README, installation, operations, and pilot acceptance documentation. Run Ruff, strict mypy, the complete Python suite, desktop Node tests, focused live Bedrock evaluations, and `git diff --check`. Perform a final repository scan for device-name branching, credentials, proprietary Sentaurus material, obsolete raw-prompt runtime calls, and duplicated preprocessing paths.
