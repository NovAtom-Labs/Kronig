"use strict";

(() => {
  const SVG_NS = "http://www.w3.org/2000/svg";

  function normalizedPath(path) {
    return String(path || "").replaceAll("\\", "/").replace(/^\.\//, "");
  }

  function isCanonicalResultPath(path) {
    const parts = normalizedPath(path).split("/").filter(Boolean);
    return parts.length >= 3
      && parts.at(-2) === "results"
      && parts.at(-1) === "canonical.json";
  }

  function findCanonicalResultPath(changeSet) {
    const supported = new Set(["created", "modified", "renamed"]);
    const match = (changeSet?.files || []).find(
      (file) => supported.has(file.operation) && isCanonicalResultPath(file.path),
    );
    return match ? normalizedPath(match.path) : null;
  }

  function finiteValues(values) {
    return (Array.isArray(values) ? values : [])
      .map(Number)
      .filter((value) => Number.isFinite(value));
  }

  function fieldOptions(payload) {
    return Object.entries(payload?.result?.fields || {}).flatMap(([name, series]) => {
      const positions = Array.isArray(series?.positions_m) ? series.positions_m.map(Number) : [];
      const values = Array.isArray(series?.values) ? series.values.map(Number) : [];
      if (
        positions.length < 2
        || positions.length !== values.length
        || positions.some((value) => !Number.isFinite(value))
        || values.some((value) => !Number.isFinite(value))
      ) return [];
      return [{name, positions, values, unit: String(series.unit || "")}];
    });
  }

  function summarize(payload) {
    const fields = payload?.result?.fields || {};
    const potential = finiteValues(fields.potential?.values);
    const electricField = finiteValues(fields.electric_field?.values);
    const currents = (payload?.result?.bias_points || []).flatMap(
      (point) => finiteValues(Object.values(point.terminal_currents_a_per_m2 || {})),
    );
    const checks = Array.isArray(payload?.validation?.checks)
      ? payload.validation.checks
      : [];
    return {
      potentialRange: potential.length
        ? Math.max(...potential) - Math.min(...potential)
        : null,
      peakElectricField: electricField.length
        ? Math.max(...electricField.map(Math.abs))
        : null,
      maximumTerminalCurrent: currents.length
        ? Math.max(...currents.map(Math.abs))
        : null,
      operatingPointCount: (payload?.result?.bias_points || []).length,
      fieldCount: Object.keys(fields).length,
      validationPassed: checks.filter((check) => check.status === "passed").length,
      validationTotal: checks.length,
    };
  }

  function label(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replaceAll("-", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function formatNumber(value, digits = 5) {
    if (value === null || value === undefined || value === "") return "Unavailable";
    const number = Number(value);
    if (!Number.isFinite(number)) return "Unavailable";
    const absolute = Math.abs(number);
    if (absolute >= 1e5 || (absolute > 0 && absolute < 1e-3)) {
      return number.toExponential(3).replace("e+", "e");
    }
    return Number(number.toPrecision(digits)).toString();
  }

  function positionLabel(meters) {
    const absolute = Math.abs(meters);
    if (absolute >= 1e-3) return `${formatNumber(meters * 1e3)} mm`;
    if (absolute >= 1e-6) return `${formatNumber(meters * 1e6)} µm`;
    if (absolute >= 1e-9) return `${formatNumber(meters * 1e9)} nm`;
    return `${formatNumber(meters)} m`;
  }

  function element(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function svgNode(name, attributes = {}, text = "") {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text) node.textContent = text;
    return node;
  }

  function badge(text, kind = "") {
    return element("span", `result-badge${kind ? ` is-${kind}` : ""}`, text);
  }

  function metricCard(name, value, unit = "") {
    const card = element("article", "result-metric");
    card.append(element("span", "result-metric-label", name));
    const row = element("div", "result-metric-value");
    row.append(element("strong", "", value));
    if (unit) row.append(element("small", "", unit));
    card.append(row);
    return card;
  }

  function renderStructure(payload) {
    const section = element("section", "result-section result-structure");
    const heading = element("div", "result-section-heading");
    heading.append(element("h2", "", "Structure"));
    heading.append(element("span", "", "ExperimentSpec"));
    section.append(heading);
    const strip = element("div", "result-region-strip");
    const profiles = payload.experiment?.profiles || [];
    for (const region of payload.experiment?.regions || []) {
      const item = element("article", "result-region");
      const profile = profiles.find((entry) => entry.region === region.id);
      const start = Number(region.x0?.magnitude_si);
      const end = Number(region.x1?.magnitude_si);
      item.append(element("strong", "", region.id));
      item.append(element("span", "", label(region.material)));
      item.append(element(
        "small",
        "",
        Number.isFinite(start) && Number.isFinite(end)
          ? `${positionLabel(start)} to ${positionLabel(end)}`
          : "Extent unavailable",
      ));
      item.append(element(
        "small",
        "",
        profile
          ? `${label(profile.species)} · ${formatNumber(Number(profile.value?.magnitude_si) / 1e6)} cm⁻³`
          : "No configured profile",
      ));
      strip.append(item);
    }
    if (!strip.children.length) strip.append(element("p", "result-empty", "No region geometry is available."));
    section.append(strip);
    return section;
  }

  function renderMetrics(payload) {
    const values = summarize(payload);
    const grid = element("section", "result-metrics");
    grid.append(
      metricCard("Potential range", formatNumber(values.potentialRange), values.potentialRange === null ? "" : "V"),
      metricCard("Peak electric field", formatNumber(values.peakElectricField), values.peakElectricField === null ? "" : "V/m"),
      metricCard("Maximum terminal current", formatNumber(values.maximumTerminalCurrent), values.maximumTerminalCurrent === null ? "" : "A/m²"),
      metricCard("Validation", `${values.validationPassed} / ${values.validationTotal}`, "passed"),
    );
    return grid;
  }

  function drawFieldChart(svg, tooltip, field, logarithmic = false) {
    svg.replaceChildren();
    tooltip.classList.add("hidden");
    const points = field.positions.map((position, index) => ({
      position,
      value: field.values[index],
    }));
    let useLog = logarithmic;
    if (useLog && points.some((point) => point.value <= 0)) useLog = false;
    const plotted = points.map((point) => ({
      ...point,
      plotted: useLog ? Math.log10(point.value) : point.value,
    }));
    const xMinimum = Math.min(...plotted.map((point) => point.position));
    const xMaximum = Math.max(...plotted.map((point) => point.position));
    let yMinimum = Math.min(...plotted.map((point) => point.plotted));
    let yMaximum = Math.max(...plotted.map((point) => point.plotted));
    if (xMinimum === xMaximum || yMinimum === yMaximum) {
      const padding = Math.abs(yMinimum || 1) * 0.05;
      yMinimum -= padding;
      yMaximum += padding;
    }
    const dimensions = {left: 76, top: 24, width: 782, height: 270};
    const x = (value) => dimensions.left + ((value - xMinimum) / (xMaximum - xMinimum)) * dimensions.width;
    const y = (value) => dimensions.top + (1 - (value - yMinimum) / (yMaximum - yMinimum)) * dimensions.height;
    for (let index = 0; index <= 5; index += 1) {
      const fraction = index / 5;
      const xCoordinate = dimensions.left + dimensions.width * fraction;
      const yCoordinate = dimensions.top + dimensions.height * (1 - fraction);
      svg.append(
        svgNode("line", {x1: xCoordinate, y1: dimensions.top, x2: xCoordinate, y2: dimensions.top + dimensions.height, class: "result-chart-grid"}),
        svgNode("line", {x1: dimensions.left, y1: yCoordinate, x2: dimensions.left + dimensions.width, y2: yCoordinate, class: "result-chart-grid"}),
        svgNode("text", {x: xCoordinate, y: dimensions.top + dimensions.height + 25, class: "result-chart-tick", "text-anchor": "middle"}, positionLabel(xMinimum + (xMaximum - xMinimum) * fraction)),
        svgNode("text", {x: dimensions.left - 12, y: yCoordinate + 4, class: "result-chart-tick", "text-anchor": "end"}, formatNumber(yMinimum + (yMaximum - yMinimum) * fraction)),
      );
    }
    svg.append(
      svgNode("line", {x1: dimensions.left, y1: dimensions.top + dimensions.height, x2: dimensions.left + dimensions.width, y2: dimensions.top + dimensions.height, class: "result-chart-axis"}),
      svgNode("line", {x1: dimensions.left, y1: dimensions.top, x2: dimensions.left, y2: dimensions.top + dimensions.height, class: "result-chart-axis"}),
      svgNode("path", {
        d: plotted.map((point, index) => `${index ? "L" : "M"} ${x(point.position)} ${y(point.plotted)}`).join(" "),
        class: "result-chart-line",
      }),
      svgNode("text", {x: 18, y: 160, transform: "rotate(-90 18 160)", class: "result-chart-label", "text-anchor": "middle"}, useLog ? `log₁₀(${field.unit})` : field.unit),
    );
    const crosshair = svgNode("line", {class: "result-chart-crosshair hidden"});
    const marker = svgNode("circle", {r: 4, class: "result-chart-marker hidden"});
    const hitArea = svgNode("rect", {x: dimensions.left, y: dimensions.top, width: dimensions.width, height: dimensions.height, class: "result-chart-hit"});
    svg.append(crosshair, marker, hitArea);
    hitArea.addEventListener("pointermove", (event) => {
      const bounds = svg.getBoundingClientRect();
      const pointerX = ((event.clientX - bounds.left) / bounds.width) * 880;
      const target = xMinimum + ((pointerX - dimensions.left) / dimensions.width) * (xMaximum - xMinimum);
      const nearest = plotted.reduce((best, point) => (
        Math.abs(point.position - target) < Math.abs(best.position - target) ? point : best
      ));
      const markerX = x(nearest.position);
      const markerY = y(nearest.plotted);
      crosshair.setAttribute("x1", markerX);
      crosshair.setAttribute("x2", markerX);
      crosshair.setAttribute("y1", dimensions.top);
      crosshair.setAttribute("y2", dimensions.top + dimensions.height);
      marker.setAttribute("cx", markerX);
      marker.setAttribute("cy", markerY);
      crosshair.classList.remove("hidden");
      marker.classList.remove("hidden");
      tooltip.textContent = `${positionLabel(nearest.position)} · ${formatNumber(nearest.value)} ${field.unit}`;
      tooltip.classList.remove("hidden");
    });
    hitArea.addEventListener("pointerleave", () => {
      crosshair.classList.add("hidden");
      marker.classList.add("hidden");
      tooltip.classList.add("hidden");
    });
    return useLog;
  }

  function renderFields(payload) {
    const fields = fieldOptions(payload);
    const section = element("section", "result-section result-fields");
    const heading = element("div", "result-section-heading");
    heading.append(element("h2", "", "Spatial fields"));
    heading.append(element("span", "", `${fields.length} graphable`));
    section.append(heading);
    if (!fields.length) {
      section.append(element("p", "result-empty", "No finite one-dimensional field series are available."));
      return section;
    }
    const controls = element("div", "result-field-controls");
    const select = element("select");
    select.setAttribute("aria-label", "Displayed result field");
    fields.forEach((field) => {
      const option = element("option", "", label(field.name));
      option.value = field.name;
      select.append(option);
    });
    const scale = element("select");
    scale.setAttribute("aria-label", "Result field scale");
    [["linear", "Linear scale"], ["log", "Logarithmic scale"]].forEach(([value, text]) => {
      const option = element("option", "", text);
      option.value = value;
      scale.append(option);
    });
    controls.append(select, scale);
    section.append(controls);
    const chart = element("div", "result-chart");
    const svg = svgNode("svg", {viewBox: "0 0 880 330", role: "img"});
    const tooltip = element("div", "result-chart-tooltip hidden");
    chart.append(svg, tooltip);
    section.append(chart);
    const redraw = () => {
      const field = fields.find((candidate) => candidate.name === select.value) || fields[0];
      const logAccepted = drawFieldChart(svg, tooltip, field, scale.value === "log");
      if (scale.value === "log" && !logAccepted) scale.value = "linear";
      svg.setAttribute("aria-label", `${label(field.name)} across device position`);
    };
    select.addEventListener("change", redraw);
    scale.addEventListener("change", redraw);
    redraw();
    return section;
  }

  function renderOperatingPoints(payload) {
    const section = element("section", "result-section");
    const heading = element("div", "result-section-heading");
    const points = payload.result?.bias_points || [];
    heading.append(element("h2", "", "Operating points"));
    heading.append(element("span", "", String(points.length)));
    section.append(heading);
    if (!points.length) {
      section.append(element("p", "result-empty", "No operating points are available."));
      return section;
    }
    const wrap = element("div", "result-table-wrap");
    const table = element("table", "result-table");
    const head = table.createTHead();
    const header = head.insertRow();
    ["Bias", "Terminal", "Current density", "Converged"].forEach((name) => {
      header.append(element("th", "", name));
    });
    const body = table.createTBody();
    points.forEach((point) => {
      const currents = Object.entries(point.terminal_currents_a_per_m2 || {});
      (currents.length ? currents : [["Unavailable", null]]).forEach(([terminal, current]) => {
        const row = body.insertRow();
        [
          `${formatNumber(point.bias_v)} V`,
          label(terminal),
          current === null ? "Unavailable" : `${formatNumber(current)} A/m²`,
          point.converged ? "Yes" : "No",
        ].forEach((value) => row.append(element("td", "", value)));
      });
    });
    wrap.append(table);
    section.append(wrap);
    return section;
  }

  function renderValidation(payload) {
    const section = element("section", "result-section");
    const heading = element("div", "result-section-heading");
    heading.append(element("h2", "", "Validation"));
    heading.append(badge(label(payload.validation?.overall || "unavailable"), payload.validation?.overall || ""));
    section.append(heading);
    const list = element("div", "result-validation-list");
    for (const check of payload.validation?.checks || []) {
      const row = element("article", `result-validation is-${check.status}`);
      const mark = element("span", "result-validation-mark", check.status === "passed" ? "✓" : check.status === "failed" ? "×" : "!");
      const copy = element("div");
      copy.append(element("strong", "", check.message || label(check.id)));
      const evidence = [label(check.level), label(check.evidence_origin)];
      if (check.measured_value !== null && check.measured_value !== undefined) evidence.push(`measured ${formatNumber(check.measured_value)}`);
      if (check.limit !== null && check.limit !== undefined) evidence.push(`limit ${check.limit}`);
      copy.append(element("small", "", evidence.join(" · ")));
      row.append(mark, copy, badge(label(check.status), check.status));
      list.append(row);
    }
    if (!list.children.length) list.append(element("p", "result-empty", "No validation evidence is available."));
    section.append(list);
    return section;
  }

  function renderProvenance(payload) {
    const section = element("section", "result-section");
    const heading = element("div", "result-section-heading");
    heading.append(element("h2", "", "Provenance"));
    heading.append(element("span", "", `${Object.keys(payload.manifest?.artifacts || {}).length} artifacts`));
    section.append(heading);
    const grid = element("dl", "result-provenance");
    const rows = [
      ["Run ID", payload.manifest?.run_id],
      ["Backend", payload.manifest?.backend],
      ["Simulator", payload.manifest?.simulator_version || "Unavailable"],
      ["Compiler", payload.manifest?.compiler_version],
      ["Input digest", payload.manifest?.input_digest],
      ["Runtime digest", payload.manifest?.runtime_digest],
    ];
    rows.forEach(([name, value]) => {
      const item = element("div");
      item.append(element("dt", "", name), element("dd", "", String(value || "Unavailable")));
      grid.append(item);
    });
    section.append(grid);
    return section;
  }

  function render(root, payload) {
    root.replaceChildren();
    const workbench = element("article", "results-workbench");
    const header = element("header", "results-workbench-header");
    const identity = element("div");
    identity.append(element("span", "result-eyebrow", "Canonical result"));
    identity.append(element("h1", "", payload.experiment?.name || payload.manifest?.run_id || "Simulation result"));
    identity.append(element(
      "p",
      "",
      `${label(payload.experiment?.study?.kind || "study")} · ${payload.result?.bias_points?.length || 0} operating point${payload.result?.bias_points?.length === 1 ? "" : "s"}`,
    ));
    const badges = element("div", "result-badges");
    badges.append(
      badge(label(payload.validation?.overall || "unavailable"), payload.validation?.overall || ""),
      badge(`backend: ${payload.result?.backend || "unavailable"}`),
      badge(`schema: ${payload.result?.schema_version || "unavailable"}`),
    );
    identity.append(badges);
    header.append(identity);
    workbench.append(
      header,
      renderStructure(payload),
      renderMetrics(payload),
      renderFields(payload),
    );
    const lower = element("div", "result-lower-grid");
    lower.append(renderOperatingPoints(payload), renderValidation(payload));
    workbench.append(lower, renderProvenance(payload));
    root.append(workbench);
    return workbench;
  }

  globalThis.AgentKronigResults = {
    fieldOptions,
    findCanonicalResultPath,
    formatNumber,
    isCanonicalResultPath,
    render,
    summarize,
  };
})();
