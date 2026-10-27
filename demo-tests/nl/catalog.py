"""Natural-language test catalog: terse prompts, what the researcher knows, and ground truth."""

PN_OBS = ["potential", "electric_field", "electron_density", "hole_density"]
BANDS = ["conduction_band", "valence_band"]


def pn(p, n, extra=""):
    return (
        f"silicon pn junction, 1 um long with the junction in the middle (p side 0 to 0.5 um is the "
        f"anode on the left, n side 0.5 to 1 um is the cathode on the right), p side {p} acceptor and "
        f"n side {n} donor, both uniform, ohmic contact at both ends, 10 nm mesh, {extra}"
    )


def metal_semi(kind, dop, wf, study):
    species = "donor" if kind == "n" else "acceptor"
    return (
        f"1 um of {kind}-type silicon doped {dop} {species} uniform, a metal contact on the left end "
        f"with work function {wf} eV (the Schottky contact) and an ohmic contact on the right end, "
        f"300 K, boltzmann statistics, constant mobility, SRH, 5 nm mesh, {study}"
    )


def mos(kind, dop, tox_nm, wf, study):
    species = "acceptor" if kind == "p" else "donor"
    return (
        f"MOS capacitor: gate metal with work function {wf} eV on top of a {tox_nm} nm silicon dioxide "
        f"layer on {kind}-type silicon {dop} {species} uniform, 1 um of silicon thickness, ohmic body "
        f"contact at the bottom, 300 K, fermi statistics, constant mobility, SRH, mesh 1 nm in the "
        f"oxide and in the silicon graded from 0.5 nm at the oxide interface to 10 nm in the bulk, "
        f"{study}"
    )


FET = (
    "planar n-channel MOSFET: 5 nm silicon dioxide gate oxide over the middle of the surface "
    "(0.1 to 0.2 um laterally), p-type silicon body doped 1e17 acceptor, 200 nm deep and 0.3 um long, "
    "n+ source 0 to 0.1 um and n+ drain 0.2 to 0.3 um at the surface, each 1e20 donor and 50 nm deep, "
    "gate work function 4.1 eV, ohmic source, drain and body contacts (body at the bottom), 300 K, "
    "fermi statistics, constant mobility, SRH, mesh 10 nm in the silicon and 2.5 nm in the oxide, "
    "device width 10 um, read profiles along a horizontal line 1 nm below the oxide interface"
)

TESTS = {}


def add(name, experiment, prompt, facts, expect):
    TESTS[name] = {"experiment": experiment, "prompt": prompt, "facts": facts, "expect": expect}


def pn_expect(**kw):
    base = {
        "dimension": 1,
        "regions": [("silicon", 0, 0.5), ("silicon", 0.5, 1.0)],
        "temperature_k": 300,
    }
    base.update(kw)
    return base


# 1. PN equilibrium
add("t1a", 1, "show me the band diagram and electrostatics of a pn junction at equilibrium on sentaurus",
    pn("1e17", "1e16", "300 K, boltzmann statistics, constant mobility, SRH, equilibrium, show potential, "
       "electric field, electron and hole density, conduction and valence band edges and the fermi level"),
    pn_expect(doping=[("acceptor", 1e17, 0), ("donor", 1e16, 1)], study={"kind": "equilibrium"},
              observables=PN_OBS + BANDS + ["fermi_level"], contacts=2))
add("t1b", 1, "heavily doped symmetric pn junction at equilibrium, sentaurus, need fermi statistics",
    pn("5e18", "5e18", "300 K, fermi statistics, constant mobility, SRH, equilibrium, show potential, "
       "electric field, carrier densities and the band edges"),
    pn_expect(doping=[("acceptor", 5e18, 0), ("donor", 5e18, 1)], study={"kind": "equilibrium"},
              models=["fermi"], observables=PN_OBS + BANDS, contacts=2))
