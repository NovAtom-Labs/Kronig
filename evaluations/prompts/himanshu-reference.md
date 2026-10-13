# Himanshu's original study

The researcher explicitly authorizes using DEVSIM for the local test instead of Sentaurus. The new request changes the bias, not the material parameters below.

Original problem: Simulate an Al / p-Si / n-Si / Al structure at 300 K. The p-Si region has uniform boron doping of 1e17 cm^-3; the n-Si region has uniform phosphorus doping of 1e17 cm^-3. Both aluminum metal contacts have work function 4.10 eV. Original equilibrium contacts were both at 0 V, with no voltage sweep.

Original requested outputs: electrostatic potential, junction built-in potential, electric field, electron and hole concentration, space charge, conduction and valence bands, Fermi-level position, electron and hole current densities, carrier mobility and recombination rates. Use Fermi statistics, mobility, SRH recombination, Auger recombination and band-gap narrowing.

Dimensions and the semiconductor/contact boundary model were not supplied in the original statement. Ask for them rather than assuming them. Under bias, use the electron and hole quasi-Fermi levels rather than claiming a single flat equilibrium Fermi level.
