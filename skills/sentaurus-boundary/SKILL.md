---
name: sentaurus-boundary
description: Use when compiling, executing, retrieving guidance for, or comparing results from the licensed Sentaurus backend.
---

# Operating the Sentaurus Boundary

Sentaurus is a licensed backend behind a controlled adapter and runner. It is not a prompt dialect and must not leak proprietary documentation into the product repository.

## Preconditions

Require the deployed Sentaurus version, configured authenticated runner, valid portable `ExperimentSpec`, supported capability decision, and version-compatible licensed guidance. Scientific capability and operational availability are separate.

## Execution path

1. Retrieve only authorized, version-matched guidance from the licensed-machine index.
2. Send the same portable specification used by other backends to the deterministic Sentaurus adapter.
3. Compile structure, mesh, device, and extraction artifacts only inside the controlled boundary when licence policy requires it.
4. Sign and submit a backend-specific job with no free-form shell payload.
5. Preserve native logs and outputs.
6. Normalize into `CanonicalResult`.
7. Run the same portable validators and evidence-summary builder.

## Semantic mapping

Treat model names as backend-specific mappings of portable intent. Defaults can differ across releases. Contacts, mobility, Fermi statistics, recombination, band-gap narrowing, interfaces, and output variables must each have an explicit mapping and versioned test. Never infer a command from DEVSIM syntax or from memory of another Sentaurus release.

## Cross-backend conformance

Expect semantic agreement, not identical meshes, solver iteration counts, or pointwise values. Align material parameters, physics models, contact semantics, bias history, units, and extraction definitions. Compare selected expert-owned metrics with declared absolute and relative tolerances.

## Security and licensing

Never commit proprietary manuals, copied examples, command decks, licence files, host credentials, or restricted excerpts. Do not expose an interactive SSH shell to the model. The remote service may return permitted structured answers, citations, compiled artifacts, status, logs, and normalized outputs according to access policy.

## Refusal conditions

Refuse to invent Scheme, Tcl, SDevice syntax, model mapping, or parser behavior when version-compatible evidence is unavailable. Refuse execution when runner, licence, authentication, signing key, or exact version is unconfigured.

## Evidence

Preserve Sentaurus version, licensed source IDs, adapter and runner versions, signed hashes, job identity, native logs, normalized result, validation report, and conformance evidence.
