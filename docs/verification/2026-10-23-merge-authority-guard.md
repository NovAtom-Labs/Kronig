# Merge-readiness authority guard

## Defect and scope

The prepared-plan authority check previously skipped every unresolved path. A
plan could therefore omit or rename a confirmed contact or region and evade the
check on that entity's typed values. The same gap affected out-of-range profile
indices and empty interface collections.

The guard now recognizes properties through the portable Pydantic schema,
including union variants, nested parameters and derived region thickness. A
missing schema-addressable confirmed input refuses preparation before plan
artifacts are written. It neither invents an entity nor borrows another one's
value. Researcher and repository provenance receive the same protection.

Free-text guidance remains unmapped. Declared structured input descriptors come
from the existing capability catalog, not a list of device names. Valid contact
IDs, endpoint selectors and explicitly supplied location aliases retain their
meaning. Existing output, display-unit, physical-area and profile-sampling checks
keep their own validation responsibilities.

No simulator equations, scientific acceptance thresholds, installer versions or
credentials were changed. This closes a typed-field preservation gap; it is not
a claim that arbitrary free-text intent has been mechanically certified.

## Regression evidence

Before the fix, 17 new missing-entity cases failed through the real
`DomainTools.prepare_experiment` path. Positive tests cover equivalent values,
valid entity aggregates, endpoint aliases and free text. Additional tests caught
a structured-record false positive and checked that explicit boundary aliases
still reject changed values. Existing scope and area regression tests caught
compatibility issues in the first candidate; those were corrected without
changing their assertions.

The focused prompting and agent-tool suite passed all 260 tests. Independent
read-only review found no remaining blocker in the final targeted diff.

## Final verification

- Complete Python suite in complementary phases: 1,316 passed and 32 skipped in
  the parallel phase (552.58 seconds), then the native contact-Jacobian benchmark
  passed alone (33.91 seconds). Total: 1,317 passed, 32 skipped, zero failures.
- The isolated benchmark retained its original 90-second timeout and derivative
  assertions. No test was omitted between phases. The split avoids native
  numerical workloads competing for CPU during a timeout-sensitive benchmark.
- All 60 desktop Node tests passed. Browser-renderer and OpenHands repository
  tests are included in the Python run. Opt-in live-provider and platform-only
  checks remain skipped; this follow-up did not make new paid model calls or
  rebuild native installers.
- Ruff passed for all changed Python files; Git whitespace checks passed.
- Non-failing warnings concern the existing FastAPI test-client deprecation,
  optional tmux availability and an upstream Pydantic TypedDict qualifier.

Integration is restricted to a fast-forward from the existing `main`, preserving
the tested source tree and all feature history. Remote publication and branch
cleanup follow only after the local merged-source smoke check passes.
