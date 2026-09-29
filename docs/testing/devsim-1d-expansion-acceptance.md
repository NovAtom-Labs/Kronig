# DEVSIM One-Dimensional Expansion Acceptance Contract

This document is the verification ledger for the approved expansion target. The full researcher-supplied completion list is normative. Every item in that list must finish as Verified, Research gate, Excluded, or Pending evidence in this ledger. A capability is not considered supported merely because DEVSIM exposes a command or function. Support requires a portable contract, deterministic compilation, runtime execution, canonical extraction, validation, provenance, and a passing reference test.

Status meanings:

- **Verified** means the implementation and named automated evidence exist on this branch.
- **Research gate** means the request is detected and refused before compilation because the complete reviewed implementation or benchmark is not available.
- **Excluded** means it is outside the approved one-dimensional scope.
- **Pending evidence** means code may exist, but the target must not be advertised until the listed evidence is complete.

## Target matrix

| Target area | Status | Verified boundary and evidence |
| --- | --- | --- |
| Git and isolation | Verified | Prompt preprocessing is preserved in earlier commits. Expansion work is isolated on `devsim-1d-expansion`. No remote push is performed before researcher approval. |
| Simulator-neutral contract | Verified | `ExperimentSpec` owns regions, profiles, interfaces, contacts, physics, studies, observables, sign convention, and solver controls. Capability checks run before adapter compilation. |
| Generic 1D geometry | Verified | Ordered contiguous region stacks, up to 32 regions, semiconductor and dielectric classes, regional spacing bounds, interface spacing, user anchors, and automatic profile landmarks. Tests: `tests/unit/domain/test_experiment_spec.py`, `tests/unit/adapters/test_devsim_compiler.py`, `tests/integration/test_devsim_multimaterial.py`. |
| Material registry | Verified for silicon, silicon dioxide, and researcher-parameterized generic dielectric | Unknown and incomplete materials are rejected. Parameter-set identity, source labels, versions, and DEVSIM 2.9.1 compatibility are typed and copied into canonical metadata. Tests: `tests/unit/capabilities/test_descriptors.py`, `tests/integration/test_devsim_generic_dielectric.py`, `tests/integration/test_devsim_advanced_physics.py`. |
| Spatial profiles | Verified | Constant, piecewise constant, linear, Gaussian, error-function, tabulated linear or nearest interpolation, additive donor and acceptor profiles, net doping, fixed bulk charge, extent checks, units, and automatic refinement landmarks. Tests: `tests/unit/domain/test_profiles.py`, `tests/integration/test_devsim_piecewise_profile.py`, `tests/integration/test_devsim_fixed_bulk_charge.py`. |
| Material interfaces | Verified for electrostatic continuity, fixed sheet charge, surface SRH, and one charged trap level | Silicon, silicon dioxide, and generic dielectric combinations use registry-compatible electrostatics. Fixed charge has sign, unit, zero-charge reduction, and mesh-refinement evidence. Surface SRH and single-level donor or acceptor traps have detailed-balance, injection, current-conservation, occupancy, sign, and orientation evidence. Trap distributions, tunneling, and dispersion remain refused. Tests: `tests/unit/domain/test_interfaces.py`, `tests/integration/test_devsim_interface_charge.py`, `tests/integration/test_devsim_surface_physics.py`. |
| Contacts and boundaries | Verified for semiconductor ohmic, dielectric ideal gate, dielectric work function, silicon Schottky thermionic emission, and insulating boundaries | Contact offsets, area normalization, Richardson constants, barrier ordering, temperature response, driven-contact existence, electron and hole current, terminal charge, and explicit signs are canonical. Public identifiers are mapped to expression-safe internal DEVSIM symbols and restored in canonical results. Fermi Schottky injection, tunneling, and image-force lowering are refused. Tests: `tests/integration/test_devsim_work_function.py`, `tests/integration/test_devsim_schottky.py`, `tests/integration/test_devsim_advanced_physics.py`, `tests/integration/test_devsim_reference_benchmarks.py::test_equilibrium_accepts_hyphenated_contact_identifiers`. |
| Electrostatics | Verified | Poisson, dielectric flux, semiconductor charge, fixed bulk and interface charge, electron, hole, donor, acceptor, potential, field, and flux are implemented. Charge balance, field versus potential gradient, and scale-aware `div(D) = rho` residual checks are deterministic. The Poisson residual is covered by synthetic pass and failure cases plus the real abrupt-junction benchmark. |
| Carrier transport | Verified for Boltzmann Scharfetter-Gummel and reviewed Fermi quasi-Fermi-gradient transport | Electron and hole continuity, coupled solve, current densities, total current density, quasi-Fermi energies, nonnegative carrier checks, and terminal conservation are implemented. Boltzmann drift and diffusion components are exposed as explicitly labeled continuum diagnostics with a native-total reconciliation residual. Tests: `tests/integration/test_devsim_current_decomposition.py`, `tests/integration/test_devsim_fermi_statistics.py`. |
| Carrier statistics | Verified for Boltzmann and bounded Fermi transport | Fermi uses native DEVSIM `Fermi` and `InvFermi`, statistics-consistent neutral ohmic targets, continuation initialization, and a reviewed finite-volume transport equation. The verified upper benchmark is `5e19 cm^-3`; arbitrary convergence and Fermi Schottky injection are not claimed. Test: `tests/integration/test_devsim_fermi_statistics.py`. |
| Mobility | Verified for constant, Klaassen, temperature dependence, and one-dimensional high-field saturation | Electron and hole fields are extracted at every retained point. Dependencies and conflicting bulk selections are checked before execution. Tests: `tests/integration/test_devsim_advanced_physics.py`, `tests/integration/test_devsim_high_field_mobility.py`, `tests/unit/capabilities/test_capabilities.py`. Philips-style surface mobility is excluded from the one-dimensional adapter because its reviewed implementation requires two-dimensional element and interface-normal fields. |
| Recombination and generation | Verified for bulk SRH, Auger, and surface SRH | Configurable lifetimes, coefficients, capture velocities, temperature-dependent state, separate bulk and surface rates, total recombination, and electron and hole net generation are canonical. Decomposition, sign, unit, detailed balance, and finite-value checks are deterministic. |
| Band structure | Verified for reviewed Boltzmann and Fermi energy references | Conduction band, valence band, intrinsic energy, equilibrium Fermi energy, electron and hole quasi-Fermi energy, electron affinity, temperature-dependent gap, Slotboom narrowing, and effective intrinsic density are extracted in eV or canonical density units. Band ordering and provenance are checked. Tests: `tests/integration/test_devsim_advanced_physics.py`, `tests/integration/test_devsim_fermi_statistics.py`. |
| Operating studies | Verified for equilibrium, exact DC points, ranged DC, reverse and bidirectional order, adaptive DC recovery, AC, frequency, transient step, ramp, and pulse, temperature, registered parameters, and prescribed spatial temperature in its DC envelope | Resource limits allow up to 10,000 requested points. Exact researcher ordering and failed point state are preserved. Pulse delay, rise, hold, and fall are explicit researcher values. Prescribed temperature can be constant, linear, piecewise constant, or tabulated on silicon and drives local thermal voltage, gap, density of states, intrinsic density, SRH references, mobility, contacts, and edge current. It is not solved heat flow. Tests: `tests/integration/test_devsim_sweeps.py`, `test_devsim_ac.py`, `test_devsim_transient.py`, `test_devsim_parameter_studies.py`, `tests/integration/test_devsim_temperature_profile.py`. |
| Capacitance and impedance | Verified | Terminal charge, charge-voltage curves, stable finite-difference quasi-static capacitance, area-normalized and absolute results, complex current response, complex admittance, conductance, AC capacitance, and frequency axes are canonical. A real low-frequency AC versus quasi-static benchmark passes. Tests: `tests/integration/test_devsim_capacitance.py`, `test_devsim_ac.py`, `test_devsim_reference_benchmarks.py`. |
| Nonlinear solving | Verified for equilibrium-first initialization, bounded DC recovery, transient failure step reduction, adaptive transient growth, explicit controls, and event provenance | Maximum iterations, relative tolerance, and electrostatic or carrier absolute tolerances are typed. Requested points retain attempts and failures. Transient recovery is bounded by an explicit minimum step and retry count. Failed attempts are preserved as solver events, and an exhausted point is preserved with invalid field data rather than fabricated convergence. |
| Canonical observables and results | Verified | Scalar, terminal, spatial, response, multi-point spatial, complex-frequency, time, temperature, and parameter datasets carry axes, units, centering, validity masks, simulator model names, region identities, interface identities, and schema version. Legacy field migration remains supported. |
| Derived quantities | Verified for generic extrema, averages, peak magnitude and location, endpoint differences, integrals, gradients, built-in potential, current balance, quasi-static capacitance, AC capacitance, conductance, and static resistance | Every value is calculated from canonical datasets or operating points. Resistance requires a canonical bias voltage and compatible current series. Zero-current or invalid points remain invalid instead of becoming infinity or a fabricated value. Contact charge balance is validated. |
| Results Workbench | Verified for automatic dataset discovery, metrics, curves, profile families, heatmaps, complex modes, compatible same-run and multi-run overlays, linear/log/signed-log, zoom, pan, crosshair, tooltips, region/interface/contact markers, gaps, CSV, SVG, PNG, and raw evidence access | Plot choice uses axes, rank, units, centering, validity, and metadata. It does not inspect device names. The comparison API accepts two to eight distinct bundles, verifies every manifest and artifact hash, and rejects incompatible units. Recently opened verified runs become provenance-labeled overlay candidates. Visible comparison CSV, SVG, and PNG exports retain run identity. |
| Deterministic validation | Verified for schema, units, compatibility, completeness, shape, axes, centering, finiteness, exact study order, expected count, convergence, terminal current, equilibrium current, charge balance, contact charge, field gradient, Poisson residual, carrier positivity, recombination identities, band ordering, sweep continuity, paired AC versus quasi-static capacitance, and mesh and bias refinement | Sweep continuity uses a reviewed robust secant-slope outlier policy without assuming monotonic response. AC comparison requires paired canonical datasets and a recorded DC operating point. Acceptance thresholds are code-reviewed policy or researcher inputs, never LLM output. |
| Typed capability registry | Verified | Descriptors expose required and optional inputs, authority, dependencies, conflicts, materials, interfaces, studies, observables, validators, parameter sources, execution limits, maturity, digest, DEVSIM version, and a future Sentaurus mapping field. Tests: `tests/unit/capabilities/test_descriptors.py`, `tests/unit/capabilities/test_capabilities.py`. |
| Prompt preprocessing | Verified for the registered capability projection and seven-question bound | Complete requests proceed, consequential missing fields produce questions, dimensional ambiguity is surfaced, unsupported requests are blocked, safe expert defaults do not become researcher facts, and prompt plus answer hashes are preserved. Expanded natural intake cases cover every enabled study family and both major research gates. |
| Knowledge and RAG | Verified for local versioned retrieval | The corpus separates pinned DEVSIM 2.9.1 executable guidance from newer upstream information, preserves licence, hash, version, trust, review state, and backend compatibility, and cannot override schemas or capability policy. Retrieval tests cover solve controls, contacts, capacitance, AC, interface charge, parameter studies, Fermi/Schottky gates, recovery, and meshing. |
| Compiler and runtime isolation | Verified | The model supplies only typed data. All DEVSIM expressions and commands live under `adapters/devsim`. Compiled input and runtime digests, source mapping inputs, simulator version, solver configuration, model registry identity, atomic bundles, subprocess budgets, and validation artifacts are preserved. |
| Researcher-like evaluations | Verified | Natural prose covers complete, incomplete, ambiguous, contradictory, unfamiliar-name, equilibrium, DC, AC, frequency, transient, temperature, parameter, band, recombination, advanced boundaries, prescribed spatial temperature, and gated physics requests without schema-tuned wording. The ten-case live scope suite and both live preparation and execution workflows pass after test-first repairs. |
| Live Bedrock workflow | Verified on the configured macOS development host | Opt-in bounded tests exercised natural preparation, a consequential clarification, refusal, compiled intent, OpenHands tool use, explicit simulation approval, real DEVSIM execution, immutable artifacts, deterministic validation, Results Workbench API discovery, and graphable spatial data. The final full agent workflow produced a completed bundle with a passing validation report. Cross-platform live evidence remains separate. |
| Reference and convergence benchmarks | Verified for analytical junction voltage, depletion width, neutral slab, uniform resistor, parallel-plate capacitance, fixed interface charge, mesh refinement, bias-step refinement, low-frequency AC consistency, and pinned official DEVSIM capacitance, diode, small-signal, and two-region interface invariants | Official scripts execute from source commit `43b41ca845184c47e22b72d144db7e7db8509377`; independently parsed invariants are compared with canonical adapter outputs. The native workflow emits scientific evidence for Linux, Windows, macOS Intel, and macOS Apple Silicon and gates releases on one shared revision, source, simulator, fixture, and passing suite. A successful remote workflow run is still required to instantiate cross-platform evidence. Future Sentaurus conformance requires the same `ExperimentSpec` and a licensed host. |
| Explicit exclusions | Excluded | 2D and 3D geometry, process simulation, optical coupling, thermal transport, mechanical stress, hydrodynamic and ballistic transport, general quantum transport, arbitrary PDE execution, arbitrary generated DEVSIM Python, unreviewed material sets, and unproven Sentaurus equivalence. |

