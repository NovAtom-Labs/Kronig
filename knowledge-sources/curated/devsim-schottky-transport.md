# Reviewed one-dimensional Schottky transport in DEVSIM

Agent Kronig treats a metal work-function contact on silicon as a Schottky boundary, never as an ohmic contact. It requires coupled Poisson, electron-continuity, and hole-continuity equations and is currently benchmarked only with Boltzmann carrier statistics.

The electrostatic boundary fixes the silicon potential from the difference between the intrinsic silicon work function and the researcher-supplied metal work function. Electron and hole boundary currents use thermionic emission with explicit Richardson constants:

`v_n = A_n T^2 / (q N_c)`

`v_p = A_p T^2 / (q N_v)`

`J_n,b = q v_n (n_s - n_eq)`

`J_p,b = q v_p (p_s - p_eq)`

where `n_eq = N_c exp(-(Phi_m-chi)/V_t)` and `p_eq = N_v exp(-(chi+E_g-Phi_m)/V_t)`. The defaults are 112 and 32 A/cm2/K2 for electrons and holes. Researchers may override either constant with unit-checked contact inputs. Image-force lowering, tunneling, interface states, and Fermi-statistics Schottky injection are not silently added.

The implementation is verified for zero-current equilibrium, metal-work-function barrier ordering, opposite current polarity under opposite applied bias, terminal-current conservation, and temperature response. Provenance identifier: `novatom.schottky-thermionic.2026-09-29.v1`.

Pinned DEVSIM API evidence:

- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `src/pythonapi/DevsimDoc.cc`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `src/AutoEquation/ExprContactEquation.cc`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `python_packages/simple_dd.py`
