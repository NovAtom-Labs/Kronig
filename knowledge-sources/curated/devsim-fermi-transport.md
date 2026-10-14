# Reviewed one-dimensional Fermi transport in DEVSIM

Agent Kronig enables `model.fermi` only with coupled Poisson, electron-continuity, and hole-continuity equations. It is mutually exclusive with `model.boltzmann`. The implementation is simulator-specific and remains inside the DEVSIM adapter.

The charge model uses an adapter-owned matched Joyce-Dixon/Sommerfeld approximation with silicon conduction- and valence-band effective densities of states. It corrects inconsistent constants, branch continuity and high-branch derivatives in the pinned native primitives. Forward and inverse statistics share the same law. Independent normalized order-half integral benchmarks bound the sampled density error below 0.22 percent and derivative error below 0.62 percent over the tested arguments; this is an explicitly identified approximation, not exact integral quadrature. Ohmic targets solve the local Fermi neutrality equation rather than using Boltzmann targets. Adaptive starting-state continuation ends only at full Fermi statistics. Metal contacts use the order-one thermionic supply in `devsim-schottky-transport.md`, not ohmic targets.

Carrier current is reconstructed on each one-dimensional edge from the quasi-Fermi gradient:

`J_n = q mu_n n_edge grad(E_Fn)`

`J_p = q mu_p p_edge grad(E_Fp)`

The arithmetic edge carrier density and all analytical derivatives are included in the Newton system. This is an explicit finite-volume discretization and is not described as DEVSIM's Scharfetter-Gummel formulation.

A single `fermi_level` represents equilibrium, not the midpoint of two nonequilibrium quasi-Fermi levels. If conducting contacts drive different electrochemical potentials, request `electron_quasi_fermi_level` and `hole_quasi_fermi_level`. Do not add a single Fermi-level output to a biased transport study. A stationary electrostatic gate with one common carrier reservoir can still have an equilibrium semiconductor Fermi level; dielectric gate voltage alone does not establish a split. The product guard compares conducting boundary voltages and the study semantics, not device names. A confirmed incompatible request must be explained to the researcher, never silently reinterpreted.

Verified boundaries for this implementation are:

- nondegenerate equilibrium agrees with the reviewed Boltzmann implementation within 3 percent for potential and carrier-density fields;
- a symmetric silicon junction doped to 5e19 cm^-3 is neutral at both ohmic endpoints within 0.2 percent of the dopant charge scale;
- its zero-bias terminal current is below 1e-3 A/m2, equivalent to 1e-7 A/cm2;
- biased transport conserves terminal current within 0.5 percent.

These tests do not claim convergence for arbitrary doping, mesh, or bias. The current verified upper benchmark is 5e19 cm^-3 on the repository benchmark mesh. Unsupported or nonconvergent inputs are reported, not replaced with Boltzmann statistics.

The former full-bias numerical boundary has a verified native reference: two 1 um silicon regions, 1e17 cm^-3 doping, two 4.10 eV Schottky contacts, uniform 5 nm mesh, Fermi/Klaassen/SRH/Auger/Slotboom physics, and 1 us electron/hole SRH lifetimes completed -2,0,+2 V in 238 seconds with all 12 applicable canonical validation checks passing. This is a benchmark, not a guarantee for arbitrary devices. The regression now runs in the ordinary integration suite.

DC carrier unknowns are thermal-scaled logarithms of the actual densities. This is a numerical coordinate change, not Boltzmann statistics. It avoids negative-density clipping. Actual native per-node density updates and unchanged potential errors are checked against the original absolute and relative limits, with an unscaled final Newton direction required. For a connected conducting stack with reviewed flux contacts and continuous interfaces, an equivalent integrated continuity row preserves weak source/contact terms otherwise lost when the native extended matrix is exported to a double linear solver. The pivot is selected by matrix strength, not by device name. Other boundaries retain ordinary assembly. Starting-state voltage predictors change only the initial guess, never physical inputs or final equations. Failed solves and validation checks remain failures.

The added metal-contact equilibrium/DC benchmark envelope includes both endpoint orientations, BGN/SRH/Auger equilibrium detailed balance, and explicitly requested 0,+2,-2 V points for the original aluminum/silicon study. Fermi plus Schottky dynamics and prescribed spatial temperature remain unbenchmarked and refused. Fermi current decomposition is supported as the native quasi-Fermi-gradient split into electrostatic drift and thermodynamic diffusion including BGN band-gradient correction, with definitions and benchmark limits in `devsim-current-decomposition.md`. For equilibrium with BGN, carrier chemical potentials are continuous across adjacent silicon regions even when carrier densities differ at a local band-edge step.

Pinned primary implementation references:

- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `src/MathEval/Fermi.cc`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `testing/Fermi1.py`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `python_packages/fermi_physics.py`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `python_packages/simple_dd.py`

Product implementation identifiers: `kronig.joyce-dixon.matched.v1` and `kronig.positive-density.conservative-dc.v1`, DEVSIM compiler 0.2.4. Statistical reference: Joyce and Dixon, Applied Physics Letters 31, 354 (1977), DOI `10.1063/1.89697`.
