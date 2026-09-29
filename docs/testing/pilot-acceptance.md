# Pilot Acceptance

## Automated acceptance

Run from the repository root:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/mypy --strict src
git diff --check
```

The ordinary suite must complete with the licensed Sentaurus test clearly skipped when the remote machine is absent. A skip is not proof that Phase 4 has passed on Sentaurus.

The opt-in Bedrock acceptance suite is:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest \
  tests/e2e/test_live_unified_backend.py \
  --run-live-bedrock -m live_bedrock -q
```

Authentication failures must remain generic and must never print the credential.

The live prompt-preparation acceptance suite verifies both clarification and a complete scientific
run through the same configured model. The second case must produce a real DEVSIM bundle and reopen
graphable potential and electric-field data through the Results Workbench contract:

```bash
set -a && source .env && set +a
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest -q \
  tests/e2e/test_live_prompt_preprocessing.py \
  --run-live-bedrock -s
```

Run the scientific synthetic suite with:

```bash
.venv/bin/pytest -q \
  tests/unit/evaluations/test_scientific_cases.py \
  tests/integration/test_scientific_research_workbench.py
```

This suite executes real DEVSIM cases spanning equilibrium and DC studies, two through
four generic regions, local and public evidence contracts, canonical fields, validation,
provenance, and the Results Workbench reader.

The live scientific prompt and full repository-agent evaluations incur Bedrock cost and
must be requested explicitly:

```bash
set -a && source .env && set +a
.venv/bin/pytest -q tests/e2e/test_live_unified_backend.py --run-live-bedrock
.venv/bin/pytest -q \
  tests/e2e/test_agentic_repl.py::test_live_bedrock_repository_agent_is_opt_in \
  --run-live-bedrock
```

The full agent evaluation resolves surfaced approvals through the product API, then
requires the repaired repository to pass its deterministic 100-point scientific grader.

## Manual local acceptance

1. Start Agent Kronig from the operating-system application launcher.
2. Confirm the native workspace opens without launching a browser.
3. Open an empty repository and enter an incomplete natural-language DEVSIM research request.
4. Confirm preparation appears inline in Chat and asks only consequential scientific questions.
5. Answer the questions and confirm the same run continues without creating another conversation.
6. Enter a complete request and confirm it proceeds without ceremonial questions.
7. Confirm the agent uses `prepare_experiment` and receives a simulator-neutral plan with a stable digest.
8. Confirm prompt preparation, schema checks, capability checks, and validation do not ask for approval.
9. Confirm `execute_experiment` opens one plain-language simulation approval and no arbitrary output path is shown.
10. Approve the simulation category for that run and let the agent continue.
11. Confirm the plan uses only the current DEVSIM manifest subset. Sentaurus-only physics must be refused rather than silently approximated.
12. Confirm the final state is completed only if deterministic validation passed.
13. Open `runs/<run-id>/results/canonical.json` and confirm the Results Workbench shows fields, metrics, validation, and provenance.
14. Inspect `report.md`, `validation/report.json`, `events.jsonl`, and `manifest.json` in the same immutable bundle.
15. Recompute at least one artifact SHA-256 and confirm it matches the manifest.
16. Confirm no `.env` value appears in UI events, reports, native results, or the manifest.
17. Compile `examples/al-pn-al-equilibrium.yaml` for Sentaurus and confirm its deterministic deck contains the reviewed work-function and physics mappings.
18. Confirm real Sentaurus execution remains unavailable until the licensed checklist passes.

## Licensed-machine acceptance

1. Complete every item in `docs/operations/sentaurus-integration.md`.
2. Run the same approved portable case through the signed remote service.
3. Verify the exact simulator release, job signature, archive digest, result hashes, and retained audit record.
4. Normalize the allowlisted native result and reject missing, duplicate, non-monotonic, or non-finite data.
5. Run the conformance marker:

```bash
.venv/bin/pytest -m sentaurus tests/integration/test_cross_backend_conformance.py -q
```

6. Require the expert-reviewed per-case tolerances to pass. A skipped test, fixture-only pass, or locally compiled deck is not a real Sentaurus acceptance.

## Exit evidence

Retain the local DEVSIM bundle, the signed Sentaurus bundle, exact dependency lock, commit identity, conformance report, domain-lead tolerance approval, model identifier, prompt or skill versions, and the completed checklist. Any known warning stays visible in the pilot report.
