# Research Workflow Reliability Acceptance

This record covers the plan-gated native research workflow introduced on `devsim-1d-expansion`.

## Accepted behavior

- Consequential scientific inputs use typed authority, provenance, dependency, and resolution records.
- Absolute terminal current requires contact area. Current density remains valid without area.
- Generic study accounting expands exact, ranged, and composed coordinates without device-name branching.
- Prepared experiments produce deterministic `PLAN.md` and `plan.json` artifacts in a readable experiment project.
- The OpenHands runtime pauses after plan preparation and resumes the same run only after exact-digest approval or revision.
- Approved execution uses a bounded digest-only handoff. The domain tool reloads the exact structured plan from the selected repository, verifies its location, size, schema, and digest, and never asks the model to reconstruct the prepared payload.
- Plan approval covers local simulation execution for that run. Higher-impact permission categories remain separately gated.
- Simulator internals live under cross-platform application data. The repository contains only researcher-facing artifacts.
- Managed results open in the native Results Workbench. Execution and validation states remain separate.
- Needs-review data remains inspectable and is never presented as a passed scientific result.
- Errors use typed, redacted envelopes with correlation and diagnostic identifiers.
- Desktop shutdown offers recovery and force-exit paths and cannot be trapped by backend cleanup failure.

## Local verification

```text
ruff check src tests scripts: passed
mypy src: passed across 153 source files
pytest -q: 739 passed, 17 skipped
Electron node --test: 45 passed
Targeted live Bedrock workflows: 5 passed
git diff --check: passed
```

The live workflows cover bounded clarification, exact plan approval, DEVSIM execution, canonical validation, graphable managed results, unsupported-physics refusal, and ordinary repository editing. Cross-platform packaged-installer smoke tests remain separate release evidence because they require Linux and Windows runners. No credential value is stored in this document or the repository.
