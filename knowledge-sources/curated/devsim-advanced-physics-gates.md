# DEVSIM 2.9.1 advanced-physics evidence gates

This note records why several requested capabilities remain disabled in the one-dimensional adapter. A mathematical primitive or suggestive helper name is not treated as proof of a complete transport model.

## Coupled Fermi-Dirac transport

This gate is closed for the reviewed one-dimensional silicon drift-diffusion envelope. The implemented equations, discretization, provenance, and measured acceptance boundaries are recorded in `devsim-fermi-transport.md`. Requests outside that verified envelope are not silently converted to Boltzmann statistics.

## Philips surface mobility in a one-dimensional adapter

The pinned `Philips_Surface_Mobility` helper creates two-dimensional element models and consumes interface-normal electric-field models. The official use case constructs those fields from two-dimensional current flow before applying surface mobility. A one-dimensional field normal to a dielectric interface is not a substitute for the lateral transport field and inversion-layer geometry required by that model.

Therefore Philips surface mobility is excluded from this one-dimensional expansion. It belongs in a future two-dimensional transport adapter with an independent benchmark.

Primary sources:

- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/python_packages/Klaassen.py
- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/examples/mobility/gmsh_mos2d_kla.py

## Surface recombination and interface traps

This gate is closed for explicit surface SRH and a single-level acceptor or donor trap in the reviewed one-dimensional envelope. Equations, charge convention, required researcher inputs, canonical outputs, and benchmark coverage are recorded in `devsim-surface-physics.md`. Trap distributions, tunneling, and frequency dispersion remain explicit exclusions.

## Direct metal-semiconductor Schottky transport

This gate is resolved for the reviewed one-dimensional Boltzmann boundary and Fermi thermionic equilibrium/DC envelope. Equations, parameter defaults, explicit exclusions, provenance, and benchmark coverage are recorded in `devsim-schottky-transport.md`. The combined Fermi/Schottky AC, frequency and transient gate remains closed pending reference benchmarks; it is not silently approximated.

## Spatial temperature profiles

This gate is closed for prescribed positive silicon temperature profiles inside the reviewed one-dimensional Boltzmann DC envelope. Local equations, compatibility refusals, provenance, and benchmarks are recorded in `devsim-spatial-temperature.md`. Heat-flow solution and the listed unbenchmarked combinations remain explicit exclusions.