# 2. PN bias
add("t2a", 2, "pn junction under forward and reverse bias, electrostatics and iv curve, use sentaurus",
    pn("1e17", "1e16", "300 K, boltzmann statistics, constant mobility, SRH, sweep the anode from -1 V "
       "to 0.6 V in 0.2 V steps with the cathode at 0 V, current density is fine, save spatial profiles "
       "at -1 V, 0 V and 0.6 V, show potential, electric field, electron and hole density and terminal current"),
    pn_expect(doping=[("acceptor", 1e17, 0), ("donor", 1e16, 1)],
              study={"kind": "dc", "contact": "anode", "start": -1.0, "stop": 0.6, "step": 0.2},
              profile_bias=[-1.0, 0.0, 0.6], observables=PN_OBS + ["terminal_current_density"], contacts=2))
add("t2b", 2, "forward bias iv of a diode on sentaurus",
    pn("1e17", "1e16", "300 K, boltzmann statistics, constant mobility, SRH, sweep the anode from 0 V to "
       "0.8 V in 0.1 V steps with the cathode at 0 V, current density is fine, I only need the iv curve"),
    pn_expect(doping=[("acceptor", 1e17, 0), ("donor", 1e16, 1)],
              study={"kind": "dc", "contact": "anode", "start": 0.0, "stop": 0.8, "step": 0.1},
              observables=["terminal_current_density"], contacts=2))
# 3. PN varied parameters
add("t3a", 3, "same pn junction but heavier p side 1e18 and lighter n side 1e15, forward bias sweep, sentaurus",
    pn("1e18", "1e15", "300 K, boltzmann statistics, constant mobility, SRH, sweep the anode from 0 V to "
       "0.6 V in 0.2 V steps with the cathode at 0 V, current density is fine, show terminal current, "
       "potential and electric field"),
    pn_expect(doping=[("acceptor", 1e18, 0), ("donor", 1e15, 1)],
              study={"kind": "dc", "contact": "anode", "start": 0.0, "stop": 0.6, "step": 0.2},
              observables=["terminal_current_density", "potential", "electric_field"], contacts=2))
add("t3b", 3, "diode iv at 350 K, sentaurus",
    pn("1e17", "1e16", "350 K, boltzmann statistics, constant mobility, SRH, sweep the anode from 0 V to "
       "0.6 V in 0.2 V steps with the cathode at 0 V, current density is fine, I only need the iv curve"),
    pn_expect(temperature_k=350, doping=[("acceptor", 1e17, 0), ("donor", 1e16, 1)],
              study={"kind": "dc", "contact": "anode", "start": 0.0, "stop": 0.6, "step": 0.2},
              observables=["terminal_current_density"], contacts=2))
add("t3c", 3, "pin diode iv curve on sentaurus",
    "silicon pin diode, 1 um long: p+ region 0 to 0.2 um (anode, left) 1e18 acceptor, lightly doped "
    "n- intrinsic-like region 0.2 to 0.8 um 1e14 donor, n+ region 0.8 to 1.0 um (cathode, right) 1e18 "
    "donor, all uniform, ohmic contacts at both ends, 10 nm mesh, 300 K, boltzmann statistics, constant "
    "mobility, SRH, sweep the anode from 0 V to 0.8 V in 0.2 V steps with the cathode at 0 V, current "
    "density is fine, I only need the iv curve",
    {"dimension": 1, "regions": [("silicon", 0, 0.2), ("silicon", 0.2, 0.8), ("silicon", 0.8, 1.0)],
     "temperature_k": 300,
     "doping": [("acceptor", 1e18, 0), ("donor", 1e14, 1), ("donor", 1e18, 2)],
     "study": {"kind": "dc", "contact": "anode", "start": 0.0, "stop": 0.8, "step": 0.2},
     "observables": ["terminal_current_density"], "contacts": 2})
