# Exhaustive Simulator-Neutral 1D DEVSIM Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a broad, device-independent one-dimensional DEVSIM backend with typed capabilities, adaptive studies, generic canonical datasets, deterministic validation, automatic prompt clarification, and interactive scientific plotting.

**Architecture:** `ExperimentSpec` expresses portable scientific primitives. Typed registries authorize reviewed models and feed both preprocessing and deterministic adapter compilation. DEVSIM normalizes every output into axis-aware canonical datasets that drive validation, derivation, and visualization without device-name branches.

**Tech Stack:** Python 3.13, Pydantic, Pint, DEVSIM 2.9.1, FastAPI, vanilla JavaScript and SVG, OpenHands SDK, Bedrock, pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-09-29-devsim-1d-expansion-design.md`

## Global Constraints

- `ExperimentSpec` is the simulator-neutral product contract.
- Never branch behavior on a named device.
- All DEVSIM syntax stays under `src/tcad_agent/adapters/devsim`.
- Unsupported and unreviewed physics is refused.
- Numeric reports derive only from canonical results.
- Preserve source, version, hash, compiler, runtime, simulator and validation provenance.
- Execute with packaged DEVSIM 2.9.1 until a later release passes packaging and scientific conformance.
- No proprietary Sentaurus documentation or credentials enter the repository.
- Every behavior change follows RED, GREEN, REFACTOR and the complete suite runs before completion.

## Review Focus

- Ambiguous units and missing researcher-owned quantities must cause clarification, not inferred values.
- Axis-aware datasets must preserve edge versus node centering and reject shape mismatches.
- Mixed semiconductor and dielectric stacks must not apply carrier equations inside dielectrics.
- Failed adaptive sweep points must remain visible and must not be labeled converged.
- Registry capability claims must have an implementation, extraction path, validator and evidence reference.

---

### Task 1: Typed capability, material and model registries

**Files:**
- Create: `src/tcad_agent/capabilities/descriptors.py`
- Create: `src/tcad_agent/physics/registry.py`
- Create: `src/tcad_agent/physics/materials.py`
- Modify: `src/tcad_agent/capabilities/models.py`
- Modify: `src/tcad_agent/capabilities/service.py`
- Modify: `src/tcad_agent/prompting/context.py`
- Modify: `src/tcad_agent/prompting/models.py`
- Modify: `src/tcad_agent/prompting/gateway.py`
- Test: `tests/unit/capabilities/test_descriptors.py`
- Test: `tests/unit/prompting/test_capability_context.py`

**Interfaces:**
- Produces: `CapabilityCatalog.public_view()`, `MaterialRegistry`, `PhysicsRegistry`, maturity and evidence-gated descriptors.
- Consumes: existing backend manifest identity and prompt preparation context.

- [ ] Write failing tests for typed descriptors, dependency/conflict validation, evidence requirements, public prompt projection and automatic missing-input questions.
- [ ] Run focused tests and confirm failures arise from missing types and public projection.
- [ ] Implement immutable registries and backward-compatible manifest loading.
- [ ] Pass a bounded structured catalog into prompt preparation and enforce researcher versus expert authority.
- [ ] Run capability and prompting suites, then commit.

### Task 2: Portable 1D profiles, interfaces, contacts and studies

**Files:**
- Modify: `src/tcad_agent/domain/models.py`
- Create: `src/tcad_agent/domain/profiles.py`
- Create: `src/tcad_agent/domain/interfaces.py`
- Create: `src/tcad_agent/domain/studies.py`
- Modify: `src/tcad_agent/domain/units.py`
- Test: `tests/unit/domain/test_profiles.py`
- Test: `tests/unit/domain/test_interfaces.py`
- Test: `tests/unit/domain/test_studies.py`
- Test: `tests/unit/domain/test_experiment_composition.py`

**Interfaces:**
- Consumes: registries from Task 1.
- Produces: discriminated profile, interface and study unions accepted by `ExperimentSpec`.

- [ ] Write failing tests for constant, linear, Gaussian, error-function and tabulated profiles.
- [ ] Implement typed profiles with dimensional and bounds validation.
- [ ] Write failing tests for adjacent interfaces, fixed charge and incompatible compositions.
- [ ] Implement interface contracts and composition validation.
- [ ] Write failing tests for exact, adaptive, bidirectional, AC, frequency, transient, temperature and parameter studies.
- [ ] Implement study contracts and resource-bound point expansion.
- [ ] Preserve loading of existing version 1.0 fixtures, run domain tests, then commit.

### Task 3: Axis-aware canonical scientific datasets

**Files:**
- Modify: `src/tcad_agent/results/models.py`
- Create: `src/tcad_agent/results/datasets.py`
- Create: `src/tcad_agent/results/derive.py`
- Modify: `src/tcad_agent/bundles/writer.py`
- Modify: `src/tcad_agent/bundles/reader.py`
- Test: `tests/unit/results/test_datasets.py`
- Test: `tests/unit/results/test_derive.py`
- Test: `tests/integration/test_bundle.py`

**Interfaces:**
- Consumes: study and observable contracts from Task 2.
- Produces: axes, real and complex datasets, operating-point records, derivation registry and backward-compatible canonical results.

- [ ] Write failing tests for scalar, curve, position, bias-position, frequency-complex and time datasets, including shape and centering failures.
- [ ] Implement immutable axis and dataset contracts with unit and shape checks.
- [ ] Write failing tests for extrema, gradients, integrals, built-in potential, peak field, current balance and capacitance derivation.
- [ ] Implement generic input-declared derivation without device names.
- [ ] Extend atomic bundle serialization and verified reading, run result and bundle suites, then commit.

### Task 4: Modular deterministic DEVSIM compiler and runtime

**Files:**
- Modify: `src/tcad_agent/adapters/devsim/compiler.py`
- Replace: `src/tcad_agent/adapters/devsim/runtime.py`
- Create: `src/tcad_agent/adapters/devsim/payload.py`
- Create: `src/tcad_agent/adapters/devsim/models/mesh.py`
- Create: `src/tcad_agent/adapters/devsim/models/materials.py`
- Create: `src/tcad_agent/adapters/devsim/models/profiles.py`
- Create: `src/tcad_agent/adapters/devsim/models/contacts.py`
- Create: `src/tcad_agent/adapters/devsim/models/electrostatics.py`
- Create: `src/tcad_agent/adapters/devsim/models/transport.py`
- Create: `src/tcad_agent/adapters/devsim/models/statistics.py`
- Create: `src/tcad_agent/adapters/devsim/models/mobility.py`
- Create: `src/tcad_agent/adapters/devsim/models/recombination.py`
- Create: `src/tcad_agent/adapters/devsim/models/bands.py`
- Create: `src/tcad_agent/adapters/devsim/extract.py`
- Test: `tests/unit/adapters/test_devsim_payload.py`
- Test: `tests/unit/adapters/test_devsim_models.py`
- Test: `tests/integration/test_devsim_multimaterial.py`

**Interfaces:**
- Consumes: Tasks 1 through 3 contracts.
- Produces: deterministic non-executable payload, allowlisted model builders and normalized canonical datasets.

- [ ] Write failing payload tests proving no executable expressions or arbitrary paths can enter compilation.
- [ ] Implement deterministic registry identifier and normalized-value payloads.
- [ ] Write failing multi-region tests for semiconductor continuity, dielectric electrostatics, silicon-oxide displacement and fixed interface charge.
- [ ] Implement mesh, material, interface and contact builders.
- [ ] Write failing tests for requested electrostatic, carrier, charge, band, current, mobility and recombination outputs.
- [ ] Implement reviewed model builders and extraction with node or edge centering.
- [ ] Run real DEVSIM equilibrium and mixed-stack integration tests, then commit.

### Task 5: Adaptive DC, charge, AC, frequency and transient execution

**Files:**
- Create: `src/tcad_agent/adapters/devsim/studies.py`
- Modify: `src/tcad_agent/adapters/devsim/runtime.py`
- Modify: `src/tcad_agent/runners/models.py`
- Modify: `src/tcad_agent/runners/local.py`
- Test: `tests/unit/adapters/test_devsim_studies.py`
- Test: `tests/integration/test_devsim_sweeps.py`
- Test: `tests/integration/test_devsim_capacitance.py`

**Interfaces:**
- Consumes: DEVSIM model builders and canonical dataset writer.
- Produces: bounded study executor with per-point state and recovery evidence.

- [ ] Write failing tests for exact points, adaptive step reduction, bidirectional ordering, bounded retry and preserved failed points.
- [ ] Implement continuation and adaptive DC execution.
- [ ] Write failing tests for contact charge, quasi-static capacitance, AC complex response and frequency axes.
- [ ] Implement charge and small-signal AC extraction.
- [ ] Write failing tests for bounded transient schedules and parameter sweeps.
- [ ] Implement supported transient and parameter loops, run real DEVSIM study suites, then commit.

### Task 6: Deterministic validation and reference benchmarks

**Files:**
- Modify: `src/tcad_agent/validation/engine.py`
- Create: `src/tcad_agent/validation/datasets.py`
- Create: `src/tcad_agent/validation/physics.py`
- Create: `src/tcad_agent/validation/convergence.py`
- Modify: `src/tcad_agent/validation/models.py`
- Create: `tests/integration/test_devsim_reference_benchmarks.py`
- Test: `tests/unit/validation/test_dataset_validation.py`
- Test: `tests/unit/validation/test_physics_validation.py`

**Interfaces:**
- Consumes: axis-aware datasets, model registry validators and execution evidence.
- Produces: stable checks with canonical evidence paths and scale-aware reviewed tolerances.

- [ ] Write failing tests for dataset shape, finite values, centering, point ordering and convergence.
- [ ] Implement structural dataset validation.
- [ ] Write failing tests for current, charge, field-gradient, Poisson, carrier, band, recombination and capacitance consistency.
- [ ] Implement physics validators and evidence references.
- [ ] Add analytic and official-example benchmarks plus mesh and bias-step refinement tests.
- [ ] Run full validation and real simulator suites, then commit.

### Task 7: Dataset-driven interactive Results Workbench

**Files:**
- Replace: `src/tcad_agent/web/static/results-workbench.js`
- Modify: `src/tcad_agent/web/static/ide.css`
- Modify: `src/tcad_agent/web/ide_routes.py`
- Create: `src/tcad_agent/web/static/scientific-chart.js`
- Test: `tests/js/results_workbench.test.js`
- Test: `tests/js/scientific_chart.test.js`
- Test: `tests/unit/web/test_ide_api.py`

**Interfaces:**
- Consumes: verified axis-aware result view.
- Produces: automatic metric, curve, profile-family, heatmap and complex-response views.

- [ ] Write failing JavaScript tests for plot discovery from ranks, axes and units without device names.
- [ ] Implement dataset catalog, selectors, compatible overlays and failure gaps.
- [ ] Write failing interaction tests for zoom, pan, crosshair, operating-point selection, log safety, region markers and exports.
- [ ] Implement reusable SVG scientific chart primitives and workbench controls.
- [ ] Add API tests for result migrations and verified evidence, run all UI and API tests, then commit.

### Task 8: Knowledge, natural-language evaluations and live Bedrock workflows

**Files:**
- Modify: `knowledge-sources/manifests/sources.yaml`
- Create: reviewed guides under `knowledge-sources/curated/`
- Modify: `evaluations/scientific/cases.yaml`
- Create: natural prompts under `evaluations/scientific/prompts/`
- Create: `tests/e2e/test_live_expanded_devsim.py`
- Modify: `tests/unit/evaluations/test_scientific_cases.py`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/testing/pilot-acceptance.md`

