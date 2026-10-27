# Sentaurus TCAD through Kronig: backend guide

This guide tells Kronig what Sentaurus is, what Kronig can actually run on it today, and how to
ask a researcher informed questions. It is plain text on purpose: edit it to teach Kronig more,
and keep the inventory block below equal to the manifest (a test enforces this).

## What Sentaurus is

Sentaurus Device is an industrial TCAD simulator. It solves drift-diffusion (and, beyond that,
thermodynamic and hydrodynamic transport) on 1D, 2D and 3D structures, with a very large set of
physical models: many mobility, recombination and band-gap-narrowing models, quantum
corrections, tunnelling, impact ionization, traps, self-heating, optics, mixed-mode circuits,
small-signal AC, transient and noise analysis. Kronig reaches it over SSH on a shared HPC.
Runs take minutes, not seconds, because of license checkout and queueing on the shared license
pool.

Kronig currently drives a deliberately small, reviewed subset of that. A request outside the
subset is not impossible in Sentaurus, only not available through Kronig yet; say that plainly.

## Machine-checked inventory

```yaml inventory
models: [boltzmann, fermi, constant_mobility, klaassen_mobility, high_field_saturation, srh, auger, band_gap_narrowing, slotboom_bgn]
contacts: [ohmic, metal_work_function]
studies: [equilibrium, dc, dc_points]
materials: [silicon, silicon_dioxide]
profiles: [constant, box]
dimensions: [1, 2]
```

## Available now

- Structure, one dimension: silicon, plus silicon dioxide regions for MOS capacitors, with
  uniform doping per silicon region and up to 32 contiguous regions. A 1D request is built as a
  thin 2D slab and checked for uniformity.
- Structure, two dimensions: axis-aligned rectangular regions (silicon and silicon dioxide), each
  with its extent along the stack (depth) axis `x` and the lateral axis `y`; uniform doping per
  region plus doped rectangular windows with abrupt edges (for example a source and a drain); and
  contacts on a region side, optionally over a span of it. This covers planar transistors, where
  a vertical cut through the gate stack is the MOS capacitor. Other contacts keep a fixed voltage
  through their voltage offset, so a drain bias for an Id-Vgs curve is an offset on the drain.
- Contacts in one dimension sit at an end of the stack, `x_min` or `x_max` (a gate on top of an
  oxide is `x_min`); give only the contact id, kind, location and, for a metal, its work function. Never
  give a region, span or lateral side in one dimension: those exist only in two dimensions.
- Contacts: ohmic, or a metal contact with an explicit work function in eV. A metal on silicon
  is a Schottky contact. A metal on an oxide is a gate; give its work function. The ideal-gate
  option is not available.
- Carrier statistics: Boltzmann or Fermi.
- Mobility: constant, Klaassen (Philips unified, doping and carrier-carrier dependent), and
  optional high-field velocity saturation on top.
- Recombination: Shockley-Read-Hall and Auger. SRH lifetimes can be stated (electrons and holes
  together, in seconds); otherwise Sentaurus defaults apply and the report says so.
- Band-gap narrowing: Slotboom.
- Studies: equilibrium, a DC voltage sweep (start, stop, step), or an explicit list of DC
  voltages. At most 40 bias points per run. One temperature per run.
- Outputs: terminal current and charge, potential, electric field, electron and hole density,
  net charge density, conduction and valence band edges, quasi-Fermi levels, mobility,
  recombination rate (total, and separately Shockley-Read-Hall and Auger when those models are
  on), electron, hole and total current densities, net doping with donor and acceptor
  concentrations, band gap, band-gap narrowing (when that model is on), electron affinity,
  effective intrinsic carrier concentration and lattice temperature. Every one is drawn as an
  interactive graph. Spatial profiles are returned at every solved bias.
  In two dimensions the spatial outputs are lateral line profiles at a stated depth (a
  horizontal band diagram is a profile cut through the channel), the electric field and current
  densities are not available, and terminal currents are per micrometre of device width unless
  a width is given, which turns them into amperes. One run holds one set of fixed biases; a
  family of curves, such as Id-Vds for several gate voltages, is a set of runs.
- Meshing: a numeric spacing per region, or a fine minimum and a coarser maximum spacing, which
  refines at the interface with a neighbor region and grows away from it (thin MOS layers).

## Not yet available through Kronig

3D devices, non-rectangular and graded two-dimensional geometry (graded or Gaussian source and
drain implants, rounded corners, spacers other than rectangles), two-dimensional field maps and
heat maps, dielectrics other than silicon dioxide, the ideal-gate contact, non-uniform doping (Gaussian, error function, tabulated), AC small-signal and
capacitance-voltage by AC analysis, transient analysis, temperature sweeps in one run,
quantum corrections, band-to-band and trap-assisted tunnelling, impact ionization, interface
traps and fixed charge, self-heating and hydrodynamic transport, optical generation, mixed-mode
circuits, noise, custom parameter sets other than SRH lifetimes (mobility, Auger and other coefficients),
materials other than silicon and silicon dioxide, and advanced meshing (anchors, adaptive refinement).

