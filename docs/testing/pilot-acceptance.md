# Pilot Acceptance

## Automated acceptance

Run from the repository root:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/pytest -q
.venv/bin/ruff check src tests scripts
pnpm --dir desktop test
.venv/bin/python scripts/sync_requirements.py --check
git diff --check
```

The ordinary suite must complete with the licensed Sentaurus test clearly skipped when the remote machine is absent. A skip is not proof that Phase 4 has passed on Sentaurus.
Run `.venv/bin/mypy --strict src` separately and report the existing baseline errors; do not conceal them or treat them as an installation check. Use [INSTALLATION.md](../../INSTALLATION.md) to set up the current native source application.

The opt-in Bedrock acceptance suite is:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python -c 'from dotenv import load_dotenv; import pytest; load_dotenv(); raise SystemExit(pytest.main(["tests/e2e/test_live_unified_backend.py", "tests/e2e/test_live_expanded_devsim.py", "--run-live-bedrock", "-m", "live_bedrock", "-q"]))'
```

Authentication failures must remain generic and must never print the credential.

The live prompt-preparation acceptance suite verifies both clarification and a complete scientific
run through the same configured model. The second case must produce a real DEVSIM bundle and reopen
graphable potential and electric-field data through the Results Workbench contract:

```bash
OPENHANDS_SUPPRESS_BANNER=1 .venv/bin/python -c 'from dotenv import load_dotenv; import pytest; load_dotenv(); raise SystemExit(pytest.main(["-q", "tests/e2e/test_live_prompt_preprocessing.py", "--run-live-bedrock", "-s"]))'
```

Run the scientific synthetic suite with:

```bash
.venv/bin/pytest -q \
  tests/unit/evaluations/test_scientific_cases.py \
  tests/integration/test_scientific_research_workbench.py
```

This suite executes real DEVSIM cases spanning equilibrium, exact and adaptive DC,
mixed silicon and dielectric regions, analytic profiles, fixed charge, terminal charge,
quasi-static capacitance, AC and frequency response, transient schedules, temperature and
registered parameter studies, local and public evidence contracts, axis-aware datasets,
validation, provenance, and the Results Workbench reader. Intake cases also prove that prompts
remain natural researcher prose.

The live scientific prompt and full repository-agent evaluations incur Bedrock cost and
must be requested explicitly:

```bash
.venv/bin/python -c 'from dotenv import load_dotenv; import pytest; load_dotenv(); raise SystemExit(pytest.main(["-q", "tests/e2e/test_agentic_repl.py::test_live_bedrock_repository_agent_is_opt_in", "--run-live-bedrock"]))'
```

The full agent evaluation resolves surfaced approvals through the product API, then
requires the repaired repository to pass its deterministic 100-point scientific grader.

## Manual local acceptance

1. Start the current source using the platform shortcut in `INSTALLATION.md`, or qualify a specific installed release separately.
2. Confirm the native workspace opens without launching a browser.
3. Open an empty repository and enter an incomplete natural-language DEVSIM research request.
4. Confirm preparation appears inline in Chat and asks only consequential scientific questions.
5. Answer the questions and confirm the same run continues without creating another conversation.
6. Enter a complete request and confirm it proceeds without ceremonial questions.
7. Confirm the agent uses `prepare_experiment` and receives a simulator-neutral plan with a stable digest.
8. Confirm prompt preparation, schema checks, capability checks, and validation do not ask for approval.
9. Confirm the plan review offers **Open plan**, **Approve and run** and **Run unattended**, with its immutable plan identity handled internally.
10. Approve the plan and let that same run continue. Unattended mode covers local approved simulation work, not external, network, Git or system mutation.
11. Confirm the plan uses only the current DEVSIM manifest subset. Sentaurus-only physics must be refused rather than silently approximated.
12. Distinguish completed execution from passed validation. Failed scientific checks must remain visible as needing review.
13. Open the experiment's in-app results entry and confirm the Results Workbench shows fields, metrics, validation and provenance without a browser or hand-selected HTML file.
14. Follow the projected experiment's evidence links to inspect its immutable validation, events, manifest and canonical result. A narrative report is created when appropriate, not for every repository task.
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
