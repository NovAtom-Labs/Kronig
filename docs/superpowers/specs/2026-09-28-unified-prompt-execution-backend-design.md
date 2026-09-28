# Unified Prompt and Experiment Backend Design

## Purpose

Agent Kronig will have one researcher-facing entry point and one scientific execution path. A researcher writes a natural-language request in the workspace chat. A bounded prompt-preparation stage resolves only the information needed to execute the request faithfully, then a deterministic compiler constructs the final OpenHands request. When the task requires simulation, the agent uses typed simulator-neutral tools backed by one deterministic experiment engine.

The removed guided simulation interface and its separate model proposal gateway will not remain as a second backend.

## Product contract

- The workspace chat is the only interactive prompt entry point.
- The exact researcher prompt remains visible and unchanged in chat.
- The pilot uses one configured model for prompt preparation, reasoning, tool selection, execution control, and interpretation. It does not introduce a separate prompt-rewriter model.
- Prompt preparation is bounded by model-iteration, retrieval, web, and clarification budgets.
- `ExperimentSpec` remains the only scientific intent passed into a simulator adapter.
- No behavior branches on a named device.
- Missing scientific intent becomes a clarification request. It is never filled from examples, retrieval, or typical values.
- Simulator syntax remains inside its adapter package.
- Unsupported physics is refused explicitly.
- Numeric claims remain derived from canonical result fields.
- Source, version, hash, compiler, simulator, and validation provenance remain mandatory.
- Proprietary Sentaurus documents and credentials never enter the repository or test artifacts.

## Unified flow

```text
researcher workspace message
  -> deterministic intake envelope
  -> bounded prompt-preparation agent using the configured model
  -> concise clarification batch when essential intent is missing
  -> deterministic PromptCompiler after intent is resolved
  -> compiled agent request plus context manifest
  -> OpenHands agent runtime
  -> repository tools and typed TCAD domain tools
  -> ExperimentSpec when simulation is required
  -> capability decision
  -> exact plan digest and execution approval
  -> deterministic adapter and runner
  -> CanonicalResult
  -> validation and immutable evidence bundle
  -> Results Workbench
```

Repository editing, inspection, debugging, and explanation tasks stop at the relevant repository tools. They are not forced through an experiment state machine.

## Prompt preparation and compilation

Prompt preparation has two distinct responsibilities. The preparation agent determines whether the request is sufficiently specified and gathers narrowly relevant evidence. The deterministic compiler serializes the resolved intent into the final execution request. The model never receives authority to fill missing researcher intent merely because it is preparing a better prompt.

### Intent ownership

Every consequential value in the resolved request has an explicit origin:

- `researcher`: stated in the original request or a clarification answer
- `repository`: read from a researcher-controlled project file and cited by relative path and content hash
- `evidence`: an expert-selectable method justified by reviewed local knowledge or an approved external source
- `platform_default`: an operational default defined in versioned Agent Kronig code

Researcher-owned scientific choices include the research goal, structure and materials, physical extents, dopant species and concentrations, contact intent, applied conditions, study range, and any fixed physical parameter. Evidence may explain valid choices but cannot choose one on the researcher's behalf.

Expert-selectable choices include model families, mesh strategy, continuation strategy, validation checks, and additional observables necessary to answer the stated question. These choices must remain within the researcher-defined scope, cite their basis, and appear explicitly in the final prompt.

Platform defaults are limited to operational behavior such as bounded execution time, repository-relative artifact locations, deterministic filenames, safe numerical recovery limits, and display formatting. They must be versioned and visible in provenance. They cannot introduce physical geometry, material properties, doping, bias conditions, or requested conclusions.

### Bounded preparation agent

The preparation agent uses the same configured LLM as the execution agent but a restricted tool profile. It may inspect repository files, search the authorized local knowledge index, and request approved web evidence. It cannot edit files, run arbitrary terminal commands, execute a simulator, mutate Git, delegate subagents, or finalize unsupported physics.

The preparation sequence is:

1. Preserve the exact request and build a bounded workspace snapshot.
2. Identify explicit facts, requested outcomes, constraints, and deliverables.
3. Search local skills and reviewed knowledge for terminology, capability, model-selection, and validation guidance.
4. Separate missing researcher intent from expert-selectable implementation choices.
5. Ask a concise clarification batch when a missing researcher-owned value blocks faithful execution.
6. Produce a typed `ResolvedResearchIntent` only when the request is executable without invention.

