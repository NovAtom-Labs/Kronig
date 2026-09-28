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

The opt-in Bedrock smoke test is:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest \
  tests/e2e/test_pilot_acceptance.py \
  --run-live-bedrock -m live_bedrock -q
```

Authentication failures must remain generic and must never print the credential.

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
.venv/bin/pytest -q tests/e2e/test_live_scientific_prompts.py --run-live-bedrock
.venv/bin/pytest -q \
  tests/e2e/test_agentic_repl.py::test_live_bedrock_repository_agent_is_opt_in \
  --run-live-bedrock
```

The full agent evaluation resolves surfaced approvals through the product API, then
requires the repaired repository to pass its deterministic 100-point scientific grader.

## Manual local acceptance

1. Start Agent Kronig from the operating-system application launcher.
2. Confirm the native workspace opens without launching a browser.
3. Paste `examples/prompts/al-pn-al-equilibrium.md` and select DEVSIM.
4. Confirm the app asks for p-region thickness, n-region thickness, and contact treatment instead of inventing them.
5. Enter `1 um`, `1 um`, and choose the explicit DEVSIM ohmic approximation for local testing.
6. Confirm the plan shows 300 K, both `1e17 cm^-3` dopings, equilibrium, both zero-bias contacts, and every limitation of the approximation.
7. Confirm the plan uses only the current DEVSIM manifest subset. Requested Sentaurus-only physics must not be claimed as locally executed.
8. Approve the exact digest and run it.
9. Click Run again and confirm no duplicate job or bundle is created.
10. Confirm the final state is completed only if deterministic validation passed.
11. Download and inspect `report.md`, `results/canonical.json`, `validation/report.json`, `events.jsonl`, and `manifest.json`.
12. Recompute at least one artifact SHA-256 and confirm it matches the manifest.
13. Confirm no `.env` value appears in HTML, logs, events, reports, native results, or the manifest.
14. Validate and compile `examples/al-pn-al-equilibrium.yaml` for Sentaurus. Confirm the generated deck contains explicit 4.10 eV work-function contacts, Fermi statistics, SRH, Auger, and band-gap narrowing.
15. Confirm real Sentaurus execution remains unavailable until the licensed checklist passes.

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
