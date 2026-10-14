# Schottky, Fermi and Klaassen verification

## Scope

This change concerns the DEVSIM adapter's one-dimensional stationary carrier
transport. `ExperimentSpec` remains simulator-neutral. Neither a device name nor
a researcher prompt selects the numerical implementation.

The full reference uses two silicon regions, each 1 µm long, opposite uniform
doping of 1e17 cm^-3, two metal work functions of 4.10 eV, and 300 K. It retains
Fermi statistics, Klaassen mobility, SRH with 1 µs electron and hole lifetimes,
Auger recombination and Slotboom band-gap narrowing. Both voltage polarities and
the equilibrium baseline must converge. Absolute current is not invented when
the researcher supplies no area; terminal results are current densities.

## Causes and changes

The pinned native statistical inverse had inconsistent coefficients, an
unmatched branch and an inconsistent high-branch derivative. The adapter now
owns one matched Joyce-Dixon/Sommerfeld law for forward values, inverse values
and derivatives. The source, version and approximation accuracy are recorded.
Independent integral quadrature tests cover sampled reduced energies from -100
to 100. Sampled density error is below 0.22 percent, and derivative error below
0.62 percent. This is not described as exact integral quadrature.

Raw-density Newton updates could become negative and stall in clipping. The DC
solver uses positive, thermal-scaled logarithmic coordinates. This is a change
of numerical unknowns, not a substitution of Boltzmann statistics. All node,
edge, contact and interface derivatives follow the coordinate transformation.

Extended native equations are exported to a double sparse matrix for the
configured linear solver. Cancellation could lose weak generation/contact
terms controlling the common carrier mode. For eligible conducting stacks with
flux contacts and continuous interfaces, one physical row is replaced by the
equivalent integrated continuity balance, assembled from individual native
source and boundary models. It is an algebraic row combination, not a changed
physical equation. Other boundary semantics retain ordinary assembly. A
three-region manufactured operator verifies residuals, interface constraints,
both boundary signs and cross derivatives against native physical rows.

Numerical trial directions are bounded by the thermal scale. Final acceptance
requires an unscaled direction, actual native density updates in the original
units, the original potential errors and the original strict absolute and
relative convergence limits. Failed steps restore native state. Temporary
Poisson-only gate predictors bypass the carrier certificate and explicitly
restore carrier coordinates before the full coupled solve.

A fixed reported voltage grid no longer implies one large Newton jump between
points. The positive-density solver may construct internal starting states
through bounded voltage continuation. The original point list, order and
reported study strategy are preserved. Explicit adaptive controls remain
authoritative, retry allowances are unchanged, and the internal controls and
their purpose are recorded in solver events. This numerical initialization does
not simulate or report an unrequested physical voltage sweep.

Adaptive initialization may backtrack, but finishes only at full Fermi
statistics. No partial statistical blend is an accepted physical result.

## Scientific output semantics

Conducting contacts at different voltages generally require separate electron
and hole quasi-Fermi levels. The product refuses an incompatible single
Fermi-level request instead of presenting their midpoint as a physical Fermi
level. Stationary electrostatic gating with a common carrier reservoir remains
distinct from driven carrier transport. The rule uses boundary and study
semantics, not device labels.

All adapter helpers accompany a compiled job and participate in its composite
runtime hash. The implementation identifiers are
`kronig.joyce-dixon.matched.v1`,
`kronig.positive-density.conservative-dc.v1`, and compiler 0.2.4. Existing
PyInstaller source-package collection includes the helpers for future builds.
Previously installed release binaries have not been rebuilt by this change.

## Verification record

| Evaluation | Observed result |
| --- | --- |
| Original uniform 5 nm mesh, -2/0/+2 V | Native execution completed in 238 seconds; 12 applicable checks passed |
| Fixed reported -2/0/+2 V grid, same physics and 5 nm mesh | Native regression passed in 210.56 seconds; all original checks passed and all three points remained explicit |
| Exact fixed-grid specification that failed in the live agent | Passed in 223.28 seconds with all 15 applicable checks; all 27 requested outputs, including current components, retained |
| Exact live-generated specification with 1 nm junction refinement | 808 spatial nodes, all three points converged; 15 applicable checks passed within the diagnostic 600-second allowance |
| Independent statistical values and slopes | Passed integral, inverse consistency, branch continuity and derivative checks |
| Original physical acceptance | Passed scaled-final rejection, missing/nonfinite evidence and iteration-budget regressions |
| Contact/interface algebra | Passed asymmetric three-region native residual and Jacobian comparison |
| Other stationary boundaries | Passed metal/ohmic equilibrium, other temperatures, manufactured current components and Fermi gate predictor regressions |
| Refined canonical result in Chromium | 33 graphable datasets; operating-point selection and zoom/reset passed for every dataset; no renderer errors or width overflow in three tested viewport sizes |
| Final live researcher workflow | Completed in 340.08 seconds including one clarification round, plan review and execution; execution, numerical validation and output coverage passed; 16 applicable checks passed |
| Final live result in Chromium | 31 graphable datasets; every dataset's selection and zoom/reset passed; no renderer errors in the audited result |
| First complete Python suite | 1,075 passed, 25 skipped |
| Complete suite with the final numerical implementation | 1,084 passed, 25 skipped in 1,103.67 seconds |
| Additional asymmetric physical regression | Different lengths, doping, work functions, 315 K and opposite driven endpoint; passed in 46.04 seconds |
| Post-review unit confirmation | 947 passed, 9 skipped after the metal-on-dielectric gate classification fix |
| Desktop shell tests | 60 passed |

