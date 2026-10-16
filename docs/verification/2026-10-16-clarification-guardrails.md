# Clarification guardrails verification

## Scope

This change extends the existing preparation service, SQLite run state and desktop
clarification UI. It does not add a second workflow, cross-session memory, device-name
branches, simulator equations, weaker acceptance thresholds or an installer rebuild.

Answer provenance is append-only and bound by the server to field, question and
revision. Transactional acceptance prevents duplicate preparation launches from
concurrent or late replayed submissions. Current answers alone authorize patches to
confirmed intent. Missing-value reconciliation, grounded question reasons, semantic
state comparison and a bounded round budget prevent repeated clarification loops.

Final typed plan checks cover schema-addressable temperature, geometry, profile,
contact and study values. Existing scope, output, area and presentation checks remain
active. Equivalent unit spellings and dimension-order serialization are accepted;
different quantities are not. Arbitrary free-text intent is not mechanically certified.

## Regression findings

Tests first reproduced lost answers under reused IDs, forged bindings, paraphrased
duplicate questions, invented conflict quotations, repeated unresolved state, stale and
concurrent submissions, and draft leakage between unrelated fields.

Independent review reproduced three additional defects. Scalar corrections could
leave the old value in an aggregate contact record; superseded invalid answers could
justify another question; and a changed study could restore old frequency bounds over
new voltage bounds. Each received a failing regression before a targeted fix.

Additional tests cover duplicate question IDs, blank answers, metadata tampering,
unit-only answers, numeric answers to explicitly unit-labelled questions, serialized
dimension ordering, physics parameters omitted from a plan, and unit reformatting
incorrectly treated as a changed dependency.

A final live gate-stack case exposed supplied work functions nested inside contact
records. Lookup now follows explicit structured properties and consistent entity
identities (`contact`, canonical `id`, or `label`) without borrowing another contact's
value. Correction removal uses the same identity rules. Unasked, undeclared critical
paths trigger bounded model repair instead of becoming raw bookkeeping questions.
The targeted live gate-stack rerun passed with no repeated work-function question.

Explicit physics-override checks traverse the actual portable schema, including
structured inputs. They do not rely on model-name prefixes. A scientific model name
that is also a unit name is not mistaken for a numeric physical override.

## Live API and scientific evidence

All provider work used the configured Bedrock API, isolated repositories and isolated
application data. No user session was stopped or modified. Raw responses, questions,
timings, bundles and browser evidence remain in ignored `output/clarification-*` paths.

Four varied live preparation cases reached compiled requests: unequal work-function
contacts at equilibrium, quasi-static gate-stack C-V, a temperature comparison, and
absolute-current extraction requiring an area. Both the initial and repeated four-case
evaluations passed. They exercise missing temperature, measurement kind, bias schedule,
profile sampling, distinct contacts, area and short researcher responses.

The subsequent five-case live contract evaluation passed all five cases in 253.95
seconds: four supported preparation workflows and one required refusal of explicit
unrepresentable mobility overrides. The additional gate-stack rerun passed in 132.31
seconds after the nested-record fix. A separate live multi-round test deliberately
answered temperature with `300 V`, received a justified correction question, then
answered `315 K` and reached a compiled request while preserving both distinct metal
work functions. Legitimate invalid-unit follow-ups therefore remain possible.

### Complete live MOS workflow

The request specified 7 nm SiO2, 0.8 um p-Si, boron 8e15 cm^-3 and a 4.25 eV gate.
Researcher answers selected 300 K, quasi-static charge differentiation, a -2 to +2 V
gate sweep in 0.1 V increments, grounded substrate and profiles at -1.5, 0 and +1.5 V.

The full API, clarification, plan approval, OpenHands tool and native DEVSIM workflow
completed in 496.143 seconds after one clarification batch. All 41 points converged;
all 15 applicable scientific checks passed. There are 27 canonical datasets. The
bundle retains Fermi statistics, Klaassen mobility, native source and mesh evidence.
An independent read verified manifest hashes, finite values, model provenance, band
ordering and agreement of extracted capacitance with charge differentiation.

### Current extraction diagnostic and honest failure handling

The first attempt exposed a bare-number area in interpreted intent. The existing
area guard correctly refused it. Source-grounded unit normalization now retains the
researcher's 2 um^2 as a typed quantity rather than inferring a unit from magnitude.

The second attempt reached native execution after one clarification batch in 173.806
seconds. Both contact areas are 2e-12 m^2. Absolute current equals canonical current
density times that supplied area. However, it is not a passing scientific result:
charge-density mesh comparison failed by 7.14 percent for a near-zero residual field
whose magnitude is about 4.48e-12 C/m^3. Its review-needed status is retained.

This diagnostic also exposed that explicit custom constant-mobility values were not
representable by the current portable physics contract. A plan could formerly omit
them. New preparation and plan guards refuse such overrides, rather than certify a
default-mobility result as the requested calculation. Adding calibrated parameter
support and resolving near-zero mesh-comparison behavior are separate numerical work;
this change does not pretend either is solved.

### Result interface

The real MOS and diagnostic result payloads were rendered in headless Chromium at
1440 by 900 and 1200 by 600. Graphs render, selectable controls change selection, zoom
and reset work, and no JavaScript errors occur. The diagnostic remains marked as
needing review. This is an isolated browser check of the desktop renderer, not a claim
that a packaged native application was rebuilt or manually driven.

## Final verification

The frozen source passed the complete suite in two phases: 1,290 tests passed with
32 skipped in the parallel phase, then the native contact-Jacobian test passed alone
in 49.88 seconds. Total: 1,291 passed, 32 skipped. No test was omitted between phases.
The split keeps a CPU-heavy numerical benchmark out of parallel resource contention;
an earlier all-parallel run hit its unchanged 90-second subprocess timeout. Its first
isolated retest also passed in 40.89 seconds. Neither its derivative assertions nor
any scientific validation or execution limit was relaxed.

Additional evidence: 189 prompting tests passed, 18 clarification browser tests passed,
60 desktop tests passed, and Ruff and Git whitespace checks passed. Live cases and
actual result-rendering checks are described above. The skips include opt-in and
platform-specific coverage, not silent simulation approximations.

An initial full-suite run exposed one intermittent owner-monitor subprocess cleanup
failure in code unchanged by this task. A subsequent isolated five-case run passed,
the shutdown case passed eight additional repetitions, and the final complete suite
passed its monitor tests. This observation is not claimed as a fixed defect.
