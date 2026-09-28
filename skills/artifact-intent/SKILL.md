---
name: artifact-intent
description: Use when deciding which files or deliverables a research task should create, especially when a report, plot, notebook, or summary was not explicitly requested.
---

# Choosing Research Artifacts

Create the smallest durable artifact set that satisfies the research request and preserves reproducibility.

## Decision table

| User intent | Create automatically | Create only if requested or necessary |
|---|---|---|
| inspect or explain a repository | no new scientific files | notes, report, presentation |
| edit or debug code | requested code and tests | research report, plots |
| run one TCAD experiment | immutable run bundle and evidence summary | standalone narrative report |
| compare variants | run bundles and machine-readable comparison data | durable comparison report if the analysis itself is the deliverable |
| prepare publication or handoff | evidence bundles | requested report, figures, tables, export formats |

The automatic `report.md` inside a controlled run bundle is an evidence summary. It records outcome, validation, canonical results, and provenance. It must exist for auditability, but it is not evidence that the user requested a research report.

## Decision questions

Before creating an additional file, ask internally:

1. Did the user request this deliverable?
2. Is the file required to execute, validate, reproduce, or inspect the result?
3. Does the analysis need to persist independently of chat?
4. Would this duplicate canonical data or the evidence summary?
5. Can the same value be delivered more clearly in the final response?

If the first three answers are no, do not create the file.

## Naming and placement

Use conventional, purpose-revealing names. Keep simulator-native files within their run or compiled-artifact directories. Keep canonical results and validation beside their manifests. Do not scatter generated reports at repository root unless the user asks for that location.

## No speculative deliverables

Do not generate a standalone narrative report, design specification, slide deck, notebook, or dashboard merely to make the work look substantial. Do not create empty placeholders for future work. Mention a useful optional deliverable in chat instead.

## Completion response

Tell the user what changed, what was validated, where essential evidence lives, and the most important limitation. Do not list internal artifacts as if each were a user-facing product.
