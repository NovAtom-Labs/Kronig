# Exhaustive Simulator-Neutral 1D DEVSIM Expansion

## Objective

Expand Agent Kronig from a narrow silicon drift-diffusion demonstration into a broad, reviewed, one-dimensional scientific simulation backend. The implementation must express structures as materials, regions, interfaces, profiles, contacts, equations, models, studies, observables, and validation policies. Product behavior must never branch on a named device.

The DEVSIM backend is the first complete implementation of these portable contracts. Sentaurus will later consume the same experiment, capability, result, validation, and visualization contracts through its own adapter.

## Binding principles

- `ExperimentSpec` remains the simulator-neutral product contract.
- Device names are permitted only in examples, evaluation prompts, and researcher-authored metadata.
- Simulator commands and expressions remain inside `adapters/devsim`.
- Model-generated simulator source and arbitrary researcher-supplied equations are forbidden.
- Unsupported or unreviewed physics is refused rather than approximated.
- Every numeric claim is derived from canonical result values.
- Every model, parameter set, compiler, runtime, result, and validator retains versioned provenance.
- The runtime used for execution is DEVSIM 2.9.1 until a later release is packaged and validated on all supported operating systems.
- Latest DEVSIM source may inform future work, but executable guidance must declare compatibility with the packaged runtime.

## Generic scientific contract

An experiment contains a one-dimensional coordinate system, ordered material regions, region interfaces, spatial parameter profiles, boundary contacts, a physics selection, one or more studies, requested observables, and validation requirements. No `device_type` field exists.

### Geometry and materials

Regions are contiguous intervals with stable identifiers, material identifiers, and optional mesh controls. The reviewed material registry provides silicon, silicon dioxide, and generic linear dielectrics with explicit parameters and source records. Unknown materials are rejected. A generic dielectric requires researcher-supplied or reviewed permittivity and never inherits silicon parameters.

Interfaces connect adjacent regions. Supported interface laws include continuous electrostatic potential, continuous dielectric displacement, semiconductor carrier continuity, fixed interface charge, and reviewed surface recombination. Compatibility is determined from material classes and requested equations rather than device identity.

### Spatial profiles

Profiles are typed data. The contract supports constant, linear, Gaussian, error-function, and tabulated profiles. Each profile declares its region, species or parameter, dimensional value, spatial bounds, and interpolation policy where relevant. Profiles may be superposed. The compiler constructs allowlisted expressions from these values; prompts never provide executable expressions.

### Contacts

Contacts support ohmic, applied-potential, metal-work-function, electrostatic gate, and insulating behavior where the selected material and equation set has a reviewed mapping. Contact area is optional. Without area, terminal current, charge, capacitance, and conductance remain normalized per unit area. Sign convention and driven-contact identity are explicit.

### Physics registry

Each model descriptor declares its identifier, maturity, equations, material classes, dependencies, conflicts, required parameters, available observables, required validators, implementation version, compatible DEVSIM versions, and evidence sources.

The targeted reviewed library includes Poisson electrostatics, semiconductor drift diffusion, dielectric electrostatics, Boltzmann and Fermi statistics, constant and Klaassen mobility, temperature dependence, high-field saturation, Philips-style surface mobility, SRH and Auger recombination, band-gap narrowing, fixed and interface charge, band energies, quasi-Fermi energies, and current decomposition. A capability remains disabled until its equations, derivatives, units, parameters, convergence behavior, and reference benchmarks pass.

### Studies

Studies are typed and composable. The supported set includes equilibrium, one fixed operating point, exact DC points, uniform DC range, adaptive forward or reverse DC continuation, bidirectional DC sweeps, temperature sweeps, registered parameter sweeps, quasi-static charge-voltage sweeps, small-signal AC, frequency sweeps, and bounded transient step, ramp, or pulse studies.

Study limits come from the backend resource policy. There is no arbitrary ten-point product limit. Failed points remain evidence and cannot be reported as converged.

## Capability registry and preprocessing

The flat manifest is replaced by typed descriptors for materials, profiles, interfaces, contacts, equations, models, studies, observables, limits, and execution state. Descriptors identify required researcher inputs separately from expert-selectable implementation details and safe platform defaults.

Prompt preprocessing receives a bounded public capability view, not merely manifest hashes. It extracts the stated intent, matches requested outcomes to capabilities, identifies unresolved researcher-owned fields, and produces a small clarification batch. Complete prompts proceed without ceremonial questions. Ambiguous dimensions, missing bias definitions, unspecified capacitance method, absent AC frequency, and absolute capacitance without area produce consequential questions. Adding a registry entry automatically extends preparation without prompt-specific code.

## Deterministic DEVSIM adapter

The compiler converts `ExperimentSpec` into a canonical, non-executable payload. The payload contains only normalized values and registry identifiers. It includes material parameters, mesh anchors, region definitions, interface laws, profile coefficients, contact data, model selections, study schedules, requested observables, budgets, and provenance digests.

The packaged runtime owns all DEVSIM API calls and allowlisted equations. Runtime modules are split by mesh, materials, profiles, contacts, electrostatics, transport, statistics, mobility, recombination, bands, studies, extraction, and serialization. The compiler digest covers every implementation module and registry entry.

