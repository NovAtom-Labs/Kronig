# Schottky contacts with Fermi statistics: implementation evidence

Branch: `devsim-1d-expansion`. Simulator: DEVSIM 2.9.1. Compiler and adapter identity: 0.2.2.

## Publication boundary

The earlier research-workflow snapshot was committed with a detailed message as `667c8952a317283848fe4c1ad39be7744dc271a0` and pushed to `origin/devsim-1d-expansion`. At verification completion the new physics and plotting work remained local. The researcher subsequently authorized committing and pushing all of these fixes on the existing branch. This document accompanies that publication, following another complete-suite run and remote synchronization check. Main is not merged or modified, and installers are not rebuilt.

## Root causes and corrections

1. The adapter explicitly forbade Fermi plus silicon metal contacts. Removing the guard alone would have retained incompatible classical carrier reservoirs.
2. Thermionic Fermi supply now uses native order-one F1 integrals, with local band/DOS metal reservoirs and explicit smooth F0 Jacobians. Density still uses the pinned native Joyce-Dixon Fermi approximation and its inverse. These are distinct functions, not a Boltzmann substitution.
3. SRH, Auger and surface recombination now share statistics-consistent detailed balance. Same-silicon interfaces use continuous quasi-Fermi energies when Fermi statistics or doping-dependent BGN changes the band reference.
4. Electron/hole contact normal signs were corrected using native additive contact assembly. Reduced Richardson transmission now increases contact resistance without reversing current polarity.
5. Local temperature/BGN band references also correct the older classical contact branch and classical BGN ohmic targets. A parameter benchmark previously expected a pinned ohmic conduction-band endpoint to shift with BGN; the corrected benchmark measures the narrowed gap and valence-band shift instead.
6. Large adaptive transport bias changes use bounded thermal-scale continuation and native checkpoints. Initial failures count toward retry limits; successes are not failed retries. A stationary equilibrium predictor avoids unnecessary continuation when its composition-based applicability conditions hold. Requested-point provenance remains explicit.
7. The classical abrupt neutral-bulk p-n analytical reference no longer applies to metal barriers, Fermi/BGN, imposed charge, nonzero terminal offsets or prescribed spatial temperature. Its acceptance limits were not loosened. Whole-device potential range is not a junction-specific built-in potential in a Schottky structure.
8. A fine-mesh live run exceeded the old 120-second product execution default. The generic default is now a bounded 300 seconds; explicit caller budgets take precedence and the engine records the actual budget. No failed point is discarded or accepted.

## Numerical and scientific evidence

- Native F1 supply and F0 derivative agree with independent quadrature and stable derivative references at eta from-500 to100, including zero. A negative-tail regression rejects cancellation to zero.
- Both-metal equilibrium with Fermi, SRH, Auger and BGN has flat quasi-Fermi levels and negligible terminal currents. Temperature checks at280 and340 K preserve the actual0.05 eV aluminum electron barrier.
- A degenerate reservoir differs from a Boltzmann population. A dilute metal-contact equilibrium agrees with the classical reference.
- Electron/left and hole/right contact passivity checks respond correctly to explicit Richardson changes and conserve current.
- All12 native endpoint Potential/carrier contact Jacobians match finite differences.
- A biased contact current agrees within2 percent between5 and2.5 nm benchmark meshes. This is a measured low-bias refinement reference, not a blanket high-bias or arbitrary-mesh accuracy guarantee.
- The original two1 um silicon regions, both doped1e17 cm^-3, both Al work functions4.10 eV,300 K, Fermi/SRH/Auger/BGN execute at0,+2,-2 V with scientific validation passed. Additional assertions verify each biased metal barrier against its own metal Fermi reference and canonical density, current, field, mobility and recombination units.

## Live researcher workflows

The harness uses the real prompt preparation, clarification API, OpenHands runtime, scientific plan approval, deterministic simulator execution, validation, canonical result API and workbench data selection. Test-only researcher answers are not production prompt rules.