## Required final verification

Before this branch is presented for approval, all of the following must pass from a clean process:

```bash
.venv/bin/ruff check .
.venv/bin/mypy src/tcad_agent
.venv/bin/pytest -q
# Browser helper tests are executed by tests/unit/web/test_ide_javascript.py.
pnpm --dir desktop test
.venv/bin/python scripts/sync_requirements.py --check
git diff --check
```

The live Bedrock suite is run only when the credential is configured. Cross-platform installer evidence is separate from local scientific verification.

## Live verification record

The first bounded live pass found two defects rather than masking them:

- the ambiguous-input evaluation imposed a four-question cap even though the approved product limit is seven;
- the preparation model assigned evidence origin to the explicitly supplied word `uniform`.

The evaluation now uses the approved seven-question maximum. Origin reconciliation is deliberately narrow: it can correct an evidence label only when the exact scalar string occurs in the original prompt or clarification answers. A paired negative test proves that an unstated profile type remains refused.

The next full agent run exposed an adapter identifier defect. Public names such as `p-contact` were entering DEVSIM symbolic expressions, where a hyphen is an operator. The adapter now generates deterministic expression-safe internal contact identifiers while preserving public identifiers in canonical output. A real DEVSIM regression benchmark covers this behavior.

The final live checks passed:

