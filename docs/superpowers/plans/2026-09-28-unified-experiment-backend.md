# Unified Experiment Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the obsolete natural-language request backend and make the repository agent and CLI share one deterministic `ExperimentEngine` for TCAD preparation, execution, validation, and result bundles.

**Architecture:** Extract the reusable scientific execution path from `ControlService` and the CLI into a typed `experiments` package. Connect the OpenHands TCAD tool and CLI to that engine, retain exact plan-digest approval, then delete the unused guided workflow, duplicate proposal gateway, and request store. Prompt preparation is explicitly deferred to a later branch.

**Tech Stack:** Python 3.13, Pydantic, FastAPI, OpenHands SDK, DEVSIM, pytest, Bedrock live evaluations.

**Spec:** `docs/superpowers/specs/2026-09-28-unified-prompt-execution-backend-design.md`, limited in this phase to the deterministic experiment engine, obsolete-surface removal, and backend testing sections.

## Global Constraints

- Preserve all current uncommitted workspace UI changes.
- Do not implement prompt preprocessing in this phase.
- Keep `ExperimentSpec` as the simulator-neutral product contract.
- Do not branch behavior on named devices.
- Keep backend syntax inside adapter packages.
- Refuse unsupported physics instead of approximating it.
- Derive numeric reports from canonical results only.
- Preserve source, version, hash, compiler, simulator, and validation provenance.
- Never write credentials, unrestricted provider responses, or proprietary Sentaurus material to the repository.
- Add every behavior with a failing test first.
- Do not commit or push until the user requests it.

## Review Focus

- A changed specification or backend must invalidate an earlier plan digest.
- A model-generated output path must never escape the opened repository.
- Simulator execution must require a clear run-scoped approval while validation and preparation remain approval-free.
- Removing `/api/requests` must not break desktop shutdown, workspace sessions, result viewing, or CLI execution.
- Live Bedrock failures must expose bounded sanitized evidence without leaking credentials or full provider payloads.

---

### Task 1: Extract the deterministic experiment engine

**Files:**
- Create: `src/tcad_agent/experiments/__init__.py`
- Create: `src/tcad_agent/experiments/errors.py`
- Create: `src/tcad_agent/experiments/models.py`
- Create: `src/tcad_agent/experiments/planning.py`
- Create: `src/tcad_agent/experiments/service.py`
- Test: `tests/unit/experiments/test_service.py`
- Test: `tests/integration/test_experiment_engine.py`

**Interfaces:**
- Produces: `PreparedExperiment`, `ExperimentEngine.prepare`, and `ExperimentEngine.execute`.
- Consumes: `ExperimentSpec`, `CapabilityManifest`, adapter registry, `RunBudget`, `ValidationEngine`, `EventLedger`, and `BundleWriter`.

- [ ] **Step 1: Write failing preparation tests**

Test that `ExperimentEngine.prepare(spec, backend)` returns a schema-valid `PreparedExperiment`, a stable plan digest, normalized `ExperimentSpec`, capability provenance, and no simulator artifacts.

- [ ] **Step 2: Run the focused preparation tests and confirm they fail because the package does not exist**

Run: `pytest tests/unit/experiments/test_service.py -q`

- [ ] **Step 3: Implement the typed preparation contract**

Use these public interfaces:

```python
class PreparedExperiment(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    backend: str
    spec: ExperimentSpec
    plan: dict[str, JsonValue]
    plan_digest: str
    capability_digest: str
    warnings: tuple[str, ...] = ()

class ExperimentEngine:
    def prepare(
        self,
        spec: ExperimentSpec,
        backend: str,
        *,
        warnings: tuple[str, ...] = (),
    ) -> PreparedExperiment: ...
```

Move plan construction, plan hashing, and expected bias-point accounting from `control/execution.py` into `experiments/planning.py`.

- [ ] **Step 4: Run the preparation tests and confirm they pass**

Run: `pytest tests/unit/experiments/test_service.py -q`

- [ ] **Step 5: Write failing execution tests**

Cover exact digest approval, changed-spec rejection, changed-backend rejection, unsupported capability refusal, real DEVSIM execution, canonical normalization, validation, event ledger, atomic bundle creation, and runner failure cleanup.

- [ ] **Step 6: Implement deterministic execution**

Use this public interface:

```python
def execute(
    self,
    prepared: PreparedExperiment,
    *,
    approved_plan_digest: str,
    output_root: Path,
    budget: RunBudget,
    run_id: str | None = None,
) -> ExperimentBundle: ...
```

