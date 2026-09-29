# Transport, Mobility, and Recombination Guidance

Status: source-grounded internal guidance awaiting TCAD domain-lead review.

## Drift-diffusion transport

Classical drift-diffusion couples Poisson's equation to electron and hole continuity equations. Carrier current contains drift and diffusion contributions. Equivalent formulations may use carrier density gradients, quasi-Fermi potentials, or electrochemical potentials. Sign conventions and edge orientation differ across implementations, so validation should use terminal conservation and physical limits rather than comparing raw expression text.

The Scharfetter-Gummel discretization integrates a locally approximated drift-diffusion problem across an edge and is widely used because it behaves well when drift dominates diffusion. A simulator's model location, Bernoulli-function convention, and derivative requirements remain version-specific.

## Mobility hierarchy

Constant mobility is useful for a controlled baseline but is rarely a predictive default over broad fields, temperatures, or doping ranges. Mobility can depend on:

- lattice scattering and temperature
- ionized impurity concentration
- carrier-carrier scattering
- electric field or carrier temperature
- surface or interface normal field
- crystal orientation, strain, and material composition

Choose dependencies required by the research regime. Do not combine empirical models without confirming how the backend composes or overrides them. Model coefficients are calibrated data, not universal constants.

For one-dimensional work, distinguish mobility itself from current density. Conductivity approximately follows `q(n mu_n + p mu_p)` in a low-field local picture, but a terminal current arises from the solved spatial transport problem.

## Shockley-Read-Hall recombination

SRH recombination represents trap-assisted capture and emission. A common steady-state form has numerator `np - n_i^2` and a denominator containing electron and hole lifetimes plus trap-level carrier terms. The sign changes between net recombination and generation. Relevant inputs include trap energy, capture parameters or effective lifetimes, temperature dependence, and whether effective intrinsic concentration includes band-gap narrowing.

At equilibrium, a consistent formulation should give zero net recombination. An arbitrary lifetime does not make a model calibrated. Minority-carrier behavior can be highly sensitive to lifetime and surface recombination assumptions.

Primary basis: W. Shockley and W. T. Read, Jr., Phys. Rev. 87, 835 (1952), https://doi.org/10.1103/PhysRev.87.835; R. N. Hall, Phys. Rev. 87, 387 (1952), https://doi.org/10.1103/PhysRev.87.387.

## Auger recombination

Auger recombination transfers recombination energy to another carrier and often matters at high carrier concentration or high injection. Coefficients may depend on temperature, carrier density, and the selected parameterization. Check whether a backend model uses constant coefficients or a more elaborate formulation. Treat published coefficients as empirical and preserve their validity range.

## Band-gap narrowing

Heavy doping can reduce the effective band gap and alter equilibrium carrier concentrations, junction electrostatics, and bipolar transport. A band-gap-narrowing model must be consistent with carrier statistics, density of states, intrinsic concentration, and band-edge reporting. The plotted band gap, effective intrinsic concentration, and carrier relations must not mix incompatible definitions.

Background primary reference: J. W. Slotboom and H. C. de Graaff, Solid-State Electronics 19 (1976), https://doi.org/10.1016/0038-1101(76)90043-5.

## Model-selection validation

For each enabled mechanism record:

1. why the physical regime requires it
2. its parameters and units
3. material, temperature, field, doping, and injection validity range
4. interactions with other models
5. an observable expected to change when it is enabled
6. a limiting case or reference used to validate the implementation

## Agent Kronig DEVSIM 2.9.1 implementation boundary

The reviewed one-dimensional adapter currently exposes constant mobility, DEVSIM's pinned Klaassen bulk mobility implementation, and an optional one-dimensional high-field saturation correction. It exposes SRH, constant-coefficient Auger recombination, and Slotboom band-gap narrowing through explicit model selections. Electron and hole mobility, SRH and Auger components, total recombination, and net carrier generation are extracted separately.

The parameter set identifier, every overridden parameter value, its source label, and its version are copied into the compiled payload and canonical result metadata. These baselines are reproducible simulation parameters, not a claim of universal process calibration. Researchers must supply a reviewed calibrated set when predictive process-specific accuracy is required.

Surface mobility and surface recombination require explicit interface-normal fields or velocities and independent benchmarks. They remain disabled instead of being approximated by bulk models.

## Source basis

- DEVSIM official manual and maintained examples: https://devsim.net/
- D. L. Scharfetter and H. K. Gummel, IEEE Transactions on Electron Devices 16 (1969), https://doi.org/10.1109/T-ED.1969.16566
- D. M. Caughey and R. E. Thomas, Proceedings of the IEEE 55 (1967), https://doi.org/10.1109/PROC.1967.6123
- NIST semiconductor measurement publications for mobility and resistivity context: https://www.nist.gov/publications
