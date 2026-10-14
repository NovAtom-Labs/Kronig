# Reviewed current decomposition diagnostic

Agent Kronig exposes edge-centered drift and diffusion diagnostics for one-dimensional Boltzmann and Fermi drift-diffusion results. The requested statistics and contact boundary models are retained. The decomposition follows the adapter's solved current formulation; the two discretizations have different residual meanings.

## Boltzmann continuum diagnostic

The Boltzmann components are computed from the solved electric field, carrier densities, mobility, thermal voltage, and exact edge length:

- `J_n,drift = q mu_n n_edge E`
- `J_n,diffusion = q mu_n V_t grad(n)`
- `J_p,drift = q mu_p p_edge E`
- `J_p,diffusion = -q mu_p V_t grad(p)`

The carrier average is arithmetic at the edge. The canonical `current_decomposition_residual` is the native solved Scharfetter-Gummel total current minus the four continuum diagnostic components. It is intentionally preserved rather than forced to zero. In depletion regions, large drift and diffusion components cancel, so the reviewed reconciliation tolerance is relative to the largest component magnitude, not the much smaller net current.

This output is benchmarked for uniform equilibrium, biased polarity, and refined-mesh reconciliation below 0.5 percent of the component scale. Provenance is carried in the dataset metadata as `continuum edge-centered diagnostic`.

## Fermi thermodynamic diagnostic

Fermi currents use the same finite edge difference of the quasi-Fermi energies as the native continuity equations. In each isothermal silicon region, let `delta` be the endpoint difference, `n_bar` and `p_bar` the arithmetic edge densities, and `eta_n = InvFermi(n/Nc)`, `eta_p = InvFermi(p/Nv)`. The elementary charge is positive, energies are numerically in eV, and `E = -delta(Potential)/dx`:

- `J_n,drift = q mu_n n_bar E`
- `J_n,density-diffusion = q mu_n n_bar Vt delta(eta_n)/dx`
- `J_n,band-gradient = -q mu_n n_bar delta(BGN)/(2 dx)`
- `J_p,drift = q mu_p p_bar E`
- `J_p,density-diffusion = -q mu_p p_bar Vt delta(eta_p)/dx`
- `J_p,band-gradient = +q mu_p p_bar delta(BGN)/(2 dx)`

The existing canonical `electron_diffusion_current_density` and `hole_diffusion_current_density` fields contain thermodynamic diffusion: the sum of their density-diffusion and band-gradient contributions. Their display labels and metadata explicitly say that the BGN band-gradient correction is included. The two terms are independently named inside the adapter, so an isolated band shift is not mislabeled as a density gradient. Drift contains the electrostatic field only.

In the differential limit the density term uses the generalized Einstein relation `D/mu = Vt (n/Nc) d InvFermi(n/Nc)/d(n/Nc)` (and the corresponding hole relation). A Boltzmann `D/mu = Vt` substitution is not used. Here `InvFermi` denotes the adapter-owned matched Joyce-Dixon/Sommerfeld approximation used by the solved transport model, not the inconsistent native primitive or exact integral quadrature.

`current_decomposition_residual` is evaluated from the native solved carrier currents minus the four reported components, never inserted as a zero constant. For the Fermi quasi-Fermi-gradient discretization the split is algebraically consistent at finite edge length, so a residual near roundoff is expected. This is a component algebraic reconciliation residual, not a continuity/divergence residual: it does not compare `div(J)` to generation or recombination, and does not independently establish current conservation, transport accuracy, or mesh convergence. Large equilibrium components can cancel while terminal current vanishes. Selecting Fermi statistics does not by itself guarantee improved physical accuracy over Boltzmann statistics; the pinned statistical primitive and the carrier regime must be considered.

Independent manufactured-field benchmarks check isolated electric field, density gradients, both carrier signs, isolated BGN gradients, and equilibrium cancellation. Dilute density gradients agree with direct normalized F1/2 quadrature within 0.5 percent for `eta = -12,-10,-8`. Degenerate finite-edge values and a small-gradient generalized Einstein coefficient use independently evaluated matched-approximation references. The degenerate gradient also must agree with the exact-integral chemical-potential-gradient reference within 0.3 percent.

The old native implementation used `3 pi/4` rather than `3 sqrt(pi)/4` in its high-density inverse and produced about 45.5 percent excess in this gradient reference. Compiler 0.2.4 corrects that coefficient, the dilute Joyce coefficient, the joining value and the high-branch derivative. The matched inverse at independently integrated populations for `eta = 8,9,10` gives `7.9883157634,8.9876667167,9.9872680649`. Independent integral tests show sampled forward-density error below 0.22 percent and derivative error below 0.62 percent. Initialization, recombination, contacts, transport and these diagnostics share the corrected statistical law. This removes the demonstrated native defect without claiming exact quadrature or guaranteed transport accuracy in arbitrary regimes.

The original aluminum/silicon Fermi Schottky structure with BGN/SRH/Auger executes `0,+2,-2 V`, exports canonical `A/m^2` edge datasets with bias axes, preserves zero-bias cancellation and terminal current conservation, and passes canonical validation. Terminal current conservation is checked independently from terminal currents; the edge reconciliation residual is not called a current-conservation test.

Fermi decomposition is available for equilibrium, DC, explicit DC points, and static temperature/parameter studies within the supported transport envelope. Fermi decomposition requested with AC, frequency, or transient studies is refused as an unbenchmarked diagnostic combination; this does not refuse otherwise supported Fermi dynamics without these diagnostic outputs. Fermi prescribed spatial temperature and Fermi plus Schottky dynamic studies also remain outside the reviewed envelope. Edge diagnostics apply within regions; abrupt region-interface band offsets are governed by the interface equations and are not represented as a fictitious bulk edge across the interface. Dataset provenance records `native quasi-Fermi-gradient edge diagnostic`, the statistics primitive, and `novatom.fermi-current-decomposition.2026-10-14.v1`; compiler, simulator, source hashes, and validation provenance remain in the result bundle.
