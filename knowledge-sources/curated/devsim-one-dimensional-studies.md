# One-Dimensional DEVSIM Studies in Agent Kronig

Status: engineering-curated from the pinned DEVSIM 2.9.1 source, the official 2.9.0 command reference, real adapter benchmarks, and the portable product contracts. This is implementation guidance, not a substitute for device-physics review.

## Version boundary and evidence authority

The packaged runtime is DEVSIM 2.9.1. Executable claims must be supported by the pinned 2.9.1 source at commit `43b41ca845184c47e22b72d144db7e7db8509377`, the compatible official 2.9.0 command documentation at commit `8fbe81b5719307d654f37d630cf043dc6ae0512e`, and a passing adapter benchmark. Newer upstream releases are separate evidence records. Their existence does not make a feature available in the packaged runtime.

The DEVSIM command surface is broader than the Agent Kronig adapter. The official `solve` command lists DC, AC, noise, transient DC, backward-difference, and trapezoidal modes. Upstream examples demonstrate contact charge, small-signal circuit response, and transient integration. Agent Kronig advertises only paths that also have a simulator-neutral contract, deterministic compiler, normalized extractor, validator, and passing reference test.

## Composition instead of device names

Represent a one-dimensional problem as ordered regions, adjacent interfaces, spatial profiles, boundary contacts, physical equations and models, a study schedule, and requested observables. Names such as diode or capacitor may remain in human-facing titles but must never select the runtime path.

Regions are contiguous intervals with explicit materials and mesh spacing. The reviewed material set currently contains silicon and silicon dioxide. Carrier continuity equations apply only inside semiconductor regions. Dielectrics participate in electrostatics and displacement, not electron or hole transport.

Adjacent regions require explicit interface records. Continuity is available for reviewed silicon-to-silicon and silicon-to-silicon-dioxide compositions. A fixed interface-charge field exists in the portable contract but is refused by the DEVSIM runtime until a benchmark proves its sign, units, and residual behavior.

## Profiles and units

The supported profile primitives are constant, linear, Gaussian, error-function, and tabulated. Each profile belongs to one region and has an explicit donor or acceptor species. Multiple profiles superpose algebraically. Spatial quantities are normalized to SI in the product contract and converted to centimeters only inside the DEVSIM adapter.

Never infer an ambiguous unit. A statement such as an oxide thickness of `10 m` must be confirmed if the researcher may have meant nanometers. Do not silently reinterpret it based on typical fabrication dimensions. Tabulated coordinates must stay within the owning region, be strictly ordered, and declare the interpolation rule.

## Boundary semantics

An ohmic contact is valid only where the reviewed semiconductor contact equations are intended. An ideal gate is valid on the dielectric side of a reviewed oxide stack. A numerical contact voltage is not a metal work function.

A requested aluminum work function, Schottky barrier, surface recombination velocity, tunneling boundary, or interface trap distribution changes the physical boundary model. If the adapter does not advertise the exact contact capability, block the run. Never replace a metal-semiconductor boundary with an ohmic contact merely to obtain convergence.

## Electrostatics and transport sequence

Construct the mesh and material parameters first. Solve electrostatic equilibrium before creating and initializing carrier solutions. For drift diffusion, create the electron and hole equations only in semiconductor regions, then connect compatible semiconductor interfaces and solve the coupled system.

The reviewed transport path uses Boltzmann carrier statistics, constant mobility, and Shockley-Read-Hall recombination through the pinned DEVSIM helper implementation. Fermi-Dirac statistics, Auger recombination, band-gap narrowing, field-dependent mobility, incomplete ionization, quantum corrections, and self-heating are not interchangeable refinements. They must remain unsupported until their equations, derivatives, parameters, observables, and benchmarks are reviewed together.

## Equilibrium and DC studies

Equilibrium holds all explicit terminal biases at their declared values, normally zero, and reports one operating point. A DC range expands into an ordered bounded list. Exact DC points preserve researcher order, including bidirectional sequences such as `0 V`, `+2 V`, and `-2 V`.

