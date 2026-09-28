---
name: reporting
description: Use when the user requests a technical report, comparison write-up, publication-oriented summary, or durable interpretation of completed TCAD evidence.
---

# Reporting TCAD Evidence

Structured evidence owns every number. Narrative explains the evidence but never upgrades its certainty.

## Deliverable policy

Every controlled simulation bundle contains a compact `report.md` evidence summary. It is generated automatically for provenance and is not a standalone narrative research report.

Create a separate researcher-facing report only when the user asks for one or when a durable comparative analysis is the explicit primary deliverable. Do not create one for file edits, debugging, repository inspection, a single routine run, or a request that can be answered clearly in chat. If unsure, keep the evidence bundle and summarize in chat.

## Evidence hierarchy

1. `ExperimentSpec` defines what was requested.
2. `CanonicalResult` supplies numerical values and units.
3. `ValidationReport` determines whether claims may be treated as passed, warned, or failed.
4. `BundleManifest` supplies versions, hashes, and artifact provenance.
5. Retrieved sources support background physics and simulator semantics.

Never extract a value from prose, plots, filenames, or logs when a canonical field exists. Derived metrics must name the source fields and calculation.

## Report structure when requested

- research question and scope
- explicit assumptions and normalized experiment
- methods, backend, model set, and operating conditions
- validation status before results
- results with units and uncertainty or sensitivity context
- physical interpretation separated from computed facts
- comparison across variants or references
- limitations, calibration status, and unsupported conclusions
- reproduction path, versions, hashes, and citations

Use tables for comparable metrics and figures for trends or spatial fields. Do not repeat every raw value in prose.

## Scientific language

Use “the simulation predicts under the stated model” rather than “the device will”. Label uncalibrated simulations exploratory. Distinguish numerical convergence, physical validation, calibration, and experimental agreement. Show failed and warning validators without softening their status.

## Failure behavior

Do not describe a failed run as completed. A failure report may explain the last valid stage, evidence collected, and next safe action, but must not manufacture missing results.

## Evidence

Include bundle ID, simulator and adapter versions, input and runtime hashes, validation table, canonical artifact paths, citations, limitations, and transformations used for derived quantities.
