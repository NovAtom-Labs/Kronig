# Reviewed current decomposition diagnostic

Agent Kronig can expose edge-centered drift and diffusion diagnostics for one-dimensional Boltzmann drift-diffusion results. They are computed from the solved electric field, carrier densities, mobility, thermal voltage, and exact edge length:

- `J_n,drift = q mu_n n_edge E`
- `J_n,diffusion = q mu_n V_t grad(n)`
- `J_p,drift = q mu_p p_edge E`
- `J_p,diffusion = -q mu_p V_t grad(p)`

The carrier average is arithmetic at the edge. The canonical `current_decomposition_residual` is the native solved Scharfetter-Gummel total current minus the four continuum diagnostic components. It is intentionally preserved rather than forced to zero. In depletion regions, large drift and diffusion components cancel, so the reviewed reconciliation tolerance is relative to the largest component magnitude, not the much smaller net current.

This output is benchmarked for uniform equilibrium, biased polarity, and refined-mesh reconciliation below 0.5 percent of the component scale. It is currently refused with Fermi statistics because the generalized Einstein relation needs a separate decomposition. Provenance is carried in the dataset metadata as `continuum edge-centered diagnostic`.
