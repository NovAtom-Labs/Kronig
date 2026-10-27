(() => {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const q = (magnitude, unit) => ({magnitude_si: magnitude, si_unit: unit, dimensionality: "x"});
  const V = "kilogram * meter ** 2 / ampere / second ** 3";
  const spec = {
    name: "pn-test", dimension: 1,
    regions: [
      {id: "p", material: "silicon", x0: q(0, "meter"), x1: q(5e-7, "meter"), mesh_spacing: q(1e-8, "meter")},
      {id: "n", material: "silicon", x0: q(5e-7, "meter"), x1: q(1e-6, "meter"), mesh_spacing: null},
    ],
    interfaces: [{id: "j", left_region: "p", right_region: "n", fixed_charge_density: null}],
    profiles: [
      {kind: "constant", region: "p", species: "acceptor", value: q(1e23, "1 / meter ** 3")},
      {kind: "constant", region: "n", species: "donor", value: q(1e22, "1 / meter ** 3")},
    ],
    contacts: [
      {id: "anode", kind: "metal_work_function", location: "x_min", work_function: q(4.1 * 1.602176634e-19, "kilogram * meter ** 2 / second ** 2"), voltage_offset: q(0, V)},
      {id: "cathode", kind: "ohmic", location: "x_max", voltage_offset: q(0.1, V)},
    ],
    physics: {equations: ["poisson"], models: ["srh", "slotboom_bgn"], temperature: q(300, "kelvin")},
    study: {kind: "dc", contact: "anode", start: q(-1, V), stop: q(0.6, V), step: q(0.2, V), strategy: "fixed"},
    observables: ["potential", "electron_quasi_fermi_level"],
    display_units: {potential: "V"},
    solver: {relative_error: 1e-6, maximum_iterations: 80},
  };
  const doc = {
    spec, backend: "sentaurus", plan_digest: "a".repeat(64), warnings: ["mesh is coarse"], original_request: null,
    scientific_input_ledger: [
      {path: "regions.0.id", value: "p", authority: "researcher_owned", status: "resolved"},
      {path: "solver.relative_error", value: 1e-6, authority: "platform_reviewed_default", status: "resolved"},
    ],
  };
  const P = AgentKronigPlanView;
  const model = P.buildModel(P.documentFrom(doc));

  const count = (value) => {
    if (value === null || typeof value !== "object" || "magnitude_si" in value) return 1;
    const items = Array.isArray(value) ? value : Object.values(value);
    return items.length ? items.reduce((sum, item) => sum + count(item), 0) : 1;
  };
  assert(model.allFields.length === count(spec), `every spec field is listed (${model.allFields.length} of ${count(spec)})`);
  assert(model.ledger.length === 2, "every ledger row is kept");
  assert(model.warnings.length === 1 && model.warnings[0] === "mesh is coarse", "warnings are kept");
  assert(model.request === null, "an absent request is not invented");

  // The geometry block carries raw objects only as drawing data; every other block is shown text.
  const shown = model.sections.map((s) => ({...s, blocks: s.blocks.filter((b) => b.type !== "geometry")}));
  const text = JSON.stringify(shown, (key, value) => (key === "exact" ? undefined : value));
  assert(!/kilogram|ampere|meter \*\*/.test(text), "no raw SI unit strings in the designed sections");
  assert(text.includes("-1 V") && text.includes("0.6 V") && text.includes("0.2 V"), "voltages are shown in volts");
  assert(text.includes("1e17 cm⁻³") && text.includes("1e16 cm⁻³"), "concentrations are shown per cm3");
  assert(text.includes("4.1 eV"), "work function is shown in eV");
  assert(text.includes("0 nm to 500 nm"), "extents are shown in nanometres");
  assert(text.includes("300 K"), "temperature is shown in kelvin");
  assert(text.includes("Slotboom band-gap narrowing") && text.includes("Electron quasi fermi level"), "ids are made readable");
  assert(P.quantity(q(5e-7, "meter")).exact === "exact: 5e-7 meter", "the exact value stays available");
  assert(P.cell(null).empty === true, "an unset value is marked, not hidden");
  assert(model.kpis.some((item) => item.label === "Sweep" && item.value.includes("-1 V → 0.6 V")), "the sweep summary reads naturally");
  assert(model.sections.map((s) => s.id).join() === "structure,doping,contacts,study,physics,outputs,solver", "sections appear in reading order");
})();