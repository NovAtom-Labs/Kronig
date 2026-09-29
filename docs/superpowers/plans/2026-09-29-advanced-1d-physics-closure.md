# Advanced One-Dimensional Physics Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every remaining code-owned one-dimensional DEVSIM target with reviewed equations, canonical outputs, real-simulator benchmarks, and explicit provenance while preserving honest external-evidence gates.

**Architecture:** `ExperimentSpec` remains the simulator-neutral authority. New parameters and observables compile into typed DEVSIM payload fields, while every executable expression remains inside `adapters/devsim`. Capability maturity changes only after analytical, nondegenerate-limit, conservation, polarity, refinement, and pinned-example evidence passes.

**Tech Stack:** Python 3.11+, Pydantic v2, DEVSIM 2.9.1, pytest, FastAPI canonical result APIs, existing desktop Results Workbench.

**Spec:** `docs/testing/devsim-1d-expansion-acceptance.md`

## Global Constraints

- `ExperimentSpec` is the simulator-neutral product contract.
- Product behavior never branches on a named device.
- Simulator syntax remains under `src/tcad_agent/adapters/devsim`.
- Unsupported combinations fail before workspace creation.
- Every reported numeric value comes from canonical result fields.
- Source, version, hash, compiler, simulator, model, solver, and validation provenance is preserved.
- No proprietary Sentaurus material or credential enters the repository.
- Every behavior change starts with a failing test and ends with the complete suite.
- Thermal transport, two-dimensional surface mobility, and unlicensed Sentaurus execution remain outside this one-dimensional local closure.

## Review Focus

- Degenerate and nondegenerate carrier densities must converge to their independently calculated limits without switching silently to Boltzmann statistics.
- Schottky boundaries must produce zero equilibrium current, correct barrier ordering, current polarity under bias, and bounded temperature response without becoming ohmic contacts.
- Interface recombination and trap charge must conserve terminal current and electrostatic charge for silicon on either side of an interface.
- Prescribed spatial temperature must affect every enabled local equation consistently or be refused before compilation.
- Current decomposition must state its discretization and reconcile with the solved total current within a reviewed tolerance.

---

### Task 1: Coupled Fermi-Dirac transport

**Files:**
- Modify: `src/tcad_agent/physics/registry.py`
- Modify: `src/tcad_agent/adapters/devsim/manifest.yaml`
- Create: `src/tcad_agent/adapters/devsim/models/fermi.py`
- Modify: `src/tcad_agent/adapters/devsim/runtime.py`
- Modify: `tests/integration/test_devsim_fermi_statistics.py`

**Interfaces:**
- Consumes: silicon density of states, band energies, native `Fermi`, `InvFermi`, and `dFermidx`, mobility fields, contact doping, solver controls.
- Produces: Fermi charge initialization, carrier continuity, statistics-specific ohmic contacts, quasi-Fermi energies, and model provenance.

- [ ] Replace the visible-gate test with failing nondegenerate-limit, degenerate-neutrality, equilibrium-zero-current, and biased-conservation tests.
- [ ] Implement a reviewed quasi-Fermi-gradient finite-volume current with analytical derivatives and Fermi-neutral ohmic boundary targets.
- [ ] Enable `model.fermi` only for compatible silicon drift diffusion and reject simultaneous Boltzmann selection.
- [ ] Run the real DEVSIM benchmarks and record the exact discretization and pinned sources.

### Task 2: Direct Schottky carrier boundaries

**Files:**
- Modify: `src/tcad_agent/domain/models.py`
- Modify: `src/tcad_agent/adapters/devsim/payload.py`
- Modify: `src/tcad_agent/adapters/devsim/compiler.py`
- Modify: `src/tcad_agent/capabilities/service.py`
- Create: `src/tcad_agent/adapters/devsim/models/schottky.py`
- Modify: `src/tcad_agent/adapters/devsim/runtime.py`
- Modify: `tests/integration/test_devsim_schottky.py`

**Interfaces:**
- Consumes: contact work function, silicon affinity and gap, temperature, Richardson coefficients, sign convention, and adjacent semiconductor state.
- Produces: work-function electrostatics plus electron and hole thermionic flux boundaries that remain distinct from ohmic contacts.

- [ ] Write failing tests for required parameters, zero-current equilibrium, barrier height ordering, forward/reverse polarity, temperature response, and terminal conservation.
- [ ] Add unit-checked thermionic parameters and compiled provenance.
- [ ] Implement work-function potential and Robin carrier-flux boundary equations with derivatives and circuit-current integration.
- [ ] Enable direct silicon metal-work-function contacts only for benchmarked model combinations.

### Task 3: Interface SRH recombination and interface traps

**Files:**
- Modify: `src/tcad_agent/domain/interfaces.py`
- Modify: `src/tcad_agent/adapters/devsim/payload.py`
- Modify: `src/tcad_agent/adapters/devsim/compiler.py`
- Modify: `src/tcad_agent/capabilities/service.py`
- Create: `src/tcad_agent/adapters/devsim/models/interfaces.py`
- Modify: `src/tcad_agent/adapters/devsim/runtime.py`
- Create: `tests/integration/test_devsim_surface_physics.py`