**Interfaces:**
- Consumes: complete registry, preprocessor, runtime, validators and viewer.
- Produces: reviewed evidence corpus, generic benchmark set and opt-in live acceptance.

- [ ] Add version-separated official evidence records and rebuild the immutable index.
- [ ] Add natural complete, incomplete, ambiguous, contradictory and unsupported cases without schema-tuned prompt language.
- [ ] Add deterministic scorers for portable concepts, requested datasets, validation and provenance.
- [ ] Add opt-in live tests for clarification, biased multilayer fields, charge/C-V and generic unfamiliar names.
- [ ] Run bounded live Bedrock workflows through the product API and real DEVSIM, inspect canonical results through the viewer API.
- [ ] Document supported scope, limitations, installation and evidence, then commit.

### Task 9: Complete verification and branch review

**Files:**
- Modify only files required by verified findings.

**Interfaces:**
- Consumes: all earlier tasks.
- Produces: reviewed, reproducible branch ready for researcher testing.

- [ ] Run Ruff, strict mypy, complete Python, JavaScript and desktop suites.
- [ ] Run dependency synchronization, diff hygiene, credential scan and named-device branch scan.
- [ ] Run real DEVSIM reference cases and opt-in live Bedrock acceptance.
- [ ] Review the complete branch against the spec, repair Critical and Important findings test-first, and rerun everything.
- [ ] Record exact capabilities, test evidence, remaining scientific boundaries and branch state without pushing remotely.

