---
name: physics-model-selection
description: Use when choosing carrier statistics, mobility, recombination, band-gap narrowing, generation, or transport models for a semiconductor experiment.
---

# Selecting Semiconductor Physics Models

Choose models from regime and evidence. More models do not automatically mean more accuracy.

## Start with the regime

Record material, temperature, doping range, electric-field range, carrier injection level, dimensionality, interfaces, and observables that matter. Search authoritative knowledge for each model's assumptions and parameters. Confirm that the backend capability manifest implements the combined model set.

## Core choices

| Mechanism | Consider when | Main caution |
|---|---|---|
| Boltzmann statistics | nondegenerate carrier populations | inaccurate under strong degeneracy |
| Fermi statistics | heavy doping or degenerate conditions | must remain consistent with contacts and intrinsic-density treatment |
| constant mobility | controlled baseline or low-field exploratory case | hides doping, field, and temperature dependence |
| concentration-dependent mobility | doping varies enough to affect transport | coefficients are material and calibration dependent |
| field-dependent mobility | strong electric fields affect drift velocity | driving-force definition differs by model and backend |
| SRH recombination | defects or minority-carrier lifetime matter | lifetime and trap assumptions dominate results |
| Auger recombination | high carrier concentration or injection | coefficients and temperature dependence need evidence |
| band-gap narrowing | heavily doped regions affect carrier statistics and junction behavior | must align with intrinsic concentration and statistics |

Do not activate tunnelling, avalanche, quantum correction, interface traps, self-heating, or optical generation unless the physical question requires them and the contract supports them.

## Selection test

For every model, write one sentence answering: what omitted mechanism would bias the requested observable, and in which region or operating range? If no defensible answer exists, keep the simpler baseline.

## Parameters and calibration

Model selection and parameter selection are separate. Never copy a silicon coefficient to another material. Preserve source, units, temperature range, doping range, and calibration context. Default parameters are simulator inputs, not universal physical constants.

## Comparative studies

Change one model family at a time and compare canonical metrics. A model sensitivity study can show dependence on assumptions; it does not identify the physically correct model without reference data.

## Refusal conditions

Refuse when required parameters have no authorized source, the combined model set is unsupported, or the requested conclusion exceeds the calibration range.