- `ambiguous-oxide-thickness`: clarification within the seven-question contract;
- natural complete, blocked, generic-layer, and oxide-charge preparation cases from the bounded live suite;
- incomplete-request clarification followed by compiled intent;
- full natural equilibrium request through preprocessing, schema discovery, OpenHands, approval, DEVSIM, validation, immutable bundle generation, Results API loading, and graphable potential and electric-field discovery.

No credential value is written into this record, application events, generated bundles, or reports.

## Remaining target items

The full target contract is not represented as complete while any item below lacks its required benchmark. These items remain explicit work, not hidden approximations:

- cross-platform scientific reproducibility evidence on Linux and Windows in addition to this macOS host;
- licensed cross-backend conformance against Sentaurus using the same `ExperimentSpec`.

These are external evidence items, not unimplemented DEVSIM target families. The code-owned one-dimensional expansion list is complete. Unsupported combinations and excluded physics continue to fail before compilation.

## Local verification record

- Ruff: passed.
- strict mypy: passed across 133 source files.
- Python: 670 passed, 17 opt-in skips, 6 warnings.
- Desktop Node: 41 passed using the bundled standalone Node runtime. The host shell does not expose `node` on `PATH`, so the direct `pnpm test` wrapper is not a valid local invocation on this machine.
- dependency synchronization: passed.
- `git diff --check`: passed.
- tracked credential-material scan: no findings.
- named-device branch scan under `src/tcad_agent`: no findings.
- proprietary Sentaurus material scan: no documentation or licensed material found. The only Sentaurus-named files are the product-owned adapter template and its deterministic fixture.
