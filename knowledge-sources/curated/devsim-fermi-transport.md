# Reviewed one-dimensional Fermi transport in DEVSIM

Agent Kronig enables `model.fermi` only with coupled Poisson, electron-continuity, and hole-continuity equations. It is mutually exclusive with `model.boltzmann`. The implementation is simulator-specific and remains inside the DEVSIM adapter.

The charge model uses DEVSIM's native Fermi and inverse primitives with silicon conduction- and valence-band effective densities of states. In pinned version 2.9.1 these are the Joyce-Dixon approximation and its numerically inverted counterpart, not an independently exact order-half quadrature. Ohmic carrier targets are obtained by solving the local Fermi charge-neutrality equation rather than reusing Boltzmann targets. A bounded Boltzmann-to-Fermi continuation initializes the nonlinear equilibrium solve, after which the final equations contain only the Fermi expressions. Metal contacts use the order-one thermionic supply described in `devsim-schottky-transport.md`, not ohmic carrier targets.

Carrier current is reconstructed on each one-dimensional edge from the quasi-Fermi gradient:

`J_n = q mu_n n_edge grad(E_Fn)`

`J_p = q mu_p p_edge grad(E_Fp)`

The arithmetic edge carrier density and all analytical derivatives are included in the Newton system. This is an explicit finite-volume discretization and is not described as DEVSIM's Scharfetter-Gummel formulation.

Verified boundaries for this implementation are:

- nondegenerate equilibrium agrees with the reviewed Boltzmann implementation within 3 percent for potential and carrier-density fields;
- a symmetric silicon junction doped to 5e19 cm^-3 is neutral at both ohmic endpoints within 0.2 percent of the dopant charge scale;
- its zero-bias terminal current is below 1e-3 A/m2, equivalent to 1e-7 A/cm2;
- biased transport conserves terminal current within 0.5 percent.

These tests do not claim convergence for arbitrary doping, mesh, or bias. The current verified upper benchmark is 5e19 cm^-3 on the repository benchmark mesh. Unsupported or nonconvergent inputs are reported, not replaced with Boltzmann statistics.

The added metal-contact equilibrium/DC benchmark envelope includes both endpoint orientations, BGN/SRH/Auger equilibrium detailed balance, and explicitly requested 0,+2,-2 V points for the original aluminum/silicon study. Fermi plus Schottky dynamics and prescribed spatial temperature remain unbenchmarked and refused. Fermi drift/diffusion decomposition also remains refused. For equilibrium with BGN, carrier chemical potentials are continuous across adjacent silicon regions even when carrier densities differ at a local band-edge step.

Pinned primary implementation references:

- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `src/MathEval/Fermi.cc`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `testing/Fermi1.py`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `python_packages/fermi_physics.py`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `python_packages/simple_dd.py`

Product implementation identifier: `novatom.fermi-gradient.2026-09-29.v1`.
