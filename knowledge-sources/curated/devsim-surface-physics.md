# Reviewed one-dimensional surface physics in DEVSIM

Agent Kronig supports explicit surface Shockley-Read-Hall recombination and one single-level charged interface trap at an adjacent interface with a silicon side. Silicon-dielectric and silicon-silicon interfaces are supported. Requests require coupled electron and hole continuity equations.

The surface recombination rate is evaluated as a sheet rate:

`U_s = (n p - n_i^2) / ((n+n_1)/S_p + (p+p_1)/S_n)`

with `n_1 = n_i exp(E_t/V_t)` and `p_1 = n_i exp(-E_t/V_t)`. The researcher supplies both positive capture velocities. The sheet rate is coupled into both carrier equations through the exact boundary control volume.

For a configured single-level trap, steady occupancy is:

`f_t = (S_n n + S_p p_1) / (S_n(n+n_1) + S_p(p+p_1))`

An acceptor trap contributes `-q N_t f_t`; a donor trap contributes `q N_t(1-f_t)`. Its complete carrier derivatives are included in Poisson coupling. The canonical result exposes sheet recombination rate, occupancy, and total interface charge, including configured fixed charge.

The implementation is verified for equilibrium detailed balance, nonzero recombination under carrier injection, terminal-current conservation, bounded occupancy, trap-charge sign, and silicon-side orientation. It does not infer capture velocities, a trap distribution, tunneling, or frequency dispersion. Provenance identifier: `novatom.surface-physics.2026-09-29.v1`.

Pinned DEVSIM evidence:

- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, `testing/test_common.py`
- DEVSIM commit `43b41ca845184c47e22b72d144db7e7db8509377`, interface `fluxterm` implementation under `src/Equation`
