# Contacts, Boundary Conditions, and Interfaces

Status: source-grounded internal guidance awaiting TCAD domain-lead review.

## Why contact semantics matter

A contact is not merely a voltage label. It defines boundary equations for electrostatic potential, carrier populations or quasi-Fermi levels, and terminal current extraction. Work function, carrier selectivity, interface charge, surface recombination, and series resistance can all change the physical problem.

An “ohmic” contact usually implies equilibrium carrier exchange without a rectifying barrier in the intended operating regime. The exact boundary relation is backend and model dependent. A metal work function supplied by a researcher must not be ignored merely because both terminal voltages are zero.

## Electrostatic reference

Only potential differences are physically meaningful unless a reference is fixed. A connected device needs a consistent reference potential. At equilibrium, two external contacts can both be held at 0 V while internal electrostatic potential varies because of doping, material properties, and contact boundary conditions.

When reporting built-in potential, name the extraction definition. Possible definitions include a bulk-to-bulk electrostatic potential difference, a band-edge difference, or an analytical homojunction estimate. They are not interchangeable across metal-semiconductor boundaries or heterostructures.

## Ohmic and rectifying boundaries

Use an ohmic boundary only when the intended contact supports it. For a metal-semiconductor contact where barrier formation matters, the work-function and electron-affinity relation, interface states, image-force effects, and carrier emission model may be required. A product must refuse rather than silently replace a requested Schottky or selective contact with an ohmic one.

Carrier boundary conditions must be consistent with the chosen statistics and band-gap-narrowing model. A Boltzmann contact formula can conflict with a degenerate bulk model.

## Interfaces

Material interfaces may require:

- permittivity discontinuity and electrostatic flux continuity
- conduction- and valence-band offsets
- fixed sheet charge or polarization charge
- interface traps and recombination
- thermionic, tunnelling, or continuity conditions for carrier transport
- mesh alignment and normal orientation

Do not infer band offsets from band gaps alone. State interface orientation and the sign convention for sheet charge. Validate integrated charge and displacement-field behavior when the canonical schema exposes the needed quantities.

## Terminal currents

Check whether the backend reports electron current, hole current, displacement current, circuit current, or their sum, and whether the sign is into or out of the device. For one-dimensional simulations without an area, report current density. Total current requires an explicit cross-sectional area or a multidimensional integration measure.

At equilibrium, local drift and diffusion currents can be individually large and opposite. Net terminal current should be close to zero; requiring each component to vanish would be physically wrong.

## DEVSIM evidence route

Search the versioned DEVSIM command reference for `contact_node_model`, `contact_equation`, `interface_model`, and `interface_equation`. Confirm model location, circuit coupling, edge-current names, and derivative requirements against the pinned version. Official diode and capacitor examples illustrate patterns but do not define Agent Kronig capability.

## Validation questions

1. Is every contact attached to an actual boundary?
2. Is one electrical reference unambiguous?
3. Are contact and bulk statistics consistent?
4. Are work function and interface charges represented when requested?
5. Is terminal orientation recorded?
6. Does current conservation hold after normalization?

## Source basis

- DEVSIM Manual and command reference: https://devsim.net/
- DEVSIM official examples: https://github.com/devsim/devsim/tree/main/examples
- S. M. Sze and K. K. Ng, *Physics of Semiconductor Devices*, background reference only, not redistributed