**Interfaces:**
- Consumes: explicit surface velocities, trap density, trap energy, trap type, silicon-side orientation, local carriers, and local thermal voltage.
- Produces: surface SRH flux, trap occupancy, interface charge, continuity coupling, and canonical interface observables.

- [ ] Write failing contract, material-compatibility, zero-rate, nonzero-bias, charge-sign, conservation, and refinement tests.
- [ ] Add typed surface-recombination and single-level interface-trap contracts with unit validation.
- [ ] Implement silicon-side interface models with complete carrier and electrostatic derivatives.
- [ ] Expose surface rate, occupancy, and total interface charge through canonical datasets and validators.

### Task 4: Prescribed spatial temperature

**Files:**
- Modify: `src/tcad_agent/domain/profiles.py`
- Modify: `src/tcad_agent/domain/models.py`
- Modify: `src/tcad_agent/adapters/devsim/payload.py`
- Modify: `src/tcad_agent/adapters/devsim/compiler.py`
- Create: `src/tcad_agent/adapters/devsim/models/temperature.py`
- Modify: `src/tcad_agent/adapters/devsim/runtime.py`
- Create: `tests/integration/test_devsim_temperature_profile.py`

**Interfaces:**
- Consumes: explicit positive Kelvin profiles and model compatibility metadata.
- Produces: local thermal voltage, gap, density of states, intrinsic density, mobility, recombination, statistics, and contact values without solving heat flow.

- [ ] Write failing validation and constant-profile equivalence tests.
- [ ] Add typed constant, linear, piecewise, and tabulated prescribed-temperature profiles.
- [ ] Replace constant-temperature assumptions in every enabled compatible equation with registered node and edge temperature models.
- [ ] Reject AC, transient, Schottky, or other combinations until their local-temperature boundary terms pass independent benchmarks.

### Task 5: Drift and diffusion current decomposition

**Files:**
- Modify: `src/tcad_agent/domain/models.py`
- Modify: `src/tcad_agent/adapters/devsim/manifest.yaml`
- Modify: `src/tcad_agent/adapters/devsim/runtime.py`
- Modify: `src/tcad_agent/adapters/devsim/compiler.py`
- Create: `tests/integration/test_devsim_current_decomposition.py`

**Interfaces:**
- Consumes: solved potential, carriers, mobility, local thermal voltage, and exact edge geometry.
- Produces: explicitly labeled continuum finite-volume drift and diffusion reconstructions plus a reconciliation residual, never a claim that the split is native Scharfetter-Gummel state.

- [ ] Write failing uniform-density, zero-field, polarity, and reconstruction-residual tests.
- [ ] Implement edge-centered electron and hole drift and diffusion reconstructions with explicit metadata.
- [ ] Add canonical observables and a deterministic reconciliation validator.

### Task 6: Pinned official parity and external conformance harness

**Files:**
- Modify: `tests/integration/test_devsim_reference_benchmarks.py`
- Create: `tests/fixtures/devsim/official-reference-invariants.json`
- Modify: `.github/workflows/native-build.yml`
- Modify: `docs/testing/devsim-1d-expansion-acceptance.md`

**Interfaces:**
- Consumes: pinned DEVSIM source checkout, canonical adapter runs, supported CI operating systems, and optional licensed Sentaurus result bundles.
- Produces: diode, small-signal, and oxide-interface invariant comparisons plus reproducible cross-platform and cross-backend comparison commands.

- [ ] Add failing parity tests that execute pinned official examples and compare independently parsed numeric invariants.
- [ ] Add deterministic platform artifact generation and comparison without weakening missing-evidence status.
- [ ] Add a licensed-host conformance command that consumes canonical Sentaurus bundles without bundling documentation or credentials.
- [ ] Run every locally available parity and platform check.

### Task 7: End-to-end scientific closure

**Files:**
- Modify: `src/tcad_agent/capabilities/descriptors.py`
- Modify: knowledge corpus entries under `knowledge-sources/curated/`
- Modify: `README.md`
- Modify: `docs/testing/devsim-1d-expansion-acceptance.md`
- Test: researcher-like preparation, execution, validation, and Results Workbench suites.

**Interfaces:**
- Consumes: every newly reviewed capability and its evidence.
- Produces: prompt preprocessing questions, execution, canonical bundles, validation, graph discovery, and honest readiness status.

- [ ] Add natural researcher prompts covering each new capability and consequential missing input.
- [ ] Verify capability-driven questions and refusal paths contain no named-device branches.
- [ ] Run bounded live Bedrock workflows only when the configured credential is available.
- [ ] Run Ruff, strict mypy, the complete Python suite, desktop tests, dependency sync, credential scans, named-device scans, and patch hygiene before the final commit.
