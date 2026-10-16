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
| The same structure, left contact +2 V and -2 V, right contact 0 V | 19 checks passed, none failed | The final verification used the exact approved plan through ExperimentEngine with a 3600-second budget, not a fresh complete native-UI run. |
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

## Remaining gaps at this checkpoint

Checkpoint verification: the complete Python suite passed 1198 tests with 26
skipped and 7 existing dependency/runtime warnings in 1283.67 seconds. The
additional terminal-report selector regression and related report/presentation
tests passed 27 tests. The desktop Node suite passed 60 tests. Ruff and Git
whitespace checks passed. Opt-in provider calls and licensed Sentaurus tests are
not implied by the skipped pytest cases; live scientific workflow evidence is
described separately above.

- Stop interrupts the agent but does not yet terminate its blocking native
  DEVSIM job. This is the next lifecycle fix, not a claimed completed capability.
- High-bias extended-precision evaluation is slow. The default 1200-second
  budget was insufficient for the final three-mesh comparison above.
- Built-in voltage is not automatically extracted as a dedicated scalar.
  Manual neutral-bulk comparison gave approximately 0.85218 V. The global
  potential span includes contact bending and must not be substituted for it.
- Separate conversational follow-ups can still repeat previously answered
  clarification context. Native close/popout/PDF operations were not verified
  by the isolated browser checks.

These limits must remain visible. No physics, acceptance threshold, or
researcher-specified parameter is to be dropped to make a demonstration pass.