# 4. metal-semiconductor electrostatics, four combinations
for name, kind, dop, wf, word in (("t4a", "n", "1e16", 4.1, "low doped n-type"), ("t4b", "n", "1e18", 4.7, "heavily doped n-type"),
                                  ("t4c", "p", "1e16", 4.7, "low doped p-type"), ("t4d", "p", "1e18", 4.1, "heavily doped p-type")):
    species = "donor" if kind == "n" else "acceptor"
    add(name, 4, f"electrostatics of a metal contact on {word} silicon at equilibrium, sentaurus",
        metal_semi(kind, dop, wf, "equilibrium, show potential, electric field, electron and hole density, "
                   "band edges and the fermi level"),
        {"dimension": 1, "regions": [("silicon", 0, 1.0)], "temperature_k": 300,
         "doping": [(species, float(dop), 0)], "study": {"kind": "equilibrium"},
         "observables": ["potential", "electric_field", "electron_density", "hole_density"] + BANDS,
         "contact_wf": wf, "contacts": 2})
# 5. Schottky I-V
add("t5a", 5, "schottky diode iv on n-type silicon, sentaurus",
    metal_semi("n", "1e16", 4.7, "sweep the metal contact from -1 V to 0.4 V in 0.2 V steps with the ohmic "
               "contact at 0 V, current density is fine, I only need the iv curve"),
    {"dimension": 1, "regions": [("silicon", 0, 1.0)], "temperature_k": 300,
     "doping": [("donor", 1e16, 0)],
     "study": {"kind": "dc", "contact": "metal", "start": -1.0, "stop": 0.4, "step": 0.2},
     "observables": ["terminal_current_density"], "contact_wf": 4.7, "contacts": 2})
add("t5b", 5, "iv curve of a schottky contact on p-type silicon with sentaurus",
    metal_semi("p", "1e16", 4.3, "sweep the metal contact from -0.4 V to 0.4 V in 0.2 V steps with the ohmic "
               "contact at 0 V, current density is fine, I only need the iv curve"),
    {"dimension": 1, "regions": [("silicon", 0, 1.0)], "temperature_k": 300,
     "doping": [("acceptor", 1e16, 0)],
     "study": {"kind": "dc", "contact": "metal", "start": -0.4, "stop": 0.4, "step": 0.2},
     "observables": ["terminal_current_density"], "contact_wf": 4.3, "contacts": 2})
# 6. MOS capacitor equilibrium
add("t6a", 6, "mos capacitor at equilibrium, show the band diagram, sentaurus",
    mos("p", "1e17", 5, 4.1, "equilibrium, show potential, electric field, electron and hole density and band edges"),
    {"dimension": 1, "regions": [("silicon_dioxide", 0, 0.005), ("silicon", 0.005, 1.005)], "temperature_k": 300,
     "doping": [("acceptor", 1e17, 1)], "study": {"kind": "equilibrium"},
     "observables": ["potential", "electric_field", "electron_density", "hole_density"] + BANDS,
     "contact_wf": 4.1, "contacts": 2})
add("t6b", 6, "n-type substrate mos capacitor equilibrium on sentaurus",
    mos("n", "1e17", 10, 5.0, "equilibrium, show potential, electric field, electron and hole density and band edges"),
    {"dimension": 1, "regions": [("silicon_dioxide", 0, 0.01), ("silicon", 0.01, 1.01)], "temperature_k": 300,
     "doping": [("donor", 1e17, 1)], "study": {"kind": "equilibrium"},
     "observables": ["potential", "electric_field", "electron_density", "hole_density"] + BANDS,
     "contact_wf": 5.0, "contacts": 2})
# 7. MOS capacitor under bias
add("t7a", 7, "mos capacitor gate voltage sweep, charge vs voltage, sentaurus",
    mos("p", "1e17", 5, 4.1, "sweep the gate from -2 V to 2 V in 0.5 V steps with the body at 0 V, show "
        "terminal charge, potential, electron and hole density and band edges, current density is fine"),
    {"dimension": 1, "regions": [("silicon_dioxide", 0, 0.005), ("silicon", 0.005, 1.005)], "temperature_k": 300,
     "doping": [("acceptor", 1e17, 1)],
     "study": {"kind": "dc", "contact": "gate", "start": -2.0, "stop": 2.0, "step": 0.5},
     "observables": ["terminal_charge", "potential", "electron_density", "hole_density"] + BANDS,
     "contact_wf": 4.1, "contacts": 2})