The engine owns compile, run, normalize, validate, ledger, and bundle sequencing. It accepts no natural-language prompt.

- [ ] **Step 7: Run unit and real DEVSIM integration tests**

Run: `pytest tests/unit/experiments/test_service.py tests/integration/test_experiment_engine.py -q`

### Task 2: Connect the OpenHands TCAD tool and approval policy

**Files:**
- Modify: `src/tcad_agent/agent/tools.py`
- Modify: `src/tcad_agent/agent/policy.py`
- Modify: `src/tcad_agent/ide/models.py`
- Modify: `src/tcad_agent/agent/runtime.py`
- Test: `tests/unit/agent/test_tools.py`
- Test: `tests/unit/agent/test_policy.py`
- Test: `tests/unit/agent/test_events.py`

**Interfaces:**
- Consumes: `ExperimentEngine.prepare` and `ExperimentEngine.execute` from Task 1.
- Produces: `prepare_experiment` and `execute_experiment` operations on `tcad_domain` plus `PermissionCategory.SIMULATION_EXECUTION`.

- [ ] **Step 1: Write failing tool and security-policy tests**

Assert that preparation returns a serialized `PreparedExperiment`, execution accepts only the returned digest, output is fixed below `<workspace>/runs`, and `execute_experiment` is classified as a high-risk simulation action with a plain-language approval explanation.

- [ ] **Step 2: Run the focused tests and confirm the expected failures**

Run: `pytest tests/unit/agent/test_tools.py tests/unit/agent/test_policy.py tests/unit/agent/test_events.py -q`

- [ ] **Step 3: Replace the placeholder tool operations**

Remove `compile_experiment` and the always-refusing `run_experiment`. Add:

```python
Literal["prepare_experiment", "execute_experiment"]
```

`execute_experiment` accepts serialized prepared data, exact `approved_plan_digest`, and a bounded timeout. The executor chooses the repository-local output root and never accepts an arbitrary path from the model.

- [ ] **Step 4: Add simulator-execution approval semantics**

Add `SIMULATION_EXECUTION` as a run-grantable category. Keep preparation, validation, and local knowledge retrieval low risk. Require approval for actual local or remote simulator execution.

- [ ] **Step 5: Run the focused agent tests and confirm they pass**

Run: `pytest tests/unit/agent/test_tools.py tests/unit/agent/test_policy.py tests/unit/agent/test_events.py -q`

### Task 3: Make the CLI use the same engine

**Files:**
- Modify: `src/tcad_agent/cli.py`
- Test: `tests/e2e/test_cli_workflow.py`

**Interfaces:**
- Consumes: `ExperimentEngine` from Task 1.
- Preserves: existing `validate`, `compile`, `run`, `report`, `knowledge`, and `evaluation` command names.

- [ ] **Step 1: Write a failing CLI test proving `run` delegates to `ExperimentEngine`**

The test must also prove that missing `--approve` still refuses execution and a completed DEVSIM run prints the bundle path expected by `WorkspaceResultReader`.

- [ ] **Step 2: Run the focused CLI tests and confirm the new delegation assertion fails**

Run: `pytest tests/e2e/test_cli_workflow.py -q`

- [ ] **Step 3: Replace duplicated CLI execution sequencing with the engine**

Keep `validate` and non-executing `compile` as thin lower-level commands. Make `run` call `prepare`, then `execute` with the prepared digest only after explicit CLI approval.

- [ ] **Step 4: Run the CLI tests and confirm they pass**

Run: `pytest tests/e2e/test_cli_workflow.py -q`

### Task 4: Remove the obsolete request backend and guided assets

**Files:**
- Modify: `src/tcad_agent/web/app.py`
- Modify: `src/tcad_agent/web/schemas.py`
- Modify: `src/tcad_agent/desktop/server.py`
- Delete: `src/tcad_agent/web/templates/index.html`
- Delete: `src/tcad_agent/web/static/app.js`
- Delete: `src/tcad_agent/web/static/styles.css`
- Delete: `src/tcad_agent/web/static/results-viewer.js`
- Delete: `src/tcad_agent/control/clarification.py`
- Delete: `src/tcad_agent/control/__init__.py`
- Delete: `src/tcad_agent/control/models.py`
- Delete: `src/tcad_agent/control/service.py`
- Delete: `src/tcad_agent/control/store.py`
- Delete: `src/tcad_agent/control/execution.py`
- Delete: `src/tcad_agent/model_gateway/base.py`
- Delete: `src/tcad_agent/model_gateway/openhands.py`
- Delete: `src/tcad_agent/model_gateway/__init__.py`
- Delete: `tests/unit/control/test_store.py`
- Delete: `tests/unit/control/test_service.py`
- Delete: `tests/unit/model_gateway/test_openhands.py`
- Delete: `tests/e2e/test_web_workflow.py`
- Delete: `tests/e2e/test_live_scientific_prompts.py`
- Migrate: `tests/integration/test_control_workflow.py`
- Migrate: `tests/integration/test_scientific_research_workbench.py`
- Migrate: `tests/e2e/test_pilot_acceptance.py`
- Test: `tests/unit/web/test_api.py`
- Test: `tests/unit/desktop/test_server.py`

