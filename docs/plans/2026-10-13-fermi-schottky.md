# Statistics-consistent Schottky boundary implementation plan

> For agentic workers: execute inline with systematic debugging and failing-first tests. Do not pause for design approval; the researcher explicitly authorized implementation.

Goal: support the original semiconductor metal-work-function contacts with Fermi carrier statistics, without replacing the boundary with ohmic contacts or the statistics with Boltzmann.

Architecture: preserve ExperimentSpec and existing contact/model identifiers. Implement the native Fermi-Dirac thermionic supply in the DEVSIM adapter. Keep canonical result extraction and validation authoritative. Open the capability only after actual numerical benchmarks. No named-device or sample-prompt production branches.

Tech stack: DEVSIM 2.9.1 native model expressions and Jacobians, pytest, deterministic adapter/runner, live Bedrock/OpenHands researcher driver.

Spec: this document, the original Al/p-Si/n-Si/Al request, user instructions, and AGENTS.md.

## Initial state and root cause

- Verified prior work committed and pushed as667c8952a317283848fe4c1ad39be7744dc271a0. Local/upstream match0/0; main unchanged.
- Fresh pre-commit suite916 passed,28 skipped; desktop60 passed.
- CapabilityService explicitly refuses semiconductor metal_work_function + fermi. Descriptor conflicts repeat that exclusion.
- Existing thermionic targets are Nc exp(-barrier/Vt), Nv exp(-hole_barrier/Vt), with a linear density-relaxation flux. Those Maxwell-Boltzmann reservoirs do not match Fermi bulk densities and can violate equilibrium detailed balance if the gate is merely deleted.
- The metal potential boundary is a Dirichlet work-function boundary; it remains a metal boundary.
- Existing Fermi bulk uses native Fermi/InvFermi, generalized quasi-Fermi-gradient transport, and Boltzmann-to-Fermi initialization.

## Physics and numerical design

For ideal elastic thermionic transmission across a three-dimensional parabolic band,
the carrier supply has order-one Fermi integral F1, while density uses F1/2.
Use J=A*T^2*(F1(eta_surface)-F1(eta_metal)), with the current/normal assembly
conventions already used by the adapter. Surface eta is InvFermi(carrier/DOS).
Metal eta comes from the actual local band energy and metal Fermi level=-contact bias.
At equilibrium both reservoirs have equal eta, yielding zero net current. In the
dilute limit F1(eta) tends to exp(eta), recovering the existing classical flux.

Use the same local effective band gap, BGN and density-of-states reference in the
electrostatic, carrier population and metal reservoir expressions. Do not freeze
classical targets from the unnarrowed bulk gap when BGN is enabled.

Evaluate F1 natively, not through Python-double callbacks. A stable dilogarithm
transform uses x=exp(-abs(eta)), z=x/(1+x)<=1/2, Li2(z)=sum z^k/k^2, and
F1(-abs(eta))=Li2(z)+log(1+x)^2/2. Positive eta uses the reflection identity.
Use96 terms and exact rational coefficient strings. The omitted series is bounded
by2^-96/97^2, below1.4e-33. This is a declared numerical series, not a substitution
of physical statistics. Provide the smooth analytical derivative F0(eta)=log(1+exp(eta))
using a stable branch, including eta=0. Native finite differences must verify the
complete contact Jacobian. Keep native extended arithmetic and provenance.

Primary references to verify:

- https://dlmf.nist.gov/25.12, equations25.12.1,25.12.3,25.12.4,25.12.14,25.12.16.
- DEVSIM commit43b41ca845184c47e22b72d144db7e7db8509377, src/MathEval/Fermi.cc and contact equation API/assembly.
- Sandia Charon User Manual, Schottky contact section: classical thermionic boundary and its stated Maxwell-Boltzmann assumption.

## Constraints

- Work in place on devsim-1d-expansion; no worktree or main merge.
- No additional push of new physics merely because the prior snapshot was authorized for push.
- Keep scalar temperature, full Poisson and both continuity equations, explicit metal work function and Richardson parameters.
- No tunnelling, image-force lowering, pinning, self-heating or invented interface physics.
- Do not weaken acceptance limits, conceal nonconvergence or substitute contact type/statistics.
- Current density remains per area unless a researcher supplies physical area.
- Source/version/hash/compiler/simulator/validation provenance must survive.
- Existing knowledge index must reflect any changed curated guidance; no proprietary documentation or credentials.

## Review focus

1. Equal reservoir Fermi levels must give zero current, including local BGN.
2. Fermi supply must differ from a Boltzmann supply near degeneracy and agree in the dilute limit.
3. Left/right and electron/hole normal signs must conserve conventional terminal current.
4. Zero eta and large signed eta must give finite values and accurate Jacobians without branch kinks or Python rounding.
5. Capability and knowledge changes must not advertise unverified dynamic, spatial-temperature or tunnelling combinations.

## Task1: Independent native F1 evaluation