The finer live-generated run originally hit the old 300-second execution
budget while still progressing. Agent execution now has a bounded 600-second
default. Explicit caller budgets still win and the ledger records the actual
allowance. This changes available runtime, not scientific acceptance. A timeout
remains a failed execution.

Earlier complete Python runs passed 1,075 and 1,076 tests respectively. A further
live run exposed a direct fixed-grid jump failure, now resolved by the recorded
internal starting-state construction. The exact failed specification and final
live-API workflow both pass. The complete numerical suite then passed 1,084 tests.
Final read-only review found a contact classification error in the single-level
guard: a metal on a dielectric is an electrostatic gate, not a carrier injector.
That error was reproduced, corrected using the adjacent material, and verified
by schema-valid ideal/metal gate cases and a fresh run of all 947 unit tests.

The final pre-publication complete Python suite passed 1,086 tests with 25
skipped in 1,058.46 seconds. Desktop tests passed all 60 tests. Ruff and staged
whitespace checks passed. This run includes the asymmetric native regression
and the dielectric metal-gate classification regression.

Skipped tests require optional external/native capabilities. The full-bias
Schottky/Fermi/Klaassen regression is an ordinary integration test, not an opt-in
skip or an expected failure. Source publication does not replace installed
release binaries. Restart the source-development application to load the
updated backend. No main-branch merge or installer rebuild is included.

Scientific acceptance code and configurable limits were not changed. The
validation policy digest remains
`e3a523804104701c06c1b3893e5c4f70a9db6dc0e1cb2e0991e4a63789bc6d7a`.

## Limits

Passing these checks does not establish calibrated experimental accuracy or
convergence for arbitrary doping, contact models, temperature, mesh or bias.
Uniform versus refined benchmark terminal currents differ by approximately
1.3 percent at forward bias and 0.6 percent at reverse bias. This is refinement
evidence, not a general mesh-convergence certificate.

The four inapplicable checks in the refined reference concern a dense bias
sweep, paired AC capacitance, unrequested generation datasets and a missing
integrated bulk-charge balance. They are not counted as passes. Current
conservation, field/potential consistency, Poisson consistency, requested
output presence, band ordering and recombination reconciliation do pass.

Fermi/Schottky dynamics and prescribed spatial-temperature combinations retain
their existing benchmark gates. No simulator-core installation, proprietary
documentation, credential change or release publication is part of this work.

## Researcher prompt and clarification answers

The successful live workflow used this prompt in an empty repository:

> Study a one-dimensional Al / p-Si / n-Si / Al structure at 300 K using DEVSIM. The p-type silicon has uniform boron doping of 1 × 10¹⁷ cm⁻³, and the n-type silicon has uniform phosphorus doping of 1 × 10¹⁷ cm⁻³.
>
> Both aluminum contacts have a work function of 4.10 eV. Model them as actual Schottky contacts, not ohmic contacts. Use Fermi statistics, Klaassen mobility, Shockley-Read-Hall recombination with electron and hole lifetimes of 1 µs, Auger recombination, and Slotboom band-gap narrowing.
>
> Compare equilibrium with forward bias of 2 V and reverse bias of 2 V. At each operating point, show the electrostatic potential, electric field, electron and hole concentrations, space-charge density, conduction and valence bands, electron and hole quasi-Fermi levels, current densities, carrier mobilities, and recombination rates.
>
> Present the comparisons as interactive results inside Kronig. Check convergence, current conservation, and consistency between the electric field and potential. Ask me for missing physical inputs before starting, and clearly explain any limitations instead of substituting simpler physics.

The final live run asked only for geometry. Its exact answer was:

> Use 1 µm of p-type silicon followed by 1 µm of n-type silicon. The p-region extends from x = 0 to 1 µm and the n-region from x = 1 to 2 µm, with an abrupt junction.

Other tested runs also asked about contact convention. If asked, answer:

> Keep the right, n-side aluminum contact at 0 V. Apply +2 V to the left, p-side contact for forward bias and −2 V for reverse bias. Include both contacts at 0 V as the equilibrium baseline.

If asked about area, density outputs need no area:

> Report current densities in A/m², not absolute currents in amperes. I am not specifying a cross-sectional area.

Question wording and grouping can vary. These are physical researcher choices,
not prompt-specific production rules. The verified outputs retain all three
operating points and open in the interactive Results Workbench.
