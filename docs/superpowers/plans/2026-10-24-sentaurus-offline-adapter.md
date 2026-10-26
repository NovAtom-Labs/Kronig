# Sentaurus offline adapter implementation

## Scope and authority

Implement on `feature/ssh-remote-tcad`, without a worktree, remote push, or merge.
The user approved implementation and synthetic testing before HPC access exists.
`ExperimentSpec` remains the authority. No named-device branches, invented areas,
silently omitted physics, copied proprietary manuals, or simulated qualification.

## Decisions

- Produce candidate SDevice decks, not a claim of licensed syntax or physics validation.
- Retain an external native `device.tdr` mesh boundary. Generating a thin 2D
  extrusion for a 1D specification would introduce geometry that was not requested.
  A true 1D mesh builder needs release-specific verification on the licensed host.
- Add a hash-bound mesh attachment and explicit native-deck review before SSH
  submission. Hash checks establish identity, not scientific mesh correctness.
- Keep native binary decoding outside the LLM. Accept strict exported tables with
  declared units and preserve operating-point coordinates in canonical datasets.
- No new dependencies and no changes to DEVSIM physics or validation tolerances.

## Task 1: deterministic compiler correctness

Write failing tests, then implement:

- Region-count-independent rendering with the declared supported materials/profiles.
- Selected equations and initial contact voltage offsets, not unconditional defaults.
- Exact DC and explicit-point targets, including decreasing and nonzero-start
  schedules. Use separate normalized-time continuation ramps and explicit endpoint
  snapshots rather than confusing volts with SDevice's normalized ramp step.
- Refuse still-unmapped physical/solver overrides, interfaces and profile sampling.
- Preserve compiler source maps, deterministic hashes, and candidate status.

Verify compiler and capability tests, including unsafe identifiers and unsupported
requests. Expected: all pass, native execution remains unqualified.

## Task 2: mesh binding and submission preflight

Write failing tests, then implement adapter-owned runtime preparation that copies a
provided mesh into a new bundle, hashes every input, binds it to the exact portable
specification, and records the exact release plus review reference. Verify all
bound files before making an SSH connection. Reject missing, modified, symlinked,
duplicate or path-escaping inputs. Do not mutate the original compiled bundle.

Use real temporary files for success/tampering cases; use a connection trap only
at the external SSH boundary. Expected: incomplete jobs cannot reach the network.

## Task 3: axis-aware exported results

Write failing tests, then implement strict versioned CSV/table import alongside
legacy JSON. Enforce field-to-unit compatibility, terminal identity, finite data,
explicit sign conventions, exact simulator/source provenance and bounded input.
Support multiple operating points and spatial grids without discarding bias,
capacitance-density/absolute-capacitance distinctions, or complex response values.
Never infer contact area or silently turn absolute currents into current density.

Use synthetic fixtures labeled as synthetic. Hand-computed SI expectations,
malformed/mismatched rows, failed points, wrong units, hashes and path traversal
must be covered. Expected: canonical datasets retain axes and workbench queries
can render them. These fixtures do not benchmark Sentaurus physics.

## Task 4: integration, review and verification

Exercise compile -> attach reviewed synthetic mesh -> export import -> results
query with varied region names, lengths, voltages and units. Test blocked/malformed
paths and preserve DEVSIM independence. Update operational docs and capability
claims, including the precise pending licensed-machine checklist.

Run targeted tests throughout, one independent final review, Python full suite,
desktop suite, lint, dependency synchronization and whitespace checks. Fix material
review findings using failing tests. Do not commit until the full suite passes.

## Progress ledger

- Pre-flight: compiler produces the bundle consumed by mesh binding and SSH
  preflight; exporter produces canonical datasets consumed by the existing results
  query. Keep old result schema readable and do not change the public spec schema.
- Ruling: native mesh generation and native binary export remain licensed-host
  integration work. Guessing those APIs would produce misleading offline passes.
- Task 1 complete: compiler regressions observed failing, then passing. Includes
  exact targets, offsets, region count, equation selection, numerical controls,
  unmapped parameters and explicit Schottky selection. Compiler output remains a
  candidate, not a native benchmark.
- Task 2 complete: mesh binding/tamper/symlink/missing-input tests passed. The
  original compiled directory is not modified; generated jobs fail locally if
  mesh/review is missing. Legacy hand-built runner jobs remain a separate,
  unqualified compatibility path.
- Task 3 complete: exported-table tests cover SI conversion, multiple axes,
  source hashes, complex values, invalid dimensions, aggregate resource budgets,
  point/axis membership, failed-point masks and alternate bias-axis identifiers.
- Task 4 complete: 85 focused adapter/SSH tests passed; 19 headless workbench
  tests passed, including a normalized Sentaurus export with selection and zoom;
  61 desktop tests passed. Full Python scientific regression suite: 1,434 passed,
  32 skipped, six dependency/runtime warnings in 1,080.59 seconds. Lint,
  requirements synchronization and whitespace checks passed. No physics or
  validation tolerances were weakened. No native licensed tests were run.
- Independent review found six material issues. Each was reproduced before its
  fix: hole-only Richardson override refusal, point/axis identity, mandatory
  provenance for generated jobs, terminal/schedule identity, pre-transfer JSON
  bounds, and bias-kind-based legacy projection. Focused tests passed afterward.
- Review boundary: native deck syntax, model/default equivalence, binary mesh
  correctness, proprietary exporter APIs, licensed execution, convergence and
  benchmark accuracy remain unverified. Cost of treating offline evidence as
  native qualification would be false scientific confidence, so execution stays
  explicitly unconfigured and no native-accuracy claim is made.
- Test-host tooling note: a GNU coreutils install attempt was stopped before
  OpenSSL changed because Homebrew wanted unrelated upgrades. It had installed
  texinfo and updated ca-certificates; the certificate post-install then completed
  successfully. Tests use their explicit POSIX deadline substitute on this Mac.
  No application dependencies or requirements locks changed.
