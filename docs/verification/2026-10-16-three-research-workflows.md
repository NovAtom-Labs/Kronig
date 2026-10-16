# Three research workflows: verification and remaining limits

## What was exercised

Live Bedrock/OpenHands preparation, researcher clarification answers, real DEVSIM
2.9.1 solves, canonical evidence validation, and the packaged Results Workbench
code were exercised in disposable local repositories. Browser tests used isolated,
authenticated instances of the same backend and frontend. They did not automate
the user's native Electron window. Sentaurus was unavailable and was not tested.

| Study | Final numerical outcome | Important qualification |
|---|---|---|
| Al / p-Si / n-Si / Al, equilibrium, 300 K, both dopings 1e17 cm^-3, work functions 4.10 eV | 19 checks passed, none failed | The initial uniform mesh needed an explicitly reviewed graded-mesh recovery. |
| The same structure, left contact +2 V and -2 V, right contact 0 V | 19 checks passed, none failed | The exact approved plan was verified through ExperimentEngine, initially with a 3600-second budget and then successfully with the normal 1200-second budget. This was not a fresh complete native-UI run. |
| 10 nm oxide / 1 um p-Si, Na 1e16 cm^-3, 4.1 eV gate, quasi-static -5 to +5 V in 0.1 V increments | 18 checks passed, none failed | All 101 points converged. Capacitance density was explicitly chosen, so no gate area was invented. |

Check counts include artifact and numerical checks. They are not counts of
independent experimental validations. Not-applicable checks remain separate.

Fermi statistics, Klaassen mobility, SRH, Auger, and Slotboom BGN remained active
in both metal-contact studies. Under bias, electron and hole quasi-Fermi levels
were requested explicitly instead of a single equilibrium Fermi level.

The high-bias run's first mesh comparison failed the unchanged 3 percent
criterion. The next comparison passed at a maximum relative Linf difference of
2.105543 percent. Original solve plus verification took 2354.93 seconds. Current
densities at the driven contact were +0.00584572 and -0.00700650 A/m^2, with the
opposite terminal balancing each value. This is numerical verification of the
specified classical model, not calibration or a tunneling/breakdown prediction.

The MOS capacitance density ranged from 3.44427e-8 to 3.38092e-7 F/cm^2, below
the geometric oxide capacitance of approximately 3.453e-7 F/cm^2. Independent
dQ/dV reconstruction and charge-balance checks were performed.

All 66 equilibrium, 54 high-bias, and 42 MOS bundle artifact hashes were checked.
Actual workbench tests exercised profile selectors, zoom/reset, compatible
overlays, converted CSV values, and styled SVG/PNG exports without JavaScript
errors. Test artifacts and provider responses are intentionally ignored by Git.

## General fixes, not prompt-specific branches

- Quantity parsing preserves dimensions, SI case, signs, and list ordering.
  Repository numbers acquire units only from an unambiguous cited excerpt.
- A changed study type requires researcher authority. Model format repair does
  not replace confirmed geometry, bias choices, or requested display units.
- Native current conditioning preserves the original equations and acceptance
  limits. Ordered operating points retain their continuation history.
- Equilibrium near-zero recombination mesh comparisons record an absolute
  resolution derived from the existing continuity-current tolerance. Biased
  recombination comparisons do not use that equilibrium-only allowance.
- Two isolated DC points do not generate a misleading finite-difference C-V
  curve. Canonical datasets retain all genuine requested fields.
- Plot exports preserve their actual styles. Overlay compatibility uses physical
  axes, not incidental axis identifiers. In-progress work is not a saved result.
- Requested root-selected terminal units also appear in the Markdown evidence
  summary, including complex responses. Canonical SI values are unchanged.

## Initial checkpoint verification

Checkpoint verification: the complete Python suite passed 1198 tests with 26
skipped and 7 existing dependency/runtime warnings in 1283.67 seconds. The
additional terminal-report selector regression and related report/presentation
tests passed 27 tests. The desktop Node suite passed 60 tests. Ruff and Git
whitespace checks passed. Opt-in provider calls and licensed Sentaurus tests are
not implied by the skipped pytest cases; live scientific workflow evidence is
described separately above.