The default clarification target is three to five questions, with a hard limit of seven questions in one batch. Questions are ordered by how strongly their answers change the experiment. Each question states what decision it controls and accepts a direct answer or an explicit instruction to leave that part out. A second batch is permitted only when the first answers reveal a new dependency, conflict, or remain unusable. There is no artificial lifetime question limit that would force invention. If more than seven questions appear necessary at once, the agent first clarifies the overall research objective and scope instead of presenting a long questionnaire.

If the request is already sufficient, preparation proceeds without asking ceremonial questions. If an omitted detail can be handled by a versioned operational default without changing scientific intent, the final prompt names that default rather than interrupting the researcher.

### Evidence and cost budget

Local skills and reviewed indexed sources are always searched before any public web request. Local retrieval has no model-provider cost and is limited to two focused searches, six deduplicated passages, and 8,000 injected characters by default.

Web research is optional, approval-gated, and used only when a consequential claim is missing, stale, conflicting, or version-dependent. One preparation cycle may perform at most one web search and fetch at most two primary or official sources. Search-result snippets are not evidence. The preparation agent must not browse to answer a question that should be asked of the researcher.

The preparation agent is limited to four model iterations before it must return a clarification batch, a ready intent, or a concise blocked status. Token and tool usage are recorded in ephemeral run metadata. Budgets are configurable for evaluation but have conservative production defaults.

### Inputs

`PromptCompiler.compile` receives:

- the exact researcher message and any clarification answers
- a validated `ResolvedResearchIntent`
- the canonical workspace root
- repository metadata such as repository name, branch, and dirty state
- the currently focused repository-relative file when the UI supplies one
- the installed backend capability summaries and their content hashes
- the bounded evidence records selected during preparation
- the runtime tool and skill inventory

It must not read additional files, perform retrieval, or make model calls. Those belong to the bounded preparation stage.

### Output contract

The compiler returns a typed `CompiledAgentRequest` containing:

- `schema_version`
- `original_prompt`
- the structured `resolved_intent`
- `compiled_prompt`
- `original_prompt_sha256`
- `compiled_prompt_sha256`
- a bounded `WorkspaceContext`
- retrieved `KnowledgeContext` records with source, version, review state, and content hash
- backend capability digests
- warnings for missing or unavailable context

The compiled prompt is a versioned JSON envelope. The researcher message and clarification answers are data fields, not interpolated instruction blocks. The envelope contains confirmed intent, evidence-backed expert choices, operational defaults, explicit exclusions, requested deliverables, validation expectations, and provenance. It tells the execution agent to preserve intent, use tools for current repository state, and route simulations through `ExperimentSpec` and the typed experiment tools.

The compiler refuses a `ResolvedResearchIntent` containing an unresolved execution-critical field or a consequential value without an allowed origin. It does not paraphrase the researcher, infer device type, generate simulator syntax, choose missing numeric values, or claim that retrieval is authoritative.

### Knowledge behavior

The preparation stage performs bounded retrieval using the original prompt and any clarification answers. It supplies the compiler only reviewed local passages and approved external evidence that directly support a recorded expert choice or constraint.

If reviewed local evidence is absent, preparation records a warning and adds no substitute. It may request approved web access only within the evidence budget. Retrieved text is labeled as untrusted evidence and cannot alter researcher intent, system policy, tool permissions, schemas, or validation rules.

The OpenHands skill loader remains responsible for progressive skill disclosure. The compiler includes only a compact skill inventory, not duplicate copies of every skill body.

### Runtime integration

The workspace run coordinator stores the unchanged user message and begins prompt preparation. If clarification is required, it emits a structured `clarification_required` event and transitions the run to `WAITING_FOR_USER`. The UI renders the questions inside the normal chat flow. Answers are attached to the same ephemeral preparation record.

When intent is resolved, the coordinator invokes `PromptCompiler`, emits a `prompt_compiled` event, and sends only `compiled_prompt` to the full OpenHands execution runtime. Chat continues to display the unchanged researcher messages and answers.