| Workflow | Clarification batches | Duration | Execution and validation | Canonical datasets |
|---|---:|---:|---|---:|
| Original-style Al/p-Si/n-Si/Al equilibrium |1|118.381 s|Passed|32|
| Same parameters at reverse, zero and forward2 V |1|321.775 s|Passed|35|

The biased live run retains Fermi, Klaassen mobility, SRH, Auger and Slotboom BGN with actual metal-work-function contacts at both ends. Its approved schedule is-2,0,+2 V. Canonical terminal current densities are:

| Applied left voltage | Left current density | Right current density |
|---:|---:|---:|
|-2 V|-0.007017592792907536 A/m²|0.007017592792189758 A/m²|
|0 V|-2.6513063751531963e-12 A/m²|9.49460298638204e-17 A/m²|
|+2 V|0.006281519206138938 A/m²|-0.006281519206138938 A/m²|

These are model outputs, not calibrated experimental predictions. Initial failed attempts remain in ignored verification output: one exposed the inapplicable classical reference and another the old execution timeout. Neither failure was concealed by changing physics or tolerances.

## Results and graph representation

- The real workbench dataset selector and bias-slice functions were audited headlessly against canonical API data. No valid dataset disappeared; all units, values, spatial coordinates and validity flags stayed intact.
- Equilibrium:32 datasets,32 plotted slices,4,138 samples checked.
- Biased:35 datasets,81 plotted slices,15,882 samples checked.
- Signed-log scaling now uses `log1p` so small nonzero currents do not disappear. Log and signed-log tick labels invert the transform into the original physical units, rather than labeling exponent values as amperes or other physical units.
- Interface duplicate coordinates are retained as native one-sided samples, not averaged away. Current density remains per area unless the researcher supplies physical area.
- Potential range stays labeled as potential range. Junction-specific built-in potential requires appropriate semiconductor bulk references; it must not be inferred from the largest contact-induced band bending. Tiny equilibrium currents and Fermi variations below numerical acceptance are residuals, not evidence of meaningful transport.
- Reusable audit: `node scripts/verify_result_plot_data.cjs <result-api-json-or-canonical-json>`.

## Regression and review

- Fresh publication rerun: 942 passed, 28 skipped, 6 warnings in 1020.24 s. Desktop rerun: 60 passed. Both workbench audits were rerun against the saved live canonical data and checked all 20,020 samples again. Ruff, staged diff checks and credential-pattern scans passed before publication.
- Complete suite: 941 passed, 28 skipped, 6 warnings in 727.09 s. Skips include unavailable licensed/infrastructure tests, not silently successful capabilities.
- Fresh unit and end-to-end rerun after late budget/plot changes: 840 passed, 27 skipped, 4 warnings in 73.68 s.
- Native desktop shell: 60 tests passed. JavaScript workbench/chart helpers: 20 passed.
- Dedicated agent budget tests: 24 passed; original biased band/unit recheck passed in 110.15 s. A subsequent 23-test capability run confirms the DEVSIM dynamic gate does not restrict other backends.
- Ruff and `git diff --check` pass. Known whole-source typing baseline is not claimed clean.
- Independent review found no critical physics defect. The requested-point event, retry accounting and surface-physics provenance findings were corrected with regressions. Mesh evidence was added. Unchanged Joyce-Dixon approximation accuracy and explicitly excluded physics remain documented limits.

## Remaining bounds

This is a silicon-first, one-dimensional ideal thermionic equilibrium/DC implementation. Combined Fermi/Schottky AC, frequency and transient response remain refused pending their own reference benchmarks. Prescribed spatial temperature, tunneling, image-force lowering, contact-state distributions, self-heating, avalanche and real-device calibration are not supplied by this change. The successful references do not establish convergence or discretization accuracy for every geometry, doping, mesh or bias. Scientific acceptance remains specific to each run and available evidence.

Primary mathematical and implementation references are linked in `knowledge-sources/curated/devsim-schottky-transport.md`. The local index was rebuilt from3,513 passages across four available sources, preserving content hashes and source versions. No proprietary Sentaurus documentation or credentials were added.
