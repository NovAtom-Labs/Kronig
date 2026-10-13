# DEVSIM 2.9.1 Adapter Guide

Status: machine-curated from the pinned public source and local adapter, awaiting TCAD domain-lead review.

## Version boundary

The installed runtime reports DEVSIM 2.9.1. The local Apache-2.0 source checkout is pinned to commit `43b41ca845184c47e22b72d144db7e7db8509377`. The official documentation snapshot is pinned to the 2.9.0 documentation commit `8fbe81b5719307d654f37d630cf043dc6ae0512e` and is explicitly marked compatible with 2.9.1 because the 2.9.1 release notes describe internal C++ cleanup without a command-interface change. Retrieval for executable guidance should still retain both the source version and documentation version in citations.

## Deterministic compilation

The current adapter compiles ordered one-dimensional silicon and dielectric regions into a line mesh. Researcher lengths normalize to SI and convert to centimeters only inside the adapter. Constant, piecewise, linear, Gaussian, error-function, and tabulated donor or acceptor profiles contribute to signed net doping. Multiple profiles in one region add algebraically. Fixed bulk and interface charge use separate typed inputs.

The adapter emits `input.json` plus a pinned runtime script. Their SHA-256 digests become `input_digest` and `runtime_digest`. Conversation text does not enter either generated file.

## Solver sequence

The runtime constructs the mesh, applies registered material and model parameters, creates electrostatic equations in every region, and creates carrier equations only in compatible semiconductor regions. It solves initial electrostatics before the coupled drift-diffusion system. DC, AC, frequency, transient, temperature, and registered parameter studies each follow a bounded typed schedule.

The native result records simulator version, terminal IDs, convergence state, requested fields, native model names, region and interface identities, model parameter-set identity, and parameter sources. The normalizer converts all supported native centimeter units into canonical SI datasets while retaining node, edge, contact, interface, and operating-point centering.

## Useful pinned-source retrieval areas

- `python_packages/simple_physics.py`: reusable semiconductor equations and contact helpers
- `examples/diode/`: diode-style construction and solve examples
- `testing/test_common.py`: common contact and equation patterns
- `src/commands/`: public command implementation and validation behavior

Search results are evidence for adapter development, not permission to copy arbitrary examples into execution. The deterministic compiler remains the only path to runnable input.

## Reviewed boundary

The adapter is not a general DEVSIM frontend. It supports only the versioned capability manifest and deterministic allowlisted runtime. The reviewed boundary includes coupled one-dimensional Fermi transport with ohmic initialization, statistics-consistent Boltzmann and Fermi equilibrium/DC thermionic Schottky contacts, surface SRH, a single charged trap level, transient pulses, prescribed silicon temperature profiles, and Boltzmann current-component diagnostics. Each has narrower compatibility rules recorded in its dedicated curated note. Philips surface mobility, combined Fermi/Schottky AC, frequency and transient response, distributed traps, tunneling, self-heating, arbitrary PDEs, arbitrary material values, and arbitrary generated DEVSIM source are refused. A new feature must enter through the portable contract, registry, normalizer, validator, and a passing reference benchmark.

## Source basis

- `src/tcad_agent/adapters/devsim/compiler.py`
- `src/tcad_agent/adapters/devsim/runtime.py`
- DEVSIM source commit `43b41ca845184c47e22b72d144db7e7db8509377`
