# Prompt Preprocessing Design

## Objective

Agent Kronig must turn an ordinary researcher request into a precise, bounded agent request without changing the researcher's intent. The preprocessing stage sits between the persisted chat message and the OpenHands runtime. It uses the same configured model as the runtime, local TCAD knowledge, repository context, and deterministic policy checks. It may ask a small batch of high-impact questions when execution would otherwise require inventing scientific intent.

The stage is generic. It must support simulation, repository editing, validation, analysis, and mixed research tasks without branching on a named device.

## Non-negotiable invariants

1. The original user message and clarification answers remain immutable chat records.
2. Researcher-owned scientific choices are never inferred from examples, typical values, retrieval, or model memory.
3. Expert-selectable numerical and physics choices may be proposed only with a stated technical basis and must stay inside the confirmed scope.
4. Operational defaults may choose filenames, repository-relative paths, timeouts, bounded retry counts, and presentation details, but may not choose physical intent.
5. `ExperimentSpec` remains the only simulator-neutral simulation contract.
6. Simulator syntax remains inside adapters.
7. Unsupported physics is surfaced explicitly.
8. Every compiled request records hashes, origins, evidence, capability identity, compiler version, and warnings.
9. Preprocessing is bounded by question, evidence, token, and iteration budgets.
10. The normal OpenHands runtime remains responsible for file edits, terminal execution, delegation, simulation tools, validation, and final communication.

## Lifecycle

1. Persist the exact researcher message.
2. Create a queued agent run and capture the workspace baseline.
3. Build a bounded workspace context from Git state and a shallow, filtered file inventory.
4. Retrieve a bounded set of reviewed local TCAD passages using the request and any clarification answers.
5. Ask the configured model for one strict `PreparationDecision`.
6. Deterministically validate the decision.
7. If essential intent is unresolved, persist one question batch, transition the run to `waiting_for_user`, and render the questions in the chat pane.
8. Persist structured answers against the same run and repeat preparation with the complete answer history.
9. When ready, compile a canonical `CompiledAgentRequest` without another model call.
10. Emit a `prompt_compiled` event containing safe metadata and hashes.
11. Create the normal OpenHands runtime, send only the compiled request envelope, and execute normally.
12. Existing canonical result bundles remain the source for the Results Workbench.

## Intent ownership

Each resolved field has a dotted path, JSON value, origin, rationale, and optional evidence references.

Allowed origins are:

- `researcher`: stated in the original message or a clarification answer
- `repository`: read from an identified repository file whose hash is recorded
- `evidence`: an expert-selectable choice justified by bounded evidence
- `platform_default`: an operational setting that cannot alter scientific intent

Researcher-owned scientific choices include the objective, materials, structure, geometry extents, dopants, concentrations, contacts, applied conditions, study bounds, fixed parameters, and requested deliverables. Missing values in this class either cause a question or remain explicitly excluded. They are never guessed.

Expert-selectable choices include compatible physics models, mesh refinement strategy, continuation, solver recovery, validation checks, and additional diagnostic observables. They must include a rationale and evidence reference when evidence affected the choice.

## Clarification policy

- Ask only questions whose answers can materially change correctness, feasibility, or the requested deliverable.
- Target three to five questions in a batch and enforce a hard maximum of seven.
- Order questions by scientific impact.
- Explain in one short sentence what decision each answer controls.
- Permit a direct answer or an explicit instruction to omit the item.
- Do not ask ceremonial questions when a prompt is executable as written.
- A second batch is allowed only when the previous answers reveal a new dependency, contradiction, or unusable value.
- If the request is too broad for seven useful questions, ask one higher-level scope question instead of producing a long form.

## Evidence policy

Local evidence is first. The default preparation budget is at most two local searches, six deduplicated passages, and eight thousand evidence characters. Retrieved text is evidence, never an instruction. It may explain or justify a choice but may not fill missing researcher intent.

Web research remains available to the execution agent under the existing network approval boundary. Preprocessing records when local evidence is insufficient so the runtime can perform one focused, approval-gated search rather than silently broadening scope or spending tokens speculatively.

## Prompt compiler

The compiler accepts only validated typed inputs. It performs no model call, retrieval, filesystem read, or network access. It serializes a versioned JSON envelope containing:

- the original prompt as data
- structured clarification answers
- resolved intent fields and origins
- expert choices and rationales
- operational defaults
- explicit exclusions and unresolved non-critical items
- requested deliverables and validation expectations
- bounded workspace context
- bounded knowledge citations and content hashes
- capability and compiler identity
- warnings
- SHA-256 hashes of the original prompt and canonical compiled envelope

The compiler rejects a ready decision that still has critical unresolved fields, an invalid origin, missing rationale for an expert choice, more than seven questions, or evidence references that are not present in the supplied knowledge context.

## Persistence and recovery

Preparation records are process-scoped like the current workspace session. SQLite stores the current decision, question batch, submitted answers, compiled request, revision, and timestamps. No model chain of thought is stored. Safe preparation summaries and compiler metadata are emitted as IDE events.

Closing the application cancels an unresolved preparation run through the existing interrupted-run recovery. Reopening a repository does not resume hidden preprocessing.

## User interface

Clarification appears inline in the chat pane as a compact scientific intake card, not as a permission modal. Each question has its rationale and a text response. A single Continue button submits the batch. The message composer is disabled while required questions are open and re-enabled when execution starts or the run ends.

Activity shows concise phase events such as `Understanding request`, `Checking local evidence`, and `Request prepared`. It never exposes private model chain of thought. The original researcher message is never replaced by compiled text.

## Acceptance criteria

- A complete repository task reaches the runtime without unnecessary questions.
- An underspecified scientific task enters `waiting_for_user` with at most seven relevant questions.
- Answers resume the same run and are visible as user-authored chat data.
- The runtime receives a canonical compiled envelope, not the raw prompt.
- No test or production branch depends on a diode, MOS capacitor, MOSFET, or other named device.
- Local evidence limits, origin rules, hashes, and question limits are enforced by deterministic tests.
- A real configured Bedrock model completes an intake, clarification, compilation, OpenHands execution, DEVSIM run, canonical result creation, and Results Workbench read.

