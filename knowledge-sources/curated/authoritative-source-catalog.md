# Authoritative TCAD Source Catalog

Status: routing catalog for public sources. Inclusion does not grant redistribution rights or make every source version-compatible with the installed backend.

## Vendored into the retrieval index

| Source | Authority | Licence and use | Scope |
|---|---|---|---|
| DEVSIM source at pinned commit | official primary | Apache-2.0 | implementation, examples, regression behavior |
| DEVSIM documentation at pinned commit | official primary | CC-BY-ND-4.0, indexed unmodified | command reference, equations, meshes, solver options |
| NovAtom curated guides | internal secondary, review required | NovAtom internal-use | portable reasoning and evidence policy |

## Public sources to consult and cite

- DEVSIM Manual: https://devsim.net/
- DEVSIM documentation source: https://github.com/devsim/devsim_documentation
- DEVSIM simulator source and official examples: https://github.com/devsim/devsim
- DEVSIM publications and citation instructions: https://devsim.org
- NIST publications search for semiconductor measurement, mobility, resistivity, and material-characterization references: https://www.nist.gov/publications
- Scharfetter-Gummel discretization paper: https://doi.org/10.1109/T-ED.1969.16566
- Shockley-Read trap-assisted recombination paper: https://doi.org/10.1103/PhysRev.87.835
- Hall recombination paper: https://doi.org/10.1103/PhysRev.87.387
- Caughey-Thomas mobility paper: https://doi.org/10.1109/PROC.1967.6123
- Slotboom-de Graaff band-gap-narrowing paper: https://doi.org/10.1016/0038-1101(76)90043-5

## Source-use rules

Use official versioned documentation for command signatures and simulator behavior. Use primary papers for model form and original assumptions. Use reviewed material registries for numeric parameters. Use textbooks and educational sources for orientation, never as an uncited source of simulator syntax or calibration values.

Do not copy paywalled papers or books into the repository. Record DOI, version, access state, and the specific claim supported. If the model cannot access a needed source through the authorized index, it must say that the evidence is unavailable.

## Sentaurus boundary

Synopsys Sentaurus documentation is proprietary and deployment-specific. It must remain on authorized licensed infrastructure. The public repository may contain only the portable contract, adapter interfaces, access policy, and nonproprietary conformance expectations. The remote knowledge service should expose version-filtered citations or permitted structured answers without copying manuals into Git.
