# Reviewed prescribed spatial temperature

Agent Kronig supports positive constant, linear, and linearly interpolated tabulated lattice-temperature profiles on one-dimensional silicon regions. This is a prescribed-temperature drift-diffusion model, not a heat-flow solve.

The local temperature drives thermal voltage, the Varshni silicon band gap, conduction- and valence-band effective densities of states, intrinsic density, equilibrium SRH reference densities, and the reviewed power-law electron and hole mobility. Edge transport uses averaged local thermal voltage and mobility in the Scharfetter-Gummel expressions. The canonical result can expose the exact `lattice_temperature` field.

The current benchmark envelope is Boltzmann statistics with constant-mobility, SRH, Auger, and Slotboom band-gap-narrowing selections under equilibrium or DC studies. AC, frequency, transient, temperature-sweep, Klaassen, high-field, Fermi, direct Schottky, and non-silicon profile combinations are refused before compilation until their local-temperature terms have independent references. No scalar temperature is silently substituted.

Constant 300 K profiles are benchmarked against the scalar-temperature path, allowing a 2 mV electrostatic tolerance and 0.2 percent carrier-field tolerance. Linear profiles are checked at both spatial endpoints and for positivity. Provenance identifier: `novatom.spatial-temperature.2026-09-29.v1`.