## Decisions and how to handle them

| Decision | Handling | Options (consequence) | Recommended default |
| --- | --- | --- | --- |
| Study, driven contact, voltage range and step | ask if missing, never assume | equilibrium, DC sweep, explicit voltage list | none |
| Geometry, doping, contact type and work function | ask if missing, never assume | ohmic or metal with work function in eV | none |
| Temperature | ask if missing | any single value in K | none |
| Carrier statistics | ask only if doping reaches about 1e18 per cm3 or injection is high; otherwise default | Boltzmann (fast, valid for dilute carriers), Fermi (needed when degenerate) | Boltzmann |
| Mobility | ask only if the goal depends on doping, field or injection; otherwise default | constant (simple baseline), Klaassen (doping and carrier scattering), Klaassen plus high-field saturation (strong fields) | constant |
| Recombination | default model; ask for lifetimes only if reverse leakage or generation matters or the result will be compared with another simulator | SRH (generation and leakage in depletion), plus Auger (high injection or heavy doping); lifetimes for electrons and holes in s | SRH with Sentaurus default lifetimes, stated in the report |
| Band-gap narrowing | ask only if heavily doped | Slotboom (heavy doping shifts intrinsic density), none | none |
| Outputs that need a model (SRH or Auger recombination rate, band-gap narrowing) | when the researcher asks for one of these outputs, put the matching model in the physics of the experiment you draft and say so in the summary, so it appears in the plan for approval; never leave the output without its model and never turn a model on without showing it | SRH rate needs SRH, Auger rate needs Auger, band-gap narrowing needs Slotboom | add the model |
| Material | do not ask: a semiconductor region is silicon and an insulating layer between a gate and the silicon is silicon dioxide; only these two are supported, so say it in the summary and use them | silicon, silicon dioxide | silicon (semiconductor), silicon dioxide (gate insulator) |
| Dimension | do not ask for a layered stack: a pn junction, pin diode, Schottky contact or MOS capacitor is one dimensional; use two dimensions only when a transistor or another laterally structured device is described | 1D (layered stack), 2D (lateral structure) | 1D for stacks, 2D for transistors |
| 2D geometry, doping windows, contact placement | ask if missing, never assume; ask which region side and span each contact occupies | rectangles with material and extents along depth and lateral axes; windows with species and concentration | none |
| 2D profile cut depth | ask when any spatial profile is wanted | a depth in nm below the surface; a channel is a few nanometres under the oxide interface, a deeper cut shows the bulk | none |
| 2D device width | ask only when currents are wanted in amperes | a width in um; otherwise currents are per 1 um of width | per 1 um |
| Fixed biases of the other contacts | ask which contact is swept and what the others are held at | for example drain held at a small voltage for a linear-region Id-Vgs | none |
| Mesh spacing | ask if missing; always a number | finer is slower and more accurate; a few nanometres for sub-micron junctions | none |
| Which voltages need spatial profiles | ask if profiles are wanted for a sweep | any subset of the swept voltages | all swept voltages |
| Absolute current instead of density | in a 1D stack ask for the contact area; in a 2D device never ask for an area, the device width (above) is what converts it | current density needs no area | density |

## How to ask

Ask one question per open decision, each with its own unique id and its own field path. Model
choices all belong to `physics.models`, so give each a distinct sub-path: carrier statistics
`physics.models.statistics`, mobility `physics.models.mobility`, recombination
`physics.models.recombination`, band-gap narrowing `physics.models.band_gap_narrowing`. Two-dimensional
geometry questions use `regions.extents`, `profiles.windows` and `contacts.placement`; the cut depth
uses `profile_cuts.depth` and the width `width`. Never
reuse one path for two questions. Give each option with its consequence in a few words, mark
the recommended default, and state the unit for every number. Do not ask about decisions marked
default unless the researcher's goal depends on them. Never offer an option that is not under
"Available now". If the researcher asks for something under "Not yet available through Kronig",
say Sentaurus can do it but Kronig cannot run it yet, and ask whether to proceed with the
closest available alternative.

## Electrode gaps (2D)

Sentaurus refuses two electrodes that touch or overlap. Source, drain and gate regions that abut at a
surface corner therefore need a gap: give one contact a span that stops a short, stated distance
(about one mesh cell) before the other, record it as an assumption, and never move a doping edge or
an oxide edge to make room.

## Honest limits

Results are from an automatically generated mesh and are not calibrated against measurements.
Kronig reports validation checks with their limits, and the numerical noise floor for Sentaurus
currents is recorded in its manifest. A Sentaurus run is a different solver from DEVSIM, so small
differences between the two are expected and are not by themselves a sign of error.
