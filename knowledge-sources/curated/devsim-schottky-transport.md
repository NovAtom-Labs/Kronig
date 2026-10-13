# Reviewed one-dimensional Schottky transport in DEVSIM

Agent Kronig treats a metal work-function contact on silicon as a Schottky boundary, never as an ohmic contact. It requires coupled Poisson, electron-continuity, and hole-continuity equations. Boltzmann and Fermi carrier statistics are available for the benchmarked one-dimensional silicon equilibrium and DC envelope.

The electrostatic boundary fixes the silicon potential from the difference between the intrinsic silicon work function and the researcher-supplied metal work function. Electron and hole boundary currents use thermionic emission with explicit Richardson constants:

`v_n = A_n T^2 / (q N_c)`

`v_p = A_p T^2 / (q N_v)`

`J_n,b = q v_n (n_s - n_eq)`

`J_p,b = q v_p (p_s - p_eq)`

where the reservoirs use the local temperature-scaled DOS and effective gap, including band-gap narrowing when selected. The electrostatic boundary and reservoirs use the same band reference. Electron and hole outward conventional currents have opposite signs; native endpoint assembly contributes opposite signs at the two ends. The defaults are 112 and 32 A/cm2/K2 for electrons and holes. Researchers may override either constant with unit-checked contact inputs.

## Fermi thermionic supply

With Fermi statistics, use `A T^2 [F1(eta_surface)-F1(eta_metal)]`, with endpoint and carrier signs determined by the native continuity-equation assembly. `eta_surface=InvFermi(carrier/DOS)` uses DEVSIM's pinned density primitive. The electron metal reservoir is `(E_Fmetal-E_c)/V_t`; the hole reservoir is `(E_v-E_Fmetal)/V_t`. `E_Fmetal=-contact_bias` in the canonical energy reference. A zero-bias equilibrium has equal surface and metal chemical potentials, so both net fluxes vanish.

Order-one supply is not the order-half density integral. Native expression models evaluate F1 through a bounded dilogarithm series and reflection identity. The 96-term dilogarithm and 112-term logarithm expansions are split into shallow native models; they preserve extended model arithmetic without Python callbacks. Their stated truncation bounds do not imply exact total floating-point arithmetic. The smooth derivative is `F0(eta)=log(1+exp(eta))`; explicit Potential, carrier and circuit derivatives are included. The dilute supply reduces to the Boltzmann thermionic formula rather than substituting statistics near degeneracy.

Bulk and surface recombination must also respect Fermi detailed balance. The stable driving term is `np*(1-exp(-(E_Fn-E_Fp)/V_t))`, evaluated through the native Bernoulli primitive near zero. SRH emission terms include the carrier degeneracy factors. Across same-material regions with BGN band-edge steps, quasi-Fermi energies, not raw carrier densities, are continuous.

## Measured scope and exclusions

Benchmarks cover zero-current and flat-Fermi equilibrium, both metal ends, BGN/SRH/Auger detailed balance, temperature variation at 280 and 340 K, a degenerate metal reservoir, contact passivity under reduced Richardson transmission, and the explicit Al / silicon / silicon / Al 300 K study at 0, +2 and -2 V. These are benchmark fixtures, not product device branches or a guarantee for arbitrary inputs. Convergence and scientific validation remain run-specific.

Fermi plus silicon Schottky AC, frequency and transient response remain gated pending their own reference benchmarks. Prescribed spatial temperature, tunneling, image-force lowering and distributed contact states remain excluded. Do not ask a researcher to replace a supported Fermi/DC metal boundary with ohmic contacts or Boltzmann statistics merely to run it.

Provenance identifiers: `novatom.schottky-thermionic.2026-10-13.v2` for the local-band classical boundary and `novatom.schottky-fermi-supply.2026-10-13.v1` for the Fermi supply. Recombination uses `novatom.recombination-detailed-balance.2026-10-13.v1`.

Pinned DEVSIM API evidence:

- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `src/pythonapi/DevsimDoc.cc`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `src/AutoEquation/ExprContactEquation.cc`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `src/Equation/ContactEquation.cc` and `python_packages/simple_physics.py`
- NIST DLMF section 25.12, Fermi integrals and dilogarithm identities: https://dlmf.nist.gov/25.12
- Public TUM dissertation, generalized recombination discussion section 6.3.2: https://mediatum.ub.tum.de/doc/1237273/1237273.pdf
