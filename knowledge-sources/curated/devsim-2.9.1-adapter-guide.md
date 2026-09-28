# DEVSIM 2.9.1 Adapter Guide

Status: machine-curated from the pinned public source and local adapter, awaiting TCAD domain-lead review.

## Version boundary

The installed runtime reports DEVSIM 2.9.1. The local Apache-2.0 source checkout is pinned to commit `43b41ca845184c47e22b72d144db7e7db8509377`. The official documentation snapshot is pinned to the 2.9.0 documentation commit `8fbe81b5719307d654f37d630cf043dc6ae0512e` and is explicitly marked compatible with 2.9.1 because the 2.9.1 release notes describe internal C++ cleanup without a command-interface change. Retrieval for executable guidance should still retain both the source version and documentation version in citations.

## Deterministic compilation

The current adapter compiles one-dimensional silicon regions into a line mesh. Researcher lengths normalize to SI and convert to centimeters only inside the adapter. Constant donor values contribute positive signed net doping, while constant acceptor values contribute negative signed net doping. Multiple profiles in one region add algebraically.

The adapter emits `input.json` plus a pinned runtime script. Their SHA-256 digests become `input_digest` and `runtime_digest`. Conversation text does not enter either generated file.

## Solver sequence

The runtime constructs the mesh and silicon device, applies material and mobility parameters, creates potential and carrier models, creates contact equations, solves initial electrostatics, then solves coupled drift-diffusion. A DC study advances through the exact compiled bias list.

The native result records simulator version, terminal IDs, convergence state, terminal current density in amperes per square centimeter, and requested field data. The normalizer converts current density to amperes per square meter, coordinates to meters, and carrier density to inverse cubic meters.

## Useful pinned-source retrieval areas

- `python_packages/simple_physics.py`: reusable semiconductor equations and contact helpers
- `examples/diode/`: diode-style construction and solve examples
- `testing/test_common.py`: common contact and equation patterns
- `src/commands/`: public command implementation and validation behavior

Search results are evidence for adapter development, not permission to copy arbitrary examples into execution. The deterministic compiler remains the only path to runnable input.

## Known foundation limits

The current adapter is not a general DEVSIM frontend. It supports the published manifest only: one dimension, silicon, constant profiles, ohmic end contacts, equilibrium or short DC sweeps, and the listed drift-diffusion models and observables. Unsupported DEVSIM features must be added through the portable contract and tests, not injected as raw Python.

## Source basis

- `src/tcad_agent/adapters/devsim/compiler.py`
- `src/tcad_agent/adapters/devsim/runtime.py`
- DEVSIM source commit `43b41ca845184c47e22b72d144db7e7db8509377`
