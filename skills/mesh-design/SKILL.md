---
name: mesh-design
description: Use when selecting, refining, or validating a TCAD mesh for junctions, interfaces, high-field regions, or geometry-sensitive observables.
---

# Designing and Checking TCAD Meshes

A mesh is adequate only relative to a physical quantity of interest. Node count alone is not evidence.

## Where resolution matters

Prioritize material interfaces, metallurgical junctions, steep doping gradients, narrow layers, space-charge regions, inversion or accumulation layers, high-field peaks, generation hotspots, and geometric corners. Preserve region boundaries exactly.

For one-dimensional structures, estimate relevant length scales such as layer thickness and depletion width before choosing spacing. For multidimensional structures, consider geometry curvature and current crowding as well as field gradients.

## Refinement strategy

1. create a physically motivated baseline mesh
2. solve the baseline and preserve its bundle
3. refine locally where the target field or residual changes rapidly
4. rerun with identical scientific inputs
5. compare declared metrics using absolute and relative tolerances
6. stop when metric change is below the expert-owned threshold or report non-convergence

Avoid abrupt spacing ratios that harm conditioning. Do not refine the entire domain when only a local feature controls the answer.

## Metrics

Choose metrics before refinement, such as built-in potential, peak electric field, integrated charge, terminal current density, threshold proxy, depletion width, or recombination integral. A visually smoother curve is not a convergence criterion.

Peak quantities are especially mesh sensitive. Record whether a peak is a node value, interpolated value, or integrated estimate. Compare its position as well as magnitude.

## Interaction with physics

Mesh refinement cannot repair a wrong contact, missing model, invalid parameter, or inconsistent unit. Conversely, apparent model differences can be discretization differences. Hold physics fixed during a mesh study.

## Evidence

Preserve mesh generator version, dimensionality, region boundaries, spacing rules, node and element counts, refinement reason, metric values at each level, convergence threshold, and canonical result hashes.
