# Semiconductor Equations and Equilibrium

Status: source-grounded internal guidance awaiting TCAD domain-lead review.

Scope: classical isothermal semiconductor device simulation. This document explains physical intent and validation relationships. It does not define simulator syntax or calibrated material parameters.

## Electrostatics

Poisson's equation relates electrostatic potential to total charge density:

`div(epsilon grad(psi)) = -rho`

For a conventional semiconductor sign convention,

`rho = q (p - n + N_D^+ - N_A^- + rho_fixed/q)`.

The exact potential sign and energy reference must be checked against the backend. Electric field is commonly `E = -grad(psi)`. This relationship supplies a useful validation check when both potential and field are available, but discrete differentiation must respect the mesh and field location.

## Carrier populations

Under nondegenerate Boltzmann statistics, electron and hole concentrations can be related to band energies and the Fermi level through exponential relations. At thermal equilibrium the Fermi level is spatially constant, provided all energies use one reference. The mass-action relation `np = n_i^2` is a Boltzmann, equilibrium relation and changes when degenerate statistics or effective intrinsic concentration models are used.

Fermi-Dirac statistics become important when carrier populations approach degeneracy. Turning on Fermi statistics is not an isolated formatting choice. Contact carrier relations, intrinsic density, band-gap narrowing, and density-of-states definitions must remain consistent.

## Thermal voltage and built-in potential

The thermal voltage is `V_T = k_B T / q`. For an abrupt, uniformly doped, nondegenerate homojunction with complete ionization and negligible band-gap narrowing, an analytical estimate is

`V_bi = V_T ln(N_A N_D / n_i^2)`.

This is an estimate under restrictive assumptions, not a universal validator. A TCAD extraction of built-in potential must define the two spatial reference points or band-energy difference used. Metal work functions and contact models can affect terminal-to-bulk potential references even when the internal junction relation remains recognizable.

## Equilibrium expectations

At equilibrium:

- externally imposed terminal voltages are fixed at their equilibrium values
- a single Fermi level should describe the connected structure
- drift and diffusion contributions may each be nonzero locally, while net electron and hole currents cancel to numerical precision
- net terminal current should be near zero according to absolute and relative tolerances
- space charge is concentrated where mobile carriers do not neutralize ionized dopants or fixed charge

An equilibrium request is not equivalent to “solve only Poisson” unless the specified model intentionally freezes or derives carrier populations. The equation set and contact definitions determine the actual equilibrium problem.

## Depletion estimates

For an abrupt one-dimensional junction under the depletion approximation, charge neutrality gives `N_A x_p = N_D x_n`. The total depletion width varies approximately with the square root of permittivity times electrostatic drop and inversely with doping. These relations are valuable order-of-magnitude and mesh-planning checks. They are not exact for graded profiles, heterojunctions, degenerate material, interface charge, narrow layers, or strong carrier spillover.

## Energy bands

Conduction-band and valence-band profiles depend on electrostatic potential, electron affinity, band gap, material offsets, and any narrowing or quantum correction. Never reconstruct energy bands from potential alone across dissimilar materials without explicit band-alignment data. State the energy zero and sign convention.

## Source basis

- DEVSIM Manual, release-matched command and equation documentation: https://devsim.net/
- DEVSIM source and `python_packages/simple_physics.py`: https://github.com/devsim/devsim
- S. M. Sze and K. K. Ng, *Physics of Semiconductor Devices*, background reference only, not redistributed
- W. Shockley, *Electrons and Holes in Semiconductors*, background reference only, not redistributed

All numerical material constants must come from versioned registries or a cited, regime-appropriate source.