Adaptive continuation may insert internal recovery points after a failed nonlinear solve. It must not change requested voltages, geometry, materials, doping, temperature, physical models, or outputs. The canonical result retains the requested point, attempt count, state, and failure message. A failed point is not removed, interpolated, or marked converged.

Large forward or reverse biases can fail for physical or numerical reasons. The appropriate output is a visible failed operating point plus evidence, not a fabricated curve. Mesh or step refinement is a new bounded attempt whose provenance must be preserved.

## Charge and quasi-static capacitance

DEVSIM exposes contact charge for the potential equation. Agent Kronig normalizes one-dimensional contact charge as charge per unit transverse area in `C/m^2`. It does not claim total charge without a researcher-supplied area.

For a strictly monotonic voltage sequence with unique points, quasi-static capacitance density is the finite-difference derivative `dQ/dV` in `F/m^2`. Duplicate, unordered, or bidirectional voltage points do not produce one implicit derivative curve. Use separate monotonic branches or request exact point data. Absolute capacitance requires area and must trigger clarification when area is absent.

Small-signal AC capacitance is a different study. Upstream DEVSIM examples use circuit coupling, an AC source, `solve(type="ac", frequency=...)`, and complex circuit-current solutions. That upstream capability is not advertised by this adapter until complex normalization and reference benchmarks are complete.

## Canonical datasets

Every numeric result is represented by named axes and typed datasets. Common axes include position, bias, frequency, time, temperature, parameter, and index. Dataset shape must exactly match its axes. Centering records whether values live on nodes, edges, contacts, operating points, or as scalars.

Potential is node-centered. Electric field and drift-diffusion current densities are edge-centered. Carrier density, net doping, charge density, mobility, and local recombination rate are node-centered. Terminal current density and charge density are operating-point quantities. Preserve duplicate interface coordinates when they represent values from different adjacent regions; never average them silently.

The viewer discovers scalar metrics, curves, profile families, heatmaps, and complex responses from dataset metadata. It does not need a device category. Reports and summaries must derive numbers from canonical datasets rather than parsing prose or simulator logs.

## Validation

Validation is layered. First verify execution and schema integrity. Then verify all requested points and explicit convergence states. Check finiteness, units, shape, axes, and centering. Check terminal current balance with absolute and relative tolerances. Carrier densities must remain nonnegative. When potential and electric field are both present, compare the edge field with the negative spatial gradient of potential using a scale-aware tolerance.

At equilibrium, terminal current must be numerically negligible. An abrupt silicon junction may be compared with an analytical built-in-potential estimate only when the approximation assumptions apply. A passing analytical check does not prove contact physics, mobility calibration, or predictive validity.

Capacitance derived from charge must cite the source charge dataset and derivative rule. Mesh and bias-step refinement compare derived observables, not just solver exit codes. A converged result can still fail physical validation.

## Prompt preparation decisions

The researcher owns geometry, materials, layer ordering, doping identity and magnitude, contact intent, applied conditions, study bounds, fixed parameters, and requested deliverables. Reviewed evidence may choose expert-owned mesh, solver, diagnostics, and validation methods. Operational defaults may choose filenames and presentation details.

Ask a concise batch only for missing inputs that change correctness or feasibility. Important examples include ambiguous dimensions, unknown driven contact, missing voltage range, absolute capacitance without area, AC response without frequency, and an unclear request to reuse parameters that are not present in the current message or repository.

When a complete request contains unsupported physics, block it with exact capability paths rather than asking unrelated questions. When a request mixes supported and unsupported deliverables, list the supported subset and exclusions, but do not execute a reduced study unless the researcher explicitly accepts that changed scope.

## Source basis

- DEVSIM 2.9.1 `python_packages/simple_physics.py`
- DEVSIM 2.9.1 `python_packages/fermi_physics.py`
- DEVSIM 2.9.1 `examples/capacitance/cap1d.py`
- DEVSIM 2.9.1 `examples/diode/ssac_diode.py`
- DEVSIM 2.9.1 `examples/diode/tran_diode.py`
- DEVSIM documentation 2.9.0 `pydoc/solverCommands.py`
- `src/tcad_agent/domain/`
- `src/tcad_agent/adapters/devsim/`
- `src/tcad_agent/results/`
- `src/tcad_agent/validation/`
