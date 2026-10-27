"use strict";

// Presentation of a prepared experiment plan. It shows exactly the data of the approved plan
// (spec, scientific input ledger, warnings, digests): friendly units for display, the exact SI
// value in a tooltip, and a complete field list so that nothing can be left out.
(() => {
  const SI = {
    volt: "kilogram * meter ** 2 / ampere / second ** 3",
    energy: "kilogram * meter ** 2 / second ** 2",
    concentration: "1 / meter ** 3",
  };
  const ELEMENTARY_CHARGE = 1.602176634e-19;
  const WORDS = {
    srh: "SRH", auger: "Auger", dc: "DC", ac: "AC", dc_points: "DC points", poisson: "Poisson",
    bgn: "BGN", pn: "PN", mos: "MOS", ohmic: "Ohmic", x_min: "x min", x_max: "x max",
    y_min: "y min", y_max: "y max", si: "Si", fermi: "Fermi", boltzmann: "Boltzmann",
    slotboom_bgn: "Slotboom band-gap narrowing", klaassen_mobility: "Klaassen mobility",
  };
  const AUTHORITY = {
    researcher_owned: {label: "Researcher", tone: "researcher"},
    evidence_backed_expert_suggestion: {label: "Expert suggestion", tone: "expert"},
    platform_reviewed_default: {label: "Platform default", tone: "default"},
    deterministically_derived: {label: "Derived", tone: "derived"},
  };

  function isQuantity(value) {
    return value !== null && typeof value === "object" && "magnitude_si" in value && "si_unit" in value;
  }

  function number(value) {
    if (!Number.isFinite(value)) return String(value);
    if (value === 0) return "0";
    const magnitude = Math.abs(value);
    if (magnitude >= 1e5 || magnitude < 1e-3) {
      return value.toExponential(3).replace(/\.?0+e/, "e").replace("e+", "e");
    }
    return String(Number(value.toPrecision(5)));
  }

  function lengthText(meters) {
    const magnitude = Math.abs(meters);
    if (magnitude >= 1e-3) return `${number(meters * 1e3)} mm`;
    if (magnitude >= 1e-6) return `${number(meters * 1e6)} µm`;
    if (magnitude >= 1e-9 || meters === 0) return `${number(meters * 1e9)} nm`;
    return `${number(meters * 1e12)} pm`;
  }

  function timeText(seconds) {
    const magnitude = Math.abs(seconds);
    if (magnitude >= 1 || seconds === 0) return `${number(seconds)} s`;
    if (magnitude >= 1e-3) return `${number(seconds * 1e3)} ms`;
    if (magnitude >= 1e-6) return `${number(seconds * 1e6)} µs`;
    return `${number(seconds * 1e9)} ns`;
  }

  // Display text for one quantity, plus its exact value for the tooltip.
  function quantity(value) {
    const meters = value.magnitude_si;
    const exact = `exact: ${value.magnitude_si} ${value.si_unit}`;
    let text;
    switch (value.si_unit) {
      case "meter": text = lengthText(meters); break;
      case "kelvin": text = `${number(meters)} K`; break;
      case SI.volt: text = `${number(meters)} V`; break;
      case SI.energy: text = `${number(meters / ELEMENTARY_CHARGE)} eV`; break;
      case SI.concentration: text = `${number(meters / 1e6)} cm⁻³`; break;
      case "second": text = timeText(meters); break;
      case "meter ** 2": text = `${number(meters * 1e12)} µm²`; break;
      case "ampere": text = `${number(meters)} A`; break;
      default: text = `${number(meters)} ${value.si_unit}`;
    }
    return {text, exact};
  }

  function pretty(name) {
    const key = String(name);
    if (WORDS[key]) return WORDS[key];
    const spaced = key.replaceAll("_", " ").replace(/\s+/g, " ").trim();
    return spaced ? spaced[0].toUpperCase() + spaced.slice(1) : key;
  }

  // Any value as text; objects and lists keep every member.
  function cell(value) {
    if (value === null || value === undefined) return {text: "—", exact: "not set", empty: true};
    if (isQuantity(value)) return quantity(value);
    if (typeof value === "number") return {text: number(value), exact: `exact: ${value}`};
    if (typeof value === "boolean") return {text: value ? "yes" : "no"};
    if (typeof value === "string") return {text: value, raw: true};
    if (Array.isArray(value)) {
      const parts = value.map(cell);
      return {text: parts.map((part) => part.text).join(", ") || "none", exact: parts.map((part) => part.exact || part.text).join(", ")};
    }
    const parts = Object.entries(value).map(([key, item]) => `${pretty(key)}: ${cell(item).text}`);
    return {text: parts.join(" · ") || "none"};
  }

  function leaves(value, prefix = "", rows = []) {
    if (value === null || value === undefined || typeof value !== "object" || isQuantity(value)) {
      rows.push({path: prefix, ...cell(value)});
    } else if (Array.isArray(value)) {
      if (!value.length) rows.push({path: prefix, text: "none", empty: true});
      value.forEach((item, index) => leaves(item, `${prefix}.${index}`, rows));
    } else {
      const entries = Object.entries(value);
      if (!entries.length) rows.push({path: prefix, text: "none", empty: true});
      entries.forEach(([key, item]) => leaves(item, prefix ? `${prefix}.${key}` : key, rows));
    }
    return rows;
  }

  function present(object, keys) {
    return keys.filter((key) => object[key] !== null && object[key] !== undefined);
  }

  function kv(object, keys) {
    return (keys || Object.keys(object)).filter((key) => object[key] !== undefined).map((key) => [pretty(key), cell(object[key]), key]);
  }

  function extent(region, lo, hi) {
    const a = region[lo];
    const b = region[hi];
    return isQuantity(a) && isQuantity(b) ? `${quantity(a).text} to ${quantity(b).text}` : null;
  }

  function meshText(region) {
    const parts = [];
    if (region.mesh_spacing) parts.push(`spacing ${cell(region.mesh_spacing).text}`);
    if (region.minimum_mesh_spacing) parts.push(`min ${cell(region.minimum_mesh_spacing).text}`);
    if (region.maximum_mesh_spacing) parts.push(`max ${cell(region.maximum_mesh_spacing).text}`);
    return parts.join(" · ") || "automatic";
  }

  function structureSection(spec) {
    const regions = spec.regions || [];
    const twoD = regions.some((region) => region.y0 || region.y1);
    const blocks = [];
    if (regions.length) blocks.push({type: "geometry", regions, contacts: spec.contacts || [], profiles: spec.profiles || [], twoD});
    blocks.push({
      type: "table",
      title: "Regions",
      columns: ["Region", "Material", twoD ? "Depth (x)" : "Extent", ...(twoD ? ["Lateral (y)"] : []), "Mesh"],
      rows: regions.map((region) => [
        {text: region.id, strong: true},
        {text: pretty(region.material)},
        {text: extent(region, "x0", "x1") || "—"},
        ...(twoD ? [{text: extent(region, "y0", "y1") || "—"}] : []),
        {text: meshText(region)},
      ]),
    });
    const extras = regions.filter((region) => region.relative_permittivity);
    if (extras.length) {
      blocks.push({type: "kv", title: "Permittivity", items: extras.map((region) => [region.id, cell(region.relative_permittivity)])});
    }
    if ((spec.interfaces || []).length) {
      blocks.push({
        type: "table",
        title: "Interfaces",
        columns: ["Interface", "Between", "Properties"],
        rows: spec.interfaces.map((item) => [
          {text: item.id, strong: true},
          {text: `${item.left_region} ↔ ${item.right_region}`},
          {text: present(item, Object.keys(item).filter((key) => !["id", "left_region", "right_region"].includes(key))).map((key) => `${pretty(key)}: ${cell(item[key]).text}`).join(" · ") || "continuity"},
        ]),
      });
    }
    return {id: "structure", title: "Structure", blocks};
  }

  function dopingSection(spec) {
    const profiles = spec.profiles || [];
    if (!profiles.length) return null;
    return {
      id: "doping", title: "Doping and charge",
      blocks: [{
        type: "table",
        columns: ["Region", "Species", "Profile", "Concentration", "Window"],
        rows: profiles.map((profile) => [
          {text: profile.region, strong: true},
          {text: pretty(profile.species)},
          {text: pretty(profile.kind)},
          cell(profile.value),
          {text: profile.kind === "box"
            ? `x ${extent(profile, "x0", "x1") || "—"} · y ${extent(profile, "y0", "y1") || "—"}`
            : "whole region"},
        ]),
      }],
    };
  }

  function contactsSection(spec) {
    const contacts = spec.contacts || [];
    return {
      id: "contacts", title: "Contacts",
      blocks: [{
        type: "table",
        columns: ["Contact", "Type", "Location", "Region", "Span", "Voltage offset"],
        rows: contacts.map((contact) => [
          {text: contact.id, strong: true},
          {text: contact.kind === "metal_work_function"
            ? `Metal · work function ${cell(contact.work_function).text}` : pretty(contact.kind)},
          {text: contact.location ? String(contact.location).replace("_", " ") : "—"},
          {text: contact.region || "—"},
          {text: contact.span ? cell(contact.span).text.replace(", ", " to ") : "full edge"},
          cell(contact.voltage_offset),
        ]),
      }, ...(contacts.some((c) => c.area || c.richardson_constant)
        ? [{type: "kv", title: "Contact details", items: contacts.flatMap((c) => ["area", "richardson_constant"].filter((k) => c[k]).map((k) => [`${c.id} · ${pretty(k)}`, cell(c[k])]))}]
        : [])],
    };
  }

  function studySection(spec) {
    const study = spec.study || {};
    const items = kv(study, Object.keys(study));
    const swept = items.find(([, , key]) => key === "contact");
    return {
      id: "study", title: "Study",
      blocks: [{type: "kv", items, lead: [pretty(study.kind || "study"), swept ? `swept contact ${study.contact}` : ""]}],
    };
  }

  function physicsSection(spec) {
    const physics = spec.physics || {};
    const blocks = [];
    blocks.push({type: "chips", title: "Equations", items: (physics.equations || []).map((id) => ({id, text: pretty(id)}))});
    blocks.push({type: "chips", title: "Models", items: (physics.models || []).map((id) => ({id, text: pretty(id)}))});
    const rest = Object.keys(physics).filter((key) => !["equations", "models"].includes(key));
    blocks.push({type: "kv", items: kv(physics, rest)});
    return {id: "physics", title: "Physics", blocks};
  }

  function outputsSection(spec) {
    const units = spec.display_units || {};
    const blocks = [{type: "chips", items: (spec.observables || []).map((id) => ({
      id, text: pretty(id), unit: units[id] || null,
    }))}];
    return {id: "outputs", title: "Requested outputs", blocks};
  }

  function samplingSection(spec) {
    const blocks = [];
    if (spec.profile_sampling) blocks.push({type: "kv", title: "Spatial profile sampling", items: kv(spec.profile_sampling)});
    if ((spec.profile_cuts || []).length) {
      blocks.push({type: "table", title: "Profile cuts", columns: ["Cut", "Position"], rows: spec.profile_cuts.map((cut) => [{text: cut.id, strong: true}, cell(cut.at)])});
    }
    if (spec.width) blocks.push({type: "kv", title: "Device width", items: [["Width", cell(spec.width)]]});
    return blocks.length ? {id: "sampling", title: "Profiles and geometry extras", blocks} : null;
  }

  function solverSection(spec) {
    const blocks = [];
    if (spec.solver) blocks.push({type: "kv", title: "Solver", items: kv(spec.solver)});
    if (spec.sign_convention) blocks.push({type: "kv", title: "Sign conventions", items: kv(spec.sign_convention)});
    return blocks.length ? {id: "solver", title: "Numerics and conventions", blocks} : null;
  }

  function buildModel(doc) {
    const spec = doc.spec || {};
    const regions = spec.regions || [];
    const study = spec.study || {};
    const total = regions.length && isQuantity(regions.at(-1).x1) && isQuantity(regions[0].x0)
      ? Math.max(...regions.map((r) => r.x1.magnitude_si)) - Math.min(...regions.map((r) => r.x0.magnitude_si))
      : null;
    const range = ["start", "stop", "step"].every((key) => isQuantity(study[key]))
      ? `${quantity(study.start).text} → ${quantity(study.stop).text}, step ${quantity(study.step).text}` : null;
    const kpis = [
      {label: "Study", value: pretty(study.kind || "—"), sub: study.contact ? `swept: ${study.contact}` : ""},
      ...(range ? [{label: "Sweep", value: range, sub: ""}] : []),
      {label: "Temperature", value: spec.physics?.temperature ? cell(spec.physics.temperature).text : "—", sub: ""},
      {label: "Structure", value: `${regions.length} region${regions.length === 1 ? "" : "s"}`, sub: total === null ? "" : `${lengthText(total)} deep`},
      {label: "Physics", value: `${(spec.physics?.models || []).length} models`, sub: `${(spec.physics?.equations || []).length} equations`},
      {label: "Outputs", value: String((spec.observables || []).length), sub: "requested"},
    ];
    const sections = [
      structureSection(spec), dopingSection(spec), contactsSection(spec), studySection(spec),
      physicsSection(spec), outputsSection(spec), samplingSection(spec), solverSection(spec),
    ].filter(Boolean);
    const ledger = (doc.ledger || []).map((row) => ({
      path: row.path, value: cell(row.value), authority: row.authority,
      authorityLabel: (AUTHORITY[row.authority] || {label: pretty(row.authority || "unknown")}).label,
      tone: (AUTHORITY[row.authority] || {tone: "default"}).tone,
      status: row.status, quantity: row.quantity, rationale: row.rationale,
      source: row.source ? `${row.source.kind || ""}${row.source.id ? ` · ${row.source.id}` : ""}` : "",
      requiredBy: row.required_by || [],
    }));
    const counts = {};
    ledger.forEach((row) => { counts[row.authority] = (counts[row.authority] || 0) + 1; });
    return {
      header: {title: spec.name || "Experiment plan", backend: doc.backend || null, study: pretty(study.kind || ""),
        dimension: spec.dimension ? `${spec.dimension}D` : null, digest: doc.plan_digest || null, capabilityDigest: doc.capability_digest || null},
      request: doc.original_request || null,
      kpis, sections, ledger, ledgerCounts: counts, authority: AUTHORITY,
      warnings: doc.warnings || [],
      allFields: leaves(spec, ""),
      metadata: spec.metadata ? kv(spec.metadata) : [],
    };
  }

  function documentFrom(data) {
    const prepared = data.prepared || {};
    return {
      spec: data.spec || prepared.spec || {},
      ledger: data.scientific_input_ledger || prepared.scientific_input_ledger || [],
      warnings: data.warnings || prepared.warnings || [],
      original_request: data.original_request ?? prepared.original_request ?? null,
      plan_digest: data.plan_digest || prepared.plan_digest || null,
      capability_digest: data.capability_digest || prepared.capability_digest || null,
      backend: data.backend || prepared.backend || null,
    };
  }

  // ---------- DOM ----------
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = text;
    return element;
  };

  function valueNode(item) {
    const span = node("span", `pv-value${item.empty ? " is-empty" : ""}`, item.text);
    if (item.exact) span.title = item.exact;
    return span;
  }

  function renderTable(block) {
    const wrap = node("div", "pv-table-wrap");
    if (block.title) wrap.append(node("h4", "pv-subtitle", block.title));
    const table = node("table", "pv-table");
    const head = node("tr");
    block.columns.forEach((name) => head.append(node("th", "", name)));
    const header = node("thead");
    header.append(head);
    table.append(header);
    const body = node("tbody");
    block.rows.forEach((row) => {
      const tr = node("tr");
      row.forEach((item) => {
        const td = node("td", item.strong ? "pv-strong" : "");
        td.append(valueNode(item));
        tr.append(td);
      });
      body.append(tr);
    });
    table.append(body);
    wrap.append(table);
    return wrap;
  }

  function renderKv(block) {
    const wrap = node("div", "pv-kv-wrap");
    if (block.title) wrap.append(node("h4", "pv-subtitle", block.title));
    const list = node("dl", "pv-kv");
    block.items.forEach(([label, item, key]) => {
      const term = node("dt", "", label);
      if (key) term.title = key;
      const description = node("dd");
      description.append(valueNode(item));
      list.append(term, description);
    });
    wrap.append(list);
    return wrap;
  }

  function renderChips(block) {
    const wrap = node("div", "pv-chip-wrap");
    if (block.title) wrap.append(node("h4", "pv-subtitle", block.title));
    const list = node("div", "pv-chips");
    block.items.forEach((item) => {
      const chip = node("span", "pv-chip", item.text);
      chip.title = item.id;
      if (item.unit) chip.append(node("small", "", item.unit));
      list.append(chip);
    });
    if (!block.items.length) list.append(node("span", "pv-value is-empty", "none"));
    wrap.append(list);
    return wrap;
  }

  const SVG = "http://www.w3.org/2000/svg";
  const svg = (name, attributes = {}, text) => {
    const element = document.createElementNS(SVG, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
    if (text !== undefined) element.textContent = text;
    return element;
  };

  function renderGeometry(block) {
    const wrap = node("div", "pv-geometry");
    const regions = block.regions.filter((region) => isQuantity(region.x0) && isQuantity(region.x1));
    if (!regions.length) return wrap;
    const palette = ["#7896c4", "#72a88d", "#bda36d", "#a08cc4", "#c67c80", "#6fb3b8"];
    if (!block.twoD) {
      const lo = Math.min(...regions.map((r) => r.x0.magnitude_si));
      const hi = Math.max(...regions.map((r) => r.x1.magnitude_si));
      const bar = node("div", "pv-stack");
      regions.forEach((region, index) => {
        const share = Math.max(((region.x1.magnitude_si - region.x0.magnitude_si) / (hi - lo)) * 100, 4);
        const piece = node("div", "pv-stack-region");
        piece.style.flexGrow = String(share);
        piece.style.setProperty("--pv-tone", palette[index % palette.length]);
        const doping = block.profiles.filter((profile) => profile.region === region.id && profile.kind !== "box");
        piece.append(node("strong", "", region.id), node("span", "", pretty(region.material)));
        doping.forEach((profile) => piece.append(node("small", "", `${pretty(profile.species)} ${cell(profile.value).text}`)));
        piece.title = `${region.id}: ${extent(region, "x0", "x1")}`;
        bar.append(piece);
      });
      wrap.append(bar);
      const axis = node("div", "pv-stack-axis");
      axis.append(node("span", "", lengthText(lo)), node("span", "", lengthText(hi)));
      wrap.append(axis);
      const marks = node("div", "pv-stack-contacts");
      block.contacts.forEach((contact) => {
        if (contact.location === "x_min" || contact.location === "x_max") {
          const tag = node("span", `pv-contact pv-contact-${contact.location}`, contact.id);
          tag.title = `${contact.id}: ${contact.kind} at ${contact.location}`;
          marks.append(tag);
        }
      });
      wrap.append(marks);
      return wrap;
    }
    // Two dimensions: depth x runs down the page, lateral y across it.
    const xs = regions.flatMap((r) => [r.x0.magnitude_si, r.x1.magnitude_si]);
    const ys = regions.flatMap((r) => [r.y0?.magnitude_si ?? 0, r.y1?.magnitude_si ?? 0]);
    const x0 = Math.min(...xs); const x1 = Math.max(...xs); const y0 = Math.min(...ys); const y1 = Math.max(...ys);
    const width = 520; const height = 220; const pad = 28;
    const sx = (value) => pad + ((value - y0) / (y1 - y0 || 1)) * (width - 2 * pad);
    const sy = (value) => pad + ((value - x0) / (x1 - x0 || 1)) * (height - 2 * pad);
    const drawing = svg("svg", {viewBox: `0 0 ${width} ${height}`, class: "pv-svg", role: "img", "aria-label": "Device cross-section"});
    regions.forEach((region, index) => {
      const ry0 = region.y0?.magnitude_si ?? y0; const ry1 = region.y1?.magnitude_si ?? y1;
      const rect = svg("rect", {x: sx(ry0), y: sy(region.x0.magnitude_si), width: sx(ry1) - sx(ry0), height: Math.max(sy(region.x1.magnitude_si) - sy(region.x0.magnitude_si), 3), fill: palette[index % palette.length], "fill-opacity": 0.28, stroke: palette[index % palette.length]});
      rect.append(svg("title", {}, `${region.id}: ${extent(region, "x0", "x1")} × ${extent(region, "y0", "y1") || ""}`));
      drawing.append(rect, svg("text", {x: sx(ry0) + 6, y: sy(region.x0.magnitude_si) + 14, class: "pv-svg-label"}, region.id));
    });
    block.profiles.filter((p) => p.kind === "box" && isQuantity(p.x0)).forEach((profile) => {
      const rect = svg("rect", {x: sx(profile.y0.magnitude_si), y: sy(profile.x0.magnitude_si), width: sx(profile.y1.magnitude_si) - sx(profile.y0.magnitude_si), height: sy(profile.x1.magnitude_si) - sy(profile.x0.magnitude_si), fill: "#c67c80", "fill-opacity": 0.35, stroke: "#c67c80", "stroke-dasharray": "3 2"});
      rect.append(svg("title", {}, `${pretty(profile.species)} ${cell(profile.value).text}`));
      drawing.append(rect);
    });
    block.contacts.forEach((contact) => {
      const region = regions.find((r) => r.id === contact.region) || regions[0];
      const ry0 = region.y0?.magnitude_si ?? y0; const ry1 = region.y1?.magnitude_si ?? y1;
      const span = contact.span && contact.span.length === 2 ? contact.span.map((q) => q.magnitude_si) : [ry0, ry1];
      let line = null;
      if (contact.location === "x_min") line = {x1: sx(span[0]), x2: sx(span[1]), y1: sy(region.x0.magnitude_si), y2: sy(region.x0.magnitude_si)};
      if (contact.location === "x_max") line = {x1: sx(span[0]), x2: sx(span[1]), y1: sy(region.x1.magnitude_si), y2: sy(region.x1.magnitude_si)};
      if (!line) return;
      drawing.append(svg("line", {...line, class: "pv-svg-contact"}), svg("text", {x: (line.x1 + line.x2) / 2, y: line.y1 + (contact.location === "x_min" ? -6 : 14), class: "pv-svg-contact-label", "text-anchor": "middle"}, contact.id));
    });
    wrap.append(drawing);
    return wrap;
  }

  function renderBlock(block) {
    if (block.type === "geometry") return renderGeometry(block);
    if (block.type === "table") return renderTable(block);
    if (block.type === "chips") return renderChips(block);
    const element = renderKv(block);
    if (block.lead) {
      const lead = node("p", "pv-lead");
      lead.append(node("strong", "", block.lead[0]));
      if (block.lead[1]) lead.append(node("span", "", ` · ${block.lead[1]}`));
      element.prepend(lead);
    }
    return element;
  }

  function renderLedger(model) {
    const details = node("details", "pv-ledger");
    details.append(node("summary", "", `Scientific inputs and authority · ${model.ledger.length} inputs`));
    const legend = node("div", "pv-legend");
    const filters = node("div", "pv-filters");
    const rows = [];
    const choose = (key) => {
      rows.forEach((row) => { row.hidden = key !== "all" && row.dataset.authority !== key; });
      filters.querySelectorAll("button").forEach((b) => b.classList.toggle("is-active", b.dataset.filter === key));
    };
    const add = (key, text) => {
      const button = node("button", "pv-filter", text);
      button.type = "button"; button.dataset.filter = key;
      button.addEventListener("click", () => choose(key));
      filters.append(button);
    };
    add("all", `All ${model.ledger.length}`);
    Object.entries(model.ledgerCounts).forEach(([key, count]) => add(key, `${(model.authority[key] || {label: pretty(key)}).label} ${count}`));
    legend.append(filters);
    details.append(legend);
    const table = node("table", "pv-table pv-ledger-table");
    const head = node("tr");
    ["Input", "Value", "Authority", "Status"].forEach((name) => head.append(node("th", "", name)));
    const header = node("thead");
    header.append(head);
    table.append(header);
    const body = node("tbody");
    model.ledger.forEach((entry) => {
      const tr = node("tr");
      tr.dataset.authority = entry.authority;
      const path = node("td", "pv-path", entry.path);
      path.title = [entry.quantity, entry.rationale, entry.source && `source: ${entry.source}`, entry.requiredBy.length && `required by: ${entry.requiredBy.join(", ")}`].filter(Boolean).join("\n");
      const value = node("td"); value.append(valueNode(entry.value));
      const authority = node("td"); authority.append(node("span", `pv-badge is-${entry.tone}`, entry.authorityLabel));
      tr.append(path, value, authority, node("td", "pv-status", entry.status || ""));
      rows.push(tr); body.append(tr);
    });
    table.append(body);
    details.append(table);
    return details;
  }

  function render(root, data) {
    const model = buildModel(documentFrom(data));
    root.replaceChildren();
    const view = node("article", "plan-view");
    const header = node("header", "pv-header");
    const identity = node("div");
    identity.append(node("span", "pv-eyebrow", "Experiment plan"), node("h1", "", model.header.title));
    const badges = node("div", "pv-badges");
    [model.header.backend && `backend: ${model.header.backend}`, model.header.study, model.header.dimension].filter(Boolean)
      .forEach((text) => badges.append(node("span", "pv-badge", text)));
    identity.append(badges);
    header.append(identity);
    if (model.header.digest) {
      const digest = node("button", "pv-digest", `plan ${model.header.digest.slice(0, 12)}…`);
      digest.type = "button";
      digest.title = `Plan digest ${model.header.digest}\nClick to copy`;
      digest.addEventListener("click", () => navigator.clipboard?.writeText(model.header.digest).catch(() => {}));
      header.append(digest);
    }
    view.append(header);
    if (model.request) {
      const quote = node("blockquote", "pv-request");
      quote.append(node("span", "pv-eyebrow", "Original request"), node("p", "", model.request));
      view.append(quote);
    }
    const kpis = node("div", "pv-kpis");
    model.kpis.forEach((item) => {
      const tile = node("div", "pv-kpi");
      tile.append(node("span", "pv-kpi-label", item.label), node("strong", "", item.value));
      if (item.sub) tile.append(node("small", "", item.sub));
      kpis.append(tile);
    });
    view.append(kpis);
    if (model.warnings.length) {
      const warnings = node("section", "pv-warnings");
      warnings.append(node("h3", "", `Warnings · ${model.warnings.length}`));
      const list = node("ul");
      model.warnings.forEach((warning) => list.append(node("li", "", typeof warning === "string" ? warning : cell(warning).text)));
      warnings.append(list);
      view.append(warnings);
    }
    model.sections.forEach((section) => {
      const card = node("section", "pv-card");
      card.id = `plan-${section.id}`;
      card.append(node("h2", "", section.title));
      section.blocks.forEach((block) => card.append(renderBlock(block)));
      view.append(card);
    });
    if (model.metadata.length) {
      const card = node("section", "pv-card");
      card.append(node("h2", "", "Provenance"), renderKv({items: model.metadata}));
      view.append(card);
    }
    const ledgerCard = node("section", "pv-card");
    ledgerCard.append(renderLedger(model));
    const all = node("details", "pv-ledger");
    all.append(node("summary", "", `Every specification field · ${model.allFields.length}`));
    const list = node("dl", "pv-kv pv-all");
    model.allFields.forEach((field) => {
      const term = node("dt", "pv-path", field.path);
      const description = node("dd"); description.append(valueNode(field));
      list.append(term, description);
    });
    all.append(list);
    ledgerCard.append(all);
    view.append(ledgerCard);
    const approval = node("footer", "pv-approval");
    approval.append(node("span", "", "Approval applies only to the exact plan digest."));
    if (model.header.digest) approval.append(node("code", "", model.header.digest));
    if (model.header.capabilityDigest) approval.append(node("small", "", `capability ${model.header.capabilityDigest}`));
    view.append(approval);
    root.append(view);
  }

  globalThis.AgentKronigPlanView = Object.freeze({buildModel, documentFrom, render, quantity, cell, pretty});
})();