The activity view may expose a technical prompt-compilation record containing hashes, warnings, knowledge citations, and context counts. It must not present the enriched prompt as if the researcher wrote it. Prompt compilation records remain process-scoped with the existing ephemeral session lifecycle.

Preparation is fail-closed for unresolved execution-critical intent and fail-soft for optional context. A missing knowledge index must not prevent ordinary repository work. An invalid intent origin or prompt envelope must prevent the execution-model call.

## Deterministic experiment engine

The current prompt-oriented `ControlService` will be replaced by an experiment engine that accepts typed scientific input rather than natural language.

### Prepare

```python
ExperimentEngine.prepare(
    spec: ExperimentSpec,
    backend: str,
) -> PreparedExperiment
```

Preparation validates the schema and units, checks the selected capability manifest, constructs a portable execution plan, and returns an exact SHA-256 plan digest. It performs no simulator run and makes no model call.

### Execute

```python
ExperimentEngine.execute(
    prepared: PreparedExperiment,
    approved_plan_digest: str,
    output_root: Path,
    budget: RunBudget,
) -> ExperimentBundle
```

Execution verifies the approved digest, compiles through the selected adapter, runs through the selected bounded runner, normalizes the native result, validates the canonical result, and writes the atomic evidence bundle.

The same engine serves the OpenHands domain tool and the CLI. The CLI is an alternate operator interface, not a separate backend.

### Agent tools and approval

The TCAD domain tool exposes two explicit operations:

- `prepare_experiment`, which is read-only with respect to simulator execution
- `execute_experiment`, which requires the exact prepared plan digest and a simulator-execution approval

Simulator execution receives its own human-readable permission category. Approval is scoped to the current run, consistent with the existing approval broker. A changed spec, backend, or plan produces a new digest and requires a new approval.

The existing `run_experiment` placeholder that always refuses is removed. The agent cannot bypass the engine by directly generating and executing backend syntax.

## Removed surfaces

The following obsolete product surfaces are deleted:

- public `/api/requests` routes and request-stage routes
- redirects retained only for the former guided simulation workflow
- `CreateResearchRequest`, `AnswerRequest`, `ApprovalRequest`, and `ResearchResults` web schemas
- the unused guided workflow template and JavaScript
- request-oriented SQLite state used only by the removed workflow
- the duplicate natural-language model proposal gateway
- frontend and end-to-end tests whose only contract is the removed workflow

Reusable deterministic logic is moved rather than deleted:

- plan construction and plan digests
- expected bias-point calculation
- capability checks
- adapters and runners
- bundle writing
- canonical normalization and validation
- result artifact access through the workspace Results Workbench

Old request records require no migration because the desktop product uses ephemeral process-scoped state and the guided frontend is no longer supported.

## API and UI behavior

The workspace run endpoint remains the only prompt execution endpoint:

```text
POST /api/workspaces/{workspace_id}/session/runs
```

It references the already stored user message. The server begins the restricted preparation phase. A full execution run is created only after preparation returns a validated ready intent. When clarification is required, the same endpoint accepts the next stored researcher answer and resumes the ephemeral preparation record.

The UI adds no second prompt form. Prompt compilation appears as a concise activity item such as “Prepared workspace and scientific context”, with technical details available on demand. Knowledge citations and warnings are shown without displaying secrets, absolute credential paths, or provider payloads.

## Security and privacy

- Prompt compilation never reads credential files.
- Workspace context uses repository-relative paths in model-visible metadata.
- API tokens are read only from the environment or protected desktop settings.
- Tests never print tokens, authorization headers, raw provider errors, or complete provider responses.
- Prompt and retrieved-text boundaries are serialized, not concatenated with ad hoc delimiters.
- Local and web evidence is data and cannot grant permissions or change policy.
- Simulator execution, network access, external files, remote execution, package installation, destructive commands, and Git mutation retain distinct approval categories.

## Testing strategy

### Deterministic tests

Prompt compiler unit tests cover:

