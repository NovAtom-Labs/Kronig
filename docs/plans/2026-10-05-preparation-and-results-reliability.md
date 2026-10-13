# Preparation and Results Reliability Implementation Plan

Goal: implement the Downloads fix log and verify six live researcher workflows in the existing test repository, including concise informal requests and terse clarification answers.

Architecture: preparation retains a typed partial intent and applies a capability-driven completeness gate. Coupled bias and AC analyses are represented in ExperimentSpec and compiled by the adapter. Chat review uses a bounded surface with stable controls, and Results renders each section independently.

Reference: `/Users/satyagni/Downloads/Agent Kronig Fixes/prompt_preprocessing_and_clarification_fixes.md`.

## Constraints

- No production branching on device names or sample problem statements.
- Researcher-owned scientific values require explicit input or an explicit selection policy.
- Keep simulator syntax inside adapters and preserve canonical evidence and provenance.
- Preserve existing uncommitted changes and archive the exact test repository before clearing its contents.
- Use failing behavior tests before implementation. Run the full suite before any commit.

## Work and verification

- [x] Repair validation presentation collection/count collision and isolate section rendering errors. Test actual DOM rendering with mixed validation evidence.
- [x] Introduce descriptor-driven readable questions and deterministic missing-input detection over typed partial intent. Batch missing inputs, preserve explicit values, and keep model reasoning for unrecognized needs.
- [x] Retain partial decisions, answer-to-field mappings, and stable context across clarification rounds. Verify changed repository context invalidates the cache.
- [x] Bound preparation calls and repair retries, expose inference/validation/retry timing, and allow cancellation without launching a stale run.
- [x] Extend the portable AC study with explicit bias scheduling and spatial sampling. Compile and execute at every valid operating point, preserve failures, and refuse metadata-only executable requirements.
- [x] Enforce requested-study and requested-output traceability before plan approval and after execution.
- [x] Refactor plan/clarification layout into bounded review states with visible controls and compact composer. Verify compact, ordinary, and wide viewports. Native result zoom and reset were tested; arbitrary operating-system display scaling is not certified.
- [x] Present actionable validation evidence with a compact navigator status and navigable detail.
- [x] Verify live progress updates, terminal animation shutdown, and repository artifact creation events.
- [x] Archive and clear `/Users/satyagni/Documents/test`, then run two real Bedrock researcher prompts through clarification, plan, execution, and interactive Results, followed by four additional requests including concise informal prompts.
- [x] Inspect numerical evidence and plots, repair new defects with regression tests, and record exact outcomes and remaining limitations.

## Review focus

- Missing sweep step alongside complete bounds must ask before compilation.
- AC settings retained only as metadata must never become an executable plan.
- Valid numerical fields from a prior decision must survive later answers unchanged.
- Cancelled preparation must never create an execution runtime after provider completion.
- A long review at a short viewport must keep its actions visible.
- Failed operating points must remain masked in interactive plots and count as unmet scientific evidence.

## Execution ledger

- The original test folder was archived to Downloads before testing. Subsequent runs share the cleared folder without deleting earlier test evidence.
- Initial live runs exercised Gaussian implant transport and AC at every bias of a dielectric/semiconductor stack. Both produced in-app interactive results. Validation retained current-conservation warnings and a failed AC bias point.
- Ruling: retain numerical validation thresholds, even when a visually plausible plot fails them. Weakening tolerances would hide evidence rather than repair a solver or validate physics.
- Reference reruns compared default and tighter relative solver updates. Tightening from 1e-6 to 1e-10 recovered the missing AC bias point in the tested stack, but did not eliminate the current residual. A broader regression run gates any general default change.
- Ruling: reject the global tighter-default change. The full reference suite exposed convergence failures for advanced Fermi/BGN physics. Keep existing reviewed defaults and explicit per-experiment numerical controls. A single better C-V run does not justify a default that regresses other physics.
- Automatic spatial sampling requires an explicitly authorized method and count. Schedule quantiles provide coverage only and must not be labelled as physical accumulation, depletion, or inversion states without separate evidence.
- Literal clarification values may be applied without another model call only when their units and descriptor mapping are unambiguous. Free text still uses model reasoning.
- Extra native workflows cover dielectric frequency response, a short conducting-bar request, a short asymmetric-junction request, and equilibrium temperature dependence.
- No Git integration or installer publication is part of this request. Leave the verified source changes on the existing branch.
- The required fresh final reviewer reproduced cancellation, ambiguous coupled-study inputs, automatic-sampling scope loss, and falsely satisfied output traceability. All four received regression tests and fixes. A full-suite cancellation cleanup regression was also resolved instead of accepting a partially passing suite.
- Temperature studies now use canonical operating points in validation, failure classification, table rendering, and current summaries. Legacy bias-only records are retained for compatibility, not required for a non-voltage study.
- Evidence and recommendations: `docs/plans/2026-10-05-live-researcher-evidence.md`.
- Extra native stop/retry testing found a Bedrock rejection of an interrupted SDK tool history. Cancelled/failed execution histories now get a fresh SDK identity while preserving visible chat and healthy follow-up context. This is not persistent repository memory.
- The unbiased small-signal equilibrium baseline is now recognized as an executed dependency, while a biased schedule cannot falsely claim an omitted equilibrium point. Extra native fresh-calculation testing passed with seven valid frequency samples and all applicable checks passing.
- Concurrent desktop shutdown calls now share one cleanup promise. A failing process-tree test preceded the fix; the final native close removed the owned Electron and backend processes.
- Final verification: 788 Python/reference tests passed, 20 skipped; 46 desktop tests passed; three optional native DOM tests passed. Scientific warnings from the original transport and bias-AC runs remain reported, not hidden.