Files: runtime.py private expression builder; tests/integration/test_devsim_fermi_schottky.py.
Consumes: native edge-model expressions. Produces: bounded supply expressions and explicit smooth derivative expression.

- [x] Write tests for native F1 values against independently integrated references at eta-500..100, including0, the smooth derivative, and dilute asymptotics.
- [x] Run and record RED for absent evaluator and under-resolved negative-tail derivative.
- [x] Implement stable native expression models with96 supply terms and112 log-series terms; bound nesting to8 per native model.
- [x] Run GREEN with actual DEVSIM, no Python callback.

## Task2: Statistics-consistent contact assembly

Files: runtime.py contact population/flux assembly; compiler.py provenance; capabilities/service.py; capabilities/descriptors.py; existing contact-gate tests.
Consumes: spec contact/model inputs and Task1 supply. Produces: native thermionic reservoir boundary with Jacobian and canonical provenance.

- [x] Add failing real equilibrium and low-bias tests with metal contacts + fermi, both endpoint orientations, BGN and both-metal contacts; assert barriers, flat equilibrium Fermi levels, negligible currents and conservation.
- [x] Use F1 supply only when Fermi is selected. Use local band energies for the metal reservoir and complete Potential/carrier/circuit derivatives.
- [x] Retain a classical supply and numerical initialization, correcting its local-band inconsistency exposed by the dilute benchmark. Seed metal equilibrium potentials generically; do not force carrier-neutral ohmic targets at metal boundaries.
- [x] Relax only the verified contact/statistics gate; retain full-equation dependency and unsupported physics gates.
- [x] Verify dilute matching and a genuinely degenerate response, not just compilation.

## Task3: Original request, regression envelope, live workflow and resources

Files: tests/integration; curated Schottky/Fermi guides and indexed resource metadata; README and verification report.
Consumes: Task2 native execution. Produces: reproducible exact original Al/p/n/Al equilibrium and requested biased evidence with no idealization switch.

- [x] Run original300K,1e17 dopings,4.10eV both metal boundaries with Fermi,mobility,SRH,Auger,BGN and requested canonical fields. Geometry is an explicit test researcher input, not a default. Junction Vbi is not substituted with a global contact-dominated potential range.
- [x] Run actual0,+2,-2V using bounded continuation; retain failed diagnostics honestly.
- [x] Verify metal barriers, BGN detailed balance, doping/temperature variations, a low-bias mesh refinement reference, and complete native contact Jacobians. Arbitrary high-bias mesh independence is not claimed.
- [x] Run equilibrium and biased researcher queries through live preparation, answer missing inputs, verify no Fermi/contact substitution, and audit canonical graph payloads headlessly.
- [x] Update capability guidance, physics provenance and searchable local knowledge to the measured envelope only.
- [x] Run complete pytest, desktop tests, Ruff/diff checks and independent final review. Do not claim whole-source typing clean: known51 baseline diagnostics exist.
- [x] Record results and unresolved boundaries in `docs/verification/2026-10-13-fermi-schottky.md`. Publication on the existing branch was subsequently authorized by the researcher, without a main merge or installer rebuild.

## Execution ledger

Pre-flight: Task2 consumes Task1 native model names/derivatives; Task3 consumes Task2 compiler/capability identity. Contract and canonical results are unchanged.
Ruling: keep native in-place execution and skip approval handoffs as explicitly requested throughout this workflow. Risk if wrong: new contact physics requires its measured benchmarks before promotion, not silent fallback.
Snapshot publication complete:667c895, fetched remote matches local, clean tracked checkout before new work.
Task1 complete: independent native integral and derivative benchmark passes. Ruling: split Horner expressions into8-deep model chunks because the native parser rejects96-deep nesting; same series retained, no reduced numerical accuracy.
Root-cause extension: initial metal/Fermi runs exposed classical SRH mass-action and BGN interface errors. Corrected degeneracy factors and a stable quasi-Fermi-affinity driving term preserve detailed balance; chemistry rather than raw densities is continuous across band-edge steps. Both-metal+BGN zero-bias regression now passes instead of producing a2.7mV Fermi-level step. This is required by the original SRH/Auger/BGN request, not an unrelated feature.
Task2 native evidence:3 focused tests passed in43.74s. The capability checker is open only in this uncommitted development checkout for public compiler tests; the agent-facing descriptor remains conflicted until expanded numerical coverage passes.

Final ledger: Task2 and Task3 completed within the measured equilibrium/DC envelope. Descriptor conflicts removed only for the supported scalar-temperature metal/Fermi pair; dynamic combinations remain gated. A full941-test suite and a fresh840-test unit/e2e rerun pass. Both live researcher workflows pass, and20,020 canonical plotting samples were audited. Review retry/provenance findings are resolved. Default execution budget300s fixes the observed live fine-mesh timeout without reducing physics or tolerance. The researcher subsequently authorized publication of all new changes on `devsim-1d-expansion`; rerun the complete suite before committing and verify fetched remote equality after pushing. No main merge or installer rebuild is authorized by this publication request.