add("t7b", 7, "n-type mos capacitor under bias on sentaurus, i want the charge curve",
    mos("n", "1e17", 10, 5.0, "sweep the gate from -2 V to 2 V in 0.5 V steps with the body at 0 V, show "
        "terminal charge and potential, current density is fine"),
    {"dimension": 1, "regions": [("silicon_dioxide", 0, 0.01), ("silicon", 0.01, 1.01)], "temperature_k": 300,
     "doping": [("donor", 1e17, 1)],
     "study": {"kind": "dc", "contact": "gate", "start": -2.0, "stop": 2.0, "step": 0.5},
     "observables": ["terminal_charge", "potential"], "contact_wf": 5.0, "contacts": 2})
# 8. MOSFET horizontal band diagram
FET_EXPECT = {"dimension": 2, "temperature_k": 300, "cut_at_nm": 6, "width_um": 10, "contacts": 4,
              "oxide_nm": 5, "body": (0.2, 0.3),
              "doping2d": [("acceptor", 1e17), ("donor", 1e20), ("donor", 1e20)], "contact_wf": 4.1}
add("t8a", 8, "horizontal band diagram of a mosfet at a few gate biases, use sentaurus",
    FET + ", gate at 0 V, 0.5 V and 1.0 V with the drain at 0.1 V and source and body at 0 V, show "
    "conduction band, valence band, electron and hole density and the quasi-fermi levels",
    {**FET_EXPECT, "study": {"kind": "dc", "contact": "gate", "start": 0.0, "stop": 1.0, "step": 0.5},
     "drain_offset": 0.1, "observables": BANDS + ["electron_density", "hole_density"]})
add("t8b", 8, "mosfet band diagram along the channel under different gate voltages with the drain biased, sentaurus",
    FET + ", gate from 0 V to 1.0 V in 0.5 V steps with the drain held at 0.5 V and source and body at 0 V, "
    "show conduction band, valence band and electron density",
    {**FET_EXPECT, "study": {"kind": "dc", "contact": "gate", "start": 0.0, "stop": 1.0, "step": 0.5},
     "drain_offset": 0.5, "observables": BANDS + ["electron_density"]})
# 9. MOSFET I-V
add("t9a", 9, "mosfet id-vgs curve at low drain bias on sentaurus",
    FET + ", sweep the gate from 0 V to 1.5 V in 0.5 V steps with the drain held at 0.1 V and source and "
    "body at 0 V, I want the drain current in amperes",
    {**FET_EXPECT, "study": {"kind": "dc", "contact": "gate", "start": 0.0, "stop": 1.5, "step": 0.5},
     "drain_offset": 0.1, "observables": ["absolute_terminal_current"]})
add("t9b", 9, "mosfet id-vds output curve at gate 1 V, sentaurus",
    FET + ", gate held at 1.0 V, sweep the drain from 0 V to 1.0 V in 0.25 V steps with source and body "
    "at 0 V, I want the drain current in amperes",
    {**FET_EXPECT, "study": {"kind": "dc", "contact": "drain", "start": 0.0, "stop": 1.0, "step": 0.25},
     "gate_offset": 1.0, "observables": ["absolute_terminal_current"]})

# Detailed variants: the same experiment, but the whole description is in the first message.
for _name in list(TESTS):
    _t = TESTS[_name]
    TESTS[_name + "d"] = {
        "experiment": _t["experiment"],
        "prompt": _t["prompt"] + ". Here is everything: " + _t["facts"],
        "facts": _t["facts"],
        "expect": _t["expect"],
    }