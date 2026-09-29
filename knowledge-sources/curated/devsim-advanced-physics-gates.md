# DEVSIM 2.9.1 advanced-physics evidence gates

This note records why several requested capabilities remain disabled in the one-dimensional adapter. A mathematical primitive or suggestive helper name is not treated as proof of a complete transport model.

## Coupled Fermi-Dirac transport

The pinned DEVSIM source commit is `43b41ca845184c47e22b72d144db7e7db8509377`, corresponding to the supported 2.9.1 runtime. Its symbolic engine exposes `Fermi`, `InvFermi`, and their derivatives. The official `testing/Fermi1.py` verifies those scalar functions and a Fermi intrinsic-density expression. The packaged `python_packages/fermi_physics.py` contains comments describing work still needed, including the relation between Fermi energy and potential. It does not provide carrier equations, contact equations, initialization, or a coupled transport benchmark.

Therefore `fermi` remains a research gate. Enabling it would require reviewed carrier-density and energy relations, generalized current discretization and derivatives, statistics-specific contacts, initialization, nondegenerate-limit tests, charge-neutrality tests, and a degenerate transport benchmark.

Primary sources:

- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/testing/Fermi1.py
- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/python_packages/fermi_physics.py
- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/src/MathEval/Fermi.cc

## Philips surface mobility in a one-dimensional adapter

The pinned `Philips_Surface_Mobility` helper creates two-dimensional element models and consumes interface-normal electric-field models. The official use case constructs those fields from two-dimensional current flow before applying surface mobility. A one-dimensional field normal to a dielectric interface is not a substitute for the lateral transport field and inversion-layer geometry required by that model.

Therefore Philips surface mobility is excluded from this one-dimensional expansion. It belongs in a future two-dimensional transport adapter with an independent benchmark.

Primary sources:

- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/python_packages/Klaassen.py
- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/examples/mobility/gmsh_mos2d_kla.py

## Surface recombination and interface traps

The upstream test helpers demonstrate a low-level interface flux construction, but the pinned package does not provide a reviewed, parameterized semiconductor-dielectric surface-SRH model or an interface-trap occupancy model for this product contract. A complete implementation must define trap energy or distribution, capture parameters, charge-state convention, interface orientation, current signs, derivatives, units, and nonzero-bias benchmarks.

These features remain research gates. Fixed interface charge remains supported because its displacement jump is independently benchmarked.

Primary source:

- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/testing/test_common.py

## Direct metal-semiconductor Schottky transport

The pinned `simple_physics.py` explicitly leaves work-function carrier-boundary treatment for future work. No reviewed thermionic electron and hole boundary, Richardson parameter registry, image-force policy, or Schottky benchmark is supplied by the pinned package.

Direct metal-semiconductor work-function contacts therefore remain blocked. Metal work function is supported only for electrostatic dielectric gate contacts. It is never converted to an ohmic semiconductor boundary.

Primary source:

- https://github.com/devsim/devsim/blob/43b41ca845184c47e22b72d144db7e7db8509377/python_packages/simple_physics.py

## Spatial temperature profiles

The reviewed runtime uses a scalar lattice temperature to construct material parameters, carrier statistics, recombination, mobility, contacts, and initialization consistently. A position-dependent prescribed temperature would require those quantities to become compatible node and edge models. Solving temperature would additionally require thermal transport, which is explicitly outside this expansion.

Spatial temperature profiles remain a research gate. Scalar temperature and isolated temperature studies remain supported and benchmarked.
