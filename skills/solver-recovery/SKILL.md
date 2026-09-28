---
name: solver-recovery
description: Use when a supported TCAD job fails numerically, times out, oscillates, or returns nonconverged operating points.
---

# Recovering TCAD Solver Failures

Recovery may change numerical strategy, never scientific intent. Preserve every failed attempt.

## Failure taxonomy

| Class | Typical evidence | Correct response |
|---|---|---|
| specification | invalid units, topology, references | repair the proposed spec with researcher-visible changes |
| capability | unsupported model, dimension, contact | refuse or select a supported backend |
| execution | missing executable, licence, transport, timeout | repair infrastructure, do not tune physics |
| initialization | equilibrium state fails | inspect boundary conditions, scaling, mesh, and initial solve sequence |
| continuation | earlier points converge, later point fails | reduce the step or continue from last converged state |
| mesh | invalid cells or unresolved sharp gradients | apply bounded local refinement and rerun convergence checks |
| model | singular or undefined expression, missing derivative | fix the deterministic adapter mapping |
| physical validation | solver exits but conservation or bounds fail | preserve the result as failed and investigate the model |

Read the first causal error, not only the final stack frame. Search version-compatible solver documentation when a diagnostic or solver option is unfamiliar.

## Recovery ladder

Use the least invasive justified action:

1. reproduce once with unchanged inputs and preserved logs
2. verify initialization order and contact consistency
3. restart from equilibrium
4. continue from the last converged operating point
5. reduce voltage or time step within recorded bounds
6. change numerical tolerances only with a stated reason and validation consequences
7. refine the mesh locally using a declared criterion
8. stop after three automatic attempts or earlier when the same failure repeats

Changing geometry, doping, material, temperature, contact type, equations, physical models, or requested observables requires a new researcher-approved experiment. Disabling a model to obtain convergence is not recovery.

## Mesh and scaling questions

Check whether depletion regions, interfaces, high-field zones, and steep doping transitions have enough spatial resolution. Check variable magnitudes and residual scaling. A finer mesh is not automatically better: abrupt refinement ratios can worsen conditioning, and a converged answer still needs a mesh-convergence study for sensitive metrics.

## Acceptance after recovery

Re-run every validator. Compare recovered results with the last valid state for discontinuities. Record changed numerical fields and show that scientific fields stayed identical.

## Evidence

Preserve failure class, cited diagnostic, attempt number, exact numerical changes, previous and new hashes, solver logs, convergence history, and before-and-after validation reports.
