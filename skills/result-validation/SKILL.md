---
name: result-validation
description: Use when deciding whether simulator output is numerically complete, physically credible, and suitable for interpretation.
---

# Validating TCAD Results

Convergence is necessary but not sufficient. Validate normalized canonical data, not screenshots, prose, or log snippets.

## Numerical checks

- process exit and native-result availability
- requested operating-point count and ordering
- convergence status at every reported point
- finite values and consistent array lengths
- mesh coordinate ordering and dimensional units
- complete terminals and observables
- input, runtime, compiler, simulator, and artifact provenance
- repeatability or declared stochastic behavior

For sweeps, verify endpoints and monotonic ordering using decimal-safe expected points. Never discard a failed point and present the remaining curve as complete.

## Scientific checks

- terminal current conservation with absolute and relative tolerances
- charge-density sign and carrier-density nonnegativity
- equilibrium terminal currents near numerical zero
- electrostatic potential and electric-field consistency
- qualitative carrier dominance in doped regions when the stated regime supports it
- continuity across material interfaces according to modeled boundary conditions
- symmetry where the specification imposes symmetry
- sensitivity to mesh and solver controls for reported metrics
- expected limiting behavior, such as equilibrium, low-field, or zero-generation conditions

These are invariant checks, not substitutes for calibration. Use analytical estimates only as transparent order-of-magnitude references with their assumptions.

## Cross-backend comparison

Before comparing DEVSIM and Sentaurus, align geometry, material parameters, statistics, mobility, recombination, band-gap narrowing, contacts, temperature, bias definition, and units. Compare physical observables and derived metrics, not raw mesh nodes or deck text. Use absolute tolerances near zero and relative tolerances away from zero.

## Status rules

Call `validate_result`. The overall state is the worst mandatory check. A failed mandatory check forces a failed bundle even if the simulator returns zero. Warnings remain visible and must be explained. A waiver requires a versioned validation configuration and named human approval.

## Interpretation boundary

A validated run proves internal numerical and contract checks passed. It does not prove fabrication predictiveness, parameter calibration, model adequacy, or agreement with experiment.

## Evidence

Preserve check IDs, levels, statuses, measurements, limits, evidence origins, tolerance ownership, reference-case version, and canonical paths from which every reported number is derived.
