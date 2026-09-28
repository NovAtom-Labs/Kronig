---
name: specification
description: Use when translating a semiconductor research request into an ExperimentSpec or deciding which scientific details require clarification.
---

# Building Simulator-Neutral Experiments

The `ExperimentSpec` is the scientific contract. Describe geometry, materials, profiles, contacts, equations, models, studies, and observables without assuming a named device workflow or simulator language.

## Decision guide

1. Identify the scientific question before choosing a structure or sweep.
2. Extract only facts stated by the researcher. Preserve every supplied unit.
3. Separate required facts from optional refinements. Ask only when a missing choice changes the physical problem, backend capability, or interpretation.
4. Use `search_knowledge` for physics terminology, model scope, or simulator behavior that is not encoded in a registry. Do not use retrieval to invent missing intent.
5. Normalize into `ExperimentSpec`, call `validate_spec`, then call capability checking.

## What must be explicit

- ordered regions, interfaces, dimensions, and material identity
- donor and acceptor profiles, including species, sign convention, magnitude, and spatial dependence
- contact locations, electrical semantics, work function when relevant, and driven terminal
- temperature, equilibrium or bias history, and requested outputs
- transported equations and physical models
- sweep endpoints and step meaning
- symmetry, dimensional reduction, and any effective area used to convert density into total current

Never infer a micrometre value as metres or convert concentration by intuition. Store researcher units at the boundary and rely on the unit system for normalization.

## Material clarification rules

Ask when the request omits a contact type, material at a region, sweep terminal, temperature for temperature-sensitive physics, or geometry needed to define the domain. State an assumption instead of asking only when it is conventional, low-impact, reversible, and represented explicitly in the proposed specification. The researcher must see that assumption before execution.

Do not ask for simulator syntax, mesh command names, or file layout. Those are implementation choices owned by adapters.

## Composition, not taxonomy

A p-n junction, p-i-n stack, MOS capacitor, resistor, and transistor are human descriptions. Product behavior must not branch on those labels. Two requests that normalize to the same regions, profiles, contacts, physics, and study are the same executable experiment.

## Stop conditions

Refuse to continue when units are ambiguous, regions overlap or leave unintended gaps, a profile references no region, a contact cannot be placed, the study contradicts itself, or a requested observable has no definition in the portable contract. Name the exact field and the smallest clarification needed.

## Evidence to preserve

Record the original request, clarification answers, normalized specification, assumptions, schema version, unit conversions, and validation result. Do not place free-form backend code in metadata.
