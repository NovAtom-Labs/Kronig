# DEVSIM through Kronig: backend guide

This guide tells Kronig what DEVSIM is, what Kronig can actually run on it today, and how to ask a
researcher informed questions. It is plain text on purpose: edit it to teach Kronig more, and keep
the inventory block below equal to the manifest (a test enforces this).

## What DEVSIM is

DEVSIM is an open-source TCAD simulator that solves drift-diffusion on one- and two-dimensional
structures. Kronig runs it on the researcher's own computer, so a run takes seconds to a few minutes
and needs no queue or licence. The physics is the same drift-diffusion model as in Sentaurus; the
numerical details and default material constants differ, so small differences between the two are
expected.

Kronig drives a reviewed subset of DEVSIM. A request outside the subset is not impossible in
DEVSIM, only not available through Kronig yet; say that plainly.

## Machine-checked inventory

```yaml inventory
dimensions: [1, 2]
models: [boltzmann, fermi, constant_mobility, klaassen_mobility, high_field_saturation, srh, auger, slotboom_bgn]
materials: [silicon, silicon_dioxide, generic_dielectric]
profiles: [constant, box, fixed_charge, piecewise_constant, linear, gaussian, error_function, tabulated]
contacts: [ohmic, ideal_gate, metal_work_function, insulating]
studies: [equilibrium, dc, dc_points, ac, frequency, transient, temperature, parameter]
```

## Available now

- Structure, one dimension: a stack of contiguous regions along `x`: silicon, silicon dioxide or a
  generic dielectric with a stated permittivity. Doping per silicon region may be constant, linear,
  Gaussian, error-function, tabulated or piecewise constant; fixed charge and interface fixed charge,
  surface recombination and interface traps are available. Contacts sit at an end of the stack,
  `x_min` or `x_max` (a gate on top of an oxide is `x_min`); give only the contact id, kind,
  location and, for a metal, its work function. Never give a region, span or lateral side in one
  dimension: those exist only in two dimensions.
- Structure, two dimensions: axis-aligned rectangular regions (silicon and an insulator), each with its
  extent along the stack (depth) axis `x` and the lateral axis `y`; constant doping per region plus
  doped rectangular windows with abrupt edges (a source and a drain); contacts on a region side,
  optionally over a span of it. This covers planar transistors, where a vertical cut through the gate
  stack is the MOS capacitor. Other contacts keep a fixed voltage through their voltage offset, so a
  drain bias for an Id-Vgs curve is an offset on the drain. In two dimensions a contact on silicon is
  ohmic and a contact on an insulator is a gate with its work function; a metal contact directly on
  silicon (a Schottky contact) is available in one dimension only.
- Contacts: ohmic; a metal with an explicit work function in eV (on silicon it is a Schottky
  contact, on an oxide it is a gate); an ideal gate; insulating.
- Carrier statistics: Boltzmann or Fermi-Dirac, in one and two dimensions.
- Mobility: constant, Klaassen, and optional high-field velocity saturation on top.
- Recombination: Shockley-Read-Hall (lifetimes may be stated) and, in one dimension, Auger.
- Band-gap narrowing: Slotboom, in one dimension only.
- Studies: in one dimension equilibrium, a DC sweep, an explicit DC voltage list, small-signal AC and
  frequency response, transient, temperature and parameter sweeps; in two dimensions equilibrium and
  DC only. One temperature per run except in a temperature sweep.
- Outputs: terminal current and charge, potential, electric field, electron and hole density, net
  charge density, conduction and valence band edges, quasi-Fermi levels, mobility, recombination
  rates, current densities, net doping, band gap, band-gap narrowing, electron affinity and effective
  intrinsic density. In two dimensions the spatial outputs are lateral line profiles at a stated
  depth (a horizontal band diagram is a profile cut through the channel); electric field and current
  densities are not available along a cut, and terminal currents are per metre of device width unless
  a width is given, which turns them into amperes. One run holds one set of fixed biases; a family of
  curves such as Id-Vds for several gate voltages is a set of runs.
- Meshing: a numeric spacing per region, or a fine minimum and a coarser maximum spacing. In two
  dimensions the mesh grows geometrically away from a silicon and insulator interface.