- exact preservation of the original prompt
- exact preservation and attribution of clarification answers
- stable compilation and hashes for identical inputs
- rejection of unresolved execution-critical intent
- rejection of consequential values without an allowed origin
- repository-relative context only
- bounded and deduplicated knowledge
- reviewed-evidence preference
- absent and corrupt knowledge indexes
- prompt-injection text inside user input and retrieved passages
- non-TCAD repository tasks
- complete TCAD requests
- incomplete scientific requests
- explicit DEVSIM and Sentaurus requests
- no named-device routing branches

Prompt-preparation tests cover:

- a complete request proceeding without unnecessary questions
- a normal batch targeting three to five decision-controlling questions
- no clarification batch exceeding seven questions
- a second batch appearing only for conflicting or unusable answers
- sources informing expert method selection but never filling researcher-owned values
- local retrieval occurring before web research
- web research remaining disabled when local evidence is sufficient
- one web search and at most two fetched sources when approved evidence is necessary
- preparation stopping at the model, tool, and token budgets
- ordinary repository work proceeding when TCAD knowledge is unavailable
- prompt-injection text being retained as data without changing policy

Experiment engine tests cover:

- valid preparation and stable plan digests
- changed spec or backend invalidating approval
- unsupported physics refusal
- DEVSIM compilation and execution
- canonical normalization
- mandatory validation failure
- atomic evidence bundle provenance
- execution budgets and runner failures
- Sentaurus unavailable and remote-runner error boundaries

Application tests prove that obsolete request routes return `404`, the workspace route starts preparation, clarification questions and answers remain in the normal chat flow, the execution runtime receives only a validated compiled prompt, the original messages remain unchanged, and compilation metadata appears in the event stream.

### Real-world model evaluation

Live Bedrock tests are opt-in and run only when `TCAD_LIVE_EVAL=1` and protected credentials are present. They use the configured production model through the same `llm_from_environment` path as the desktop runtime.

The live suite includes at least these researcher-style cases:

1. a complete equilibrium semiconductor request
2. a request missing essential geometry or doping information
3. an unsupported physics request that must be refused rather than approximated
4. an open-ended comparison requiring local TCAD knowledge
5. a repository repair task that is not a simulation
6. a request requiring file inspection before deciding what to do
7. adversarial instructions embedded in a repository document
8. a simulation that produces and reopens a verified DEVSIM result bundle

The missing-input case must ask a concise batch of no more than seven decisive questions and must not place guessed physical values in the compiled prompt. The complete case must not ask redundant questions. The evidence case must use local knowledge before requesting web access. The adversarial case must preserve the text as untrusted data without adopting its instructions.

Each case grades observable behavior rather than exact prose. Required checks include correct tool routing, no invented scientific values, valid `ExperimentSpec` when appropriate, clarification when required, capability refusal, repository confinement, evidence citation, canonical results, validation status, and usable final explanation.

Live runs have explicit maximum iterations, wall-clock limits, and recorded token usage. The suite fails with sanitized diagnostics and never stores provider secrets or unrestricted response transcripts. A smaller smoke subset runs on demand during development. The full live suite runs before a pilot release or model change.

### Simulator coverage

DEVSIM tests execute locally through the real adapter and runner. Sentaurus tests exercise schema, capability, deterministic compilation, signed remote job contracts, normalization fixtures, and failure handling without proprietary documentation. A live Sentaurus acceptance suite runs only on licensed authorized infrastructure.

## Acceptance criteria

- Researchers have one prompt box and at most one active preparation or execution runtime.
- No public natural-language request API remains outside the workspace session.
- One deterministic prompt compiler prepares every workspace agent run.
- One configured model serves bounded preparation and execution. No separate prompt-rewriter model exists.
- Complete requests are not interrupted by unnecessary clarification.
- Incomplete requests normally receive three to five decisive questions and never more than seven in one batch.
- Researcher-owned scientific values are never sourced from model memory or literature.
- Local evidence is preferred, and web research stays approval-gated and tightly capped.
- One experiment engine serves agent tools and CLI execution.
- A complete DEVSIM request reaches a validated bundle and the Results Workbench.
- Missing scientific intent produces clarification rather than guessed values.
- Unsupported physics is refused explicitly.
- The compiled prompt and context manifest are reproducible and auditable.
- All deterministic tests pass.
- The bounded live Bedrock suite passes against the configured production model.
- No credentials or proprietary Sentaurus material appear in commits, logs, fixtures, or bundles.
