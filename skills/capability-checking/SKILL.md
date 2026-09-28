---
name: capability-checking
description: Use when selecting a simulator backend or determining whether requested TCAD physics and observables are supported.
---

# Checking Backend Capability

Capability is declared data, not a guess based on general simulator reputation.

## Evaluation order

1. Require a schema-valid `ExperimentSpec`.
2. Compare every requested dimension, material, profile, contact, equation, physical model, study, observable, and resource limit with the candidate manifest.
3. Keep scientific support separate from execution availability. A licensed backend may support the physics while its runner is unconfigured.
4. Return one of `supported`, `needs_input`, `backend_unsupported`, or `platform_unsupported` with exact field paths.

## Meaning of outcomes

| Outcome | Meaning | Next action |
|---|---|---|
| `supported` | The adapter declares a mapping for the complete request | Compile deterministically |
| `needs_input` | Scientific intent is incomplete | Ask one material clarification |
| `backend_unsupported` | The portable contract can express it, but this adapter cannot | Select another declared backend or propose scoped implementation work |
| `platform_unsupported` | The product contract cannot represent the request safely | Refuse and name the missing abstraction |

Do not map “the simulator probably supports this” to `supported`. A feature is supported only when the manifest, compiler, normalizer, validators, and tests cover it.

## Model compatibility checks

Check combinations, not isolated names. Fermi statistics can affect carrier relations and contact conditions. Mobility models may require field, doping, temperature, or interface quantities. Recombination models require parameters and carrier definitions. Band-gap narrowing changes intrinsic concentration and band references. A backend that lists each label separately still needs an implemented combined path.

Use `search_knowledge` to understand model meaning or version changes. Retrieved text can explain a capability declaration but cannot override it.

## No silent simplification

Never drop a requested model, collapse a nonuniform profile, replace a Schottky contact with an ohmic contact, reduce dimensionality, or omit an observable to make a backend pass. A researcher-approved simplification is a new specification with its own provenance.

## Backend selection

Prefer the backend that supports the request with the least semantic loss and has an available runner. DEVSIM is not a fake Sentaurus mode. Sentaurus is not selected merely because it is more comprehensive. Compare the exact requested contract.

## Evidence

Preserve manifest name and version, adapter version, execution state, every issue path, requested value, supported boundary, and any researcher-approved reformulation.