## Native execution follow-up

The exact previously approved `+2,-2 V` plan was rerun through ExperimentEngine
with its normal 1200-second budget. It completed in 870.08 seconds, compared
with 2354.93 seconds before optimization. This is the total solve and mesh
verification time, not LLM latency. No provider call was made in this retest.

| Mesh | Before, seconds | After, seconds |
|---|---:|---:|
| Original | 480.86 | 155.40 |
| First refinement | 641.30 | 266.74 |
| Second refinement | 1232.77 | 447.49 |

For each mesh, all 31 canonical datasets, axes, operating-point records, and
continuation events are bit-identical to the reference. The final validation
report is unchanged: 19 checks passed and none failed. The first mesh comparison
still fails, and the second still passes at the same maximum 2.105543 percent
difference. Artifact hashes were verified through the actual Results Workbench
reader. Runtime source digests and elapsed times change as required by provenance.

Profiling identified extended-precision native expression evaluation as the hot
path. DEVSIM evaluates both branches of a vector `ifelse`, but short-circuits a
scalar condition. Vector extrema now select the same branch directly only when
every value is on the same side of the existing statistical breakpoint. Mixed
vectors use the original expression. The statistical approximation, derivative,
113-bit evaluation, physics models, voltage order, continuation, meshes, acceptance
thresholds, and validation policy are unchanged. No device name, prompt text, or
requested voltage selects this optimization.

Stop now carries the actual OpenHands per-run cancellation token through the
domain execution tool into both local and desktop-sidecar runners. Waiting polls
at most every 0.1 seconds. Cleanup sends termination, escalates when needed, and
reaps the owned native worker without killing the desktop backend or unrelated
runs. Tests include workers which ignore termination, cancellation between mesh
solves, cancellation during result hashing, and token isolation between runs.
Cancelled work cannot publish a completed bundle before the atomic commit point.
This does not claim cancellation of remote Sentaurus jobs or external hardware.

Packaged sidecar integrity checks now accept the real four-file compiler contract
and verify the composite runtime digest, including both numerical helper modules.
Tampering is refused before execution. An actual compiler-to-production-sidecar
test runs Fermi equilibrium physics and checks the canonical validation result.
The development launcher was exercised on macOS, not a rebuilt frozen installer
or a Windows host.

Run identifiers are validated before filesystem access. Execution claims its
work directory exclusively and refuses existing work, staging or final results.
Duplicate requests cannot clean up another execution's files. The experiment
engine cleans only work it owns; the bundle writer owns its staging cleanup.

Final follow-up verification on the complete changed source: 1224 Python tests
passed, 27 skipped, and 10 dependency/runtime warnings in 358.77 seconds using
four isolated pytest workers. The desktop Node suite passed 60 tests. The opt-in
relative native expression performance regression passed separately. Ruff and
Git whitespace checks passed. Skips do not constitute provider, licensed
Sentaurus, frozen-installer, or other-OS verification. No new live provider call
was needed for these native process and mathematical-evaluation changes.

Reproduce the relative timing check separately from scientific acceptance:

```bash
KRONIG_RUN_PERFORMANCE_TESTS=1 .venv/bin/pytest -q \
  tests/integration/test_devsim_statistical_evaluation.py
```

This optional benchmark compares the native legacy and optimized expressions
with identical values. Hardware-dependent timing is not a physical validation
threshold. Routine suites skip it unless explicitly enabled.

## Remaining limits after the follow-up

- High-bias extended-precision solves are still computationally expensive.
  This reference now completes inside the default budget, but harder structures
  or parameters can still require more time or fail convergence. A timing result
  is not a guarantee for all supported experiments.
- Built-in voltage is not automatically extracted as a dedicated scalar.
  Manual neutral-bulk comparison gave approximately 0.85218 V. The global
  potential span includes contact bending and must not be substituted for it.
- Separate conversational follow-ups can still repeat previously answered
  clarification context. Native close/popout/PDF operations were not verified
  by the isolated browser checks.

These limits must remain visible. No physics, acceptance threshold, or
researcher-specified parameter is to be dropped to make a demonstration pass.
