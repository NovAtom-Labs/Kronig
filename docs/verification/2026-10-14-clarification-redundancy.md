# Clarification quantity and state reconciliation

## Observed failure

The running desktop session retained the originally supplied metal work function
and the subsequently confirmed dielectric permittivity. The preparation model
declared the scientific inputs resolved, but the product's scalar-only quantity
check rejected scoped records. It generated new missing-value questions, and the
next preparation round repeated them. This was a backend completeness failure,
not a missing researcher answer and not merely a stale rendering problem.

The observed forms included a role-qualified energy key and a region record
containing a dimensionless material parameter. Neither requires a new physical
assumption to interpret.

## Implementation scope

- Extend descriptor-driven quantity checks to scoped records, arrays, canonical
  quantities and explicit unit-bearing keys. Reject wrong dimensions, nonfinite
  numbers, booleans, empty records and incomplete entries.
- Distinguish named/indexed entity scopes. A quantity for one contact cannot
  answer another contact's question. Nested voltage schedules do not satisfy or
  contaminate outer frequency bounds.
- Remove obsolete mechanically generated missing-value questions only when their
  required value is now valid. Preserve model-owned unit ambiguity, conflicting
  inputs and scientific choices for reasoning and researcher confirmation.
- Preserve confirmed quantities across rounds, including other entries of a
  partially updated aggregate. Do not discard the newly answered entry or let a
  model change another confirmed entry without an answer authorizing that change.
- Preserve original indices when retaining part of a quantity list. Similar
  entity names must remain distinct.
- Require literal scalar fast-path answers to contain a numeric literal. A reply
  consisting only of a unit must not become an implicit quantity of magnitude one.
- Preserve unanswered questions when recovering from a model's unauthorized
  expert choice of a researcher-controlled physical setting.
- Check new gateway output for valid, consistent machine paths and unique question
  IDs. Use the existing bounded model repair with precise mismatch diagnostics.
  Existing stored preparation records remain loadable; no persisted schema was
  tightened.

These changes do not inspect named devices, match problem-statement text, supply
physical defaults, or change simulator physics, numerical convergence criteria,
validation limits or result values. The test operator's prompt and answers remain
test data rather than production rules.

## Verification

The regression tests were reproduced failing before their respective fixes.
The focused preparation suite passes 100 tests. Desktop tests pass all 60 tests.
The clarification/supervisor and headless researcher-interface checks pass 22 tests.
Independent review reproduced and checked the multi-contact, coupled-study,
aggregate-update and older-record compatibility cases.

The current-session decision was replayed read-only: both redundant generated
questions clear without changing retained quantities. A live provider replay of
the recorded prompt and answers produces a ready compiled request. An isolated
fresh live submission has also completed one genuine clarification batch and
compiled without repeating the work-function or permittivity questions.

Live testing also exposed malformed model bookkeeping. The gateway validates and
repairs this rather than treating differently named unresolved metadata as new
scientific questions. A malformed response can still fail safely after the bounded
repair; this is not permission to guess an unresolved physical setting.

The complete Python regression suite passed 1,123 tests with 25 skipped in
1,099.94 seconds. The final focused preparation rerun passed all 100 tests after
refining the bounded model-repair diagnostics. Ruff and whitespace checks pass.

The final fresh live submission asked six genuine questions in one batch:
oxide unit, measurement method, temperature, substrate boundary, capacitance
normalization and sweep increment. After their researcher-authored answers, the
request compiled ready without additional clarification rounds. Work function
and dielectric permittivity were not asked again. The old-session read-only
replay likewise compiled ready with its stored answers.

Live checks for this change concern preparation and compilation, not a claim
that a new live numerical simulation was run. Generated provider responses,
diagnostics and session snapshots remain outside version control.

## Applying the source fix

The open desktop process retains its already imported Python code. A source
development relaunch is needed to use these changes. Inspection and verification
do not restart the researcher's application, modify its session database or alter
the selected research repository. Installed release binaries require a separate
rebuild; this change does not publish an installer or merge branches.
