---
name: devsim-compilation
description: Use when compiling an approved, capability-supported ExperimentSpec for the local DEVSIM backend or diagnosing its generated inputs.
---

# Compiling and Reasoning About DEVSIM

The deterministic adapter owns executable DEVSIM syntax. The agent reasons about intent and evidence, then uses typed compiler and runner boundaries.

## DEVSIM mental model

DEVSIM is a finite-volume device simulator controlled through Python. A device contains a mesh, regions, contacts, interfaces, parameters, models, equations, and solutions. Node, edge, element-edge, contact, and interface models have different numerical locations. Equations assemble residuals and Jacobian terms from those models. Symbolic derivatives are therefore part of a correct nonlinear formulation, not optional decoration.

For semiconductor drift-diffusion work, a typical dependency order is:

1. construct and finalize the mesh
2. create the device and regions
3. define material and temperature parameters
4. define doping and electrostatic quantities
5. create potential models and Poisson equation
6. establish equilibrium or initial carrier solutions
7. add carrier statistics, mobility, current, and recombination models
8. create contact and interface equations
9. solve equilibrium, then continue through requested operating points
10. extract native results for normalization

This is conceptual guidance. Do not write an ad hoc script when a typed adapter mapping is missing.

## Knowledge use

Before changing an adapter mapping, search the reviewed `DEVSIM Manual`, the pinned source tree, and official examples with backend and version filters. Confirm command arguments and model locations against the installed version. Examples demonstrate patterns, not product capability.

## Compilation workflow

Require a validated specification, a supported capability decision, and execution approval. Call `compile_experiment` with backend `devsim`. Preserve generated files, compiler version, input digest, runtime digest, and the exact simulator version. Execute only the returned entrypoint with an explicit budget.

## Units and signs

The portable contract uses SI. DEVSIM examples often use centimetres, inverse cubic centimetres, and current density per square centimetre. Conversion belongs exclusively inside the adapter and normalizer. Preserve terminal orientation and carrier-current sign conventions explicitly.

## Diagnosis boundary

If compilation refuses a request declared supported, classify it as an adapter defect. If DEVSIM rejects generated syntax, compare the generated command with version-matched manual evidence and adapter tests. Never patch generated files during a run. Fix the mapping and regenerate.

## Evidence

Keep the `ExperimentSpec`, capability decision, compiler and runtime versions, generated input files, hashes, entrypoint, run budget, stdout, stderr, native outputs, and citations used for a mapping decision.