**Interfaces:**
- Preserves: native root, workspace routes, agent runs, desktop bootstrap and shutdown, health, result workbench, and static assets used by `ide.html`.
- Removes: `/simulate`, `/requests/{id}/{stage}`, `/api/requests/**`, the `control=` application dependency, and request-store active-work checks.

- [ ] **Step 1: Write failing absence and lifecycle tests**

Assert that every obsolete public route returns `404`, no removed static asset is linked, desktop active state derives only from workspace runs, and `create_app` no longer accepts or constructs a control service.

- [ ] **Step 2: Run web and desktop tests and confirm the new contract fails**

Run: `pytest tests/unit/web/test_api.py tests/unit/desktop/test_server.py -q`

- [ ] **Step 3: Remove routes, dependency wiring, schemas, assets, and dead packages**

Migrate scientific acceptance tests to `ExperimentEngine`. Delete tests that only verify the removed frontend rather than scientific behavior. Keep all engine, adapter, runner, bundle, validation, workspace, and Results Workbench coverage.

- [ ] **Step 4: Search for stale imports and route references**

Run: `rg -n "ControlService|SqliteRequestStore|OpenHandsBedrockGateway|/api/requests|/simulate|templates/index.html|static/app.js" src tests desktop README.md docs/architecture.md`

Expected: no production references, except historical design documents clearly describing removed behavior.

- [ ] **Step 5: Run migrated web, desktop, scientific, and pilot tests**

Run: `pytest tests/unit/web tests/unit/desktop tests/integration tests/e2e/test_pilot_acceptance.py -q`

### Task 5: Add deterministic and live unified-backend acceptance

**Files:**
- Create: `tests/e2e/test_live_unified_backend.py`
- Modify: `tests/e2e/test_agentic_repl.py`
- Modify: `evaluations/scientific/cases.yaml`
- Modify: `docs/architecture.md`
- Modify: `README.md`
- Modify: `docs/operations/devsim.md`

**Interfaces:**
- Consumes: workspace OpenHands runtime, `tcad_domain`, `ExperimentEngine`, real DEVSIM, and `WorkspaceResultReader`.
- Produces: opt-in live Bedrock evidence that the configured production model can use the unified backend.

- [ ] **Step 1: Add deterministic scripted-agent acceptance tests**

Use natural researcher prompts and scripted OpenHands tool calls to prove that the agent prepares an `ExperimentSpec`, receives simulation approval, executes through `ExperimentEngine`, opens the verified canonical result, and reports only canonical metrics.

- [ ] **Step 2: Add bounded live Bedrock cases**

Add three opt-in live cases:

1. a complete DEVSIM equilibrium request that produces and reopens a validated bundle
2. an unsupported request that reaches capability refusal without direct simulator syntax
3. a non-simulation repository task proving the unified backend does not force every prompt through TCAD execution

Gate them behind `--run-live-bedrock`, require protected credentials, cap approval cycles and OpenHands iterations, record only sanitized grading data, and never persist raw provider responses.

- [ ] **Step 3: Run deterministic acceptance and the complete project suite**

Run: `pytest -q`

Expected: all non-live tests pass, with only documented environment-dependent skips.

- [ ] **Step 4: Run the real Bedrock suite against the configured production model**

Run: `pytest tests/e2e/test_live_unified_backend.py tests/e2e/test_agentic_repl.py --run-live-bedrock -m live_bedrock -q`

Expected: all three unified-backend cases and the existing live repository-agent case pass within their iteration, approval, and wall-clock budgets.

- [ ] **Step 5: Run final engineering verification**

Run:

```bash
ruff check src tests scripts
mypy src
python scripts/check_requirements_sync.py
git diff --check
```

Expected: all commands pass with no credential, proprietary-document, stale-route, or dependency drift findings.