Adaptive execution begins with electrostatics, initializes carriers, couples drift diffusion, and continues from the last converged point. Bias failure reduces the step within configured limits. Bounded recovery attempts and all failures are recorded. AC and transient execution use explicit budgets.

## Canonical scientific datasets

The existing single field map and current-only bias points are retained for backward reading but superseded by generic datasets. A dataset has a stable name, quantity, unit, ordered dimensions, coordinate axes, values, centering, terminal or region association, and provenance.

Supported axis kinds include position, bias, time, frequency, temperature, and registered parameter. Dataset ranks provide:

- Scalar metrics.
- Terminal values at operating points.
- One-dimensional spatial fields.
- Generic response curves.
- Bias-indexed spatial fields.
- Frequency-domain complex responses.
- Time-domain responses.
- Parameter sweeps.

Fields preserve node or edge centering and their true coordinates. Failed operating points are represented explicitly. Terminal electron current, hole current, total current, charge, capacitance, conductance, and complex admittance are first-class canonical quantities.

Derived metrics are registered by required inputs. They include extrema, locations, differences, gradients, integrals, averages, built-in potential, peak field, current balance, charge balance, quasi-static capacitance, AC capacitance, conductance, and resistance where meaningful. Derivers never inspect device names.

## Results Workbench

The workbench discovers plots from dataset dimensionality, axes, units, and metadata.

- A scalar becomes a metric.
- One independent axis becomes a line plot.
- Position plus a sweep axis becomes a selectable profile family and optional heatmap.
- Complex data offers real, imaginary, magnitude, and phase views.
- Compatible units can be overlaid; incompatible units remain separate.

The interface provides dataset search, axis and operating-point selectors, terminal and region filters, linear, logarithmic, and signed-log scales, zoom, pan, crosshair inspection, nearest-sample tooltips, material-region and interface markers, run overlays, CSV export, and SVG or PNG plot export. Non-finite points and failed solves remain visible as gaps and warnings. The evidence view always exposes the canonical source.

## Validation

Validation is layered and deterministic:

- Contract, unit, material, model, and compatibility checks.
- Mesh order, spacing, density, and refinement checks.
- Finite-value, shape, coordinate, and dataset-centering checks.
- Expected operating-point count and ordering.
- Convergence and bounded-recovery checks.
- Terminal-current and terminal-charge conservation.
- Equilibrium-current checks.
- Electric field against negative potential gradient.
- Poisson and charge consistency.
- Carrier positivity and finite bounds.
- Band ordering and carrier-band consistency.
- Recombination sign and unit checks.
- Capacitance derivative stability.
- AC and charge-derived capacitance comparison when both are present.
- Mesh and step refinement convergence.
- Mandatory observable presence.
- Artifact and provenance integrity.

Tolerances originate from reviewed policy, analytic scale-aware rules, or explicit researcher input. The language model cannot invent acceptance limits.

## Knowledge and evidence

The packaged corpus indexes the exact DEVSIM 2.9.1 API and reviewed official examples for capacitance, small-signal AC, oxide interfaces, MOS electrostatics, adaptive ramping, Fermi functions, and mobility. Portable guides describe every implemented equation, derivative, parameter set, applicability range, and validator. Latest-release sources are labeled separately from executable-runtime guidance.

Every capability descriptor references evidence identifiers and content hashes. Proprietary Sentaurus material is excluded.

## Evaluation strategy

Synthetic cases use natural researcher language and cover complete, incomplete, ambiguous, contradictory, unsupported, and unfamiliar-named structures. Scoring checks resolved portable concepts rather than prompt keywords or device names.

Reference benchmarks include abrupt-junction equilibrium, depletion and built-in potential, uniform resistance, parallel-plate capacitance, charge neutrality, official DEVSIM diode, capacitance, AC, oxide-interface and mobility examples, mesh refinement, bias-step refinement, and cross-platform reproducibility.

Opt-in live Bedrock evaluations use the real preprocessing service, clarification API, compiled request, OpenHands runtime, approval broker, DEVSIM execution, canonical reader, validators, and Results Workbench. They verify that no missing values are invented, every supported requested result is present and graphable, unsupported physics is refused, and credentials never enter events or artifacts.

## Delivery order

1. Typed capability and material/model registry plus preprocessing projection.
2. Expanded portable contract for profiles, interfaces, contacts and studies.
3. Generic canonical dataset contract with backward reading.
4. Modular deterministic DEVSIM compiler and runtime.
5. Adaptive DC, charge, AC, transient and parameter execution.
6. Expanded deterministic validation and derivation.
7. Dataset-driven interactive Results Workbench.
8. Reviewed knowledge, synthetic benchmarks and live API workflows.
9. Cross-platform, packaging, provenance and documentation verification.

## Explicit boundary

This expansion excludes two-dimensional and three-dimensional geometry, process simulation, optical, thermal and mechanical coupling, hydrodynamic and ballistic transport, general quantum transport, arbitrary researcher equations, model-generated DEVSIM source, unreviewed material parameters, and claims of Sentaurus equivalence without cross-backend evidence.