## Not yet available through Kronig

3D devices, non-rectangular and graded two-dimensional geometry (graded or Gaussian implants, rounded
corners), Auger recombination and band-gap narrowing in two dimensions, AC, transient, temperature
and parameter studies in two dimensions, a Schottky contact in two dimensions, two-dimensional field
maps, quantum corrections, tunnelling, impact ionization, self-heating, optical generation, mixed-mode
circuits, noise and materials other than silicon and the insulators above.

## Decisions and how to handle them

| Decision | Handling | Options (consequence) | Recommended default |
| --- | --- | --- | --- |
| Study, driven contact, voltage range and step | ask if missing, never assume | equilibrium, DC sweep, explicit voltage list | none |
| Geometry, doping, contact type and work function | ask if missing, never assume | ohmic or metal with work function in eV | none |
| Temperature | ask if missing | any single value in K | none |
| Carrier statistics | a metal contact whose work function is within 0.1 eV of a band edge or beyond it, any MOS stack or transistor, and doping above about 1e18 per cm3 need Fermi-Dirac; otherwise default | Boltzmann (valid for dilute carriers), Fermi (needed when degenerate) | Boltzmann for dilute pn junctions, Fermi otherwise |
| Mobility | ask only if the goal depends on doping, field or injection; otherwise default | constant, Klaassen, Klaassen plus high-field saturation | constant |
| Recombination | default model; ask for lifetimes only if reverse leakage matters | SRH, plus Auger in one dimension | SRH |
| Band-gap narrowing | ask only if heavily doped and one dimensional; in two dimensions say it is not available | Slotboom, none | none |
| Material | do not ask: a semiconductor region is silicon and an insulating layer between a gate and the silicon is silicon dioxide, say so in the summary | silicon, silicon dioxide | silicon, silicon dioxide |
| Dimension | do not ask for a layered stack: a pn junction, pin diode, Schottky contact or MOS capacitor is one dimensional; use two dimensions only for a transistor or another laterally structured device | 1D, 2D | 1D for stacks, 2D for transistors |
| 2D geometry, doping windows, contact placement | ask if missing, never assume; ask which region side and span each contact occupies | rectangles with material and extents along depth and lateral axes; windows with species and concentration | none |
| 2D profile cut depth | ask when any spatial profile is wanted | a depth in nm below the surface; a channel is a few nanometres under the oxide interface | none |
| 2D device width | ask only when currents are wanted in amperes | a width in um; otherwise currents are per metre of width | per unit width |
| Fixed biases of the other contacts | ask which contact is swept and what the others are held at | for example a drain held at a small voltage for a linear-region Id-Vgs | none |
| Mesh spacing | ask if missing; always a number | finer is slower and more accurate; a few nanometres for sub-micron junctions | none |
| Which voltages need spatial profiles | ask if profiles are wanted for a sweep | any subset of the swept voltages | all swept voltages |
| Absolute current instead of density | in a 1D stack ask for the contact area; in a 2D device never ask for an area, the device width is what converts it; once the researcher accepts density, stop asking | current density needs no area | density |

## How to ask

Ask one question per open decision, each with its own unique id and its own field path. Model choices
all belong to `physics.models`, so give each a distinct sub-path: carrier statistics
`physics.models.statistics`, mobility `physics.models.mobility`, recombination
`physics.models.recombination`. Two-dimensional geometry questions use `regions.extents`,
`profiles.windows` and `contacts.placement`; the cut depth uses `profile_cuts.depth` and the width
`width`. Never reuse one path for two questions. Give each option with its consequence in a few words,
mark the recommended default, and state the unit for every number. Do not ask about decisions marked
default unless the researcher's goal depends on them. Never offer an option that is not under
"Available now". If the researcher asks for something under "Not yet available through Kronig", say
DEVSIM can do it but Kronig cannot run it yet, and ask whether to proceed with the closest available
alternative, or to run it on Sentaurus.

## Honest limits

Results are from an automatically generated mesh and are not calibrated against measurements. Kronig
reports validation checks with their limits. A DEVSIM run is a different solver from Sentaurus, so
small differences between the two are expected and are not by themselves a sign of error.
