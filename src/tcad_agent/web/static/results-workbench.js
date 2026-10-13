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

  function datasetOptions(payload) {
    const axes = payload?.result?.axes || {};
    return Object.entries(payload?.result?.datasets || {}).flatMap(([name, dataset]) => {
      const axisIds = Array.isArray(dataset?.axes) ? dataset.axes : [];
      const shape = Array.isArray(dataset?.shape) ? dataset.shape.map(Number) : [];
      const values = Array.isArray(dataset?.values) ? dataset.values.map(Number) : [];
      if (
        axisIds.length !== shape.length
        || values.some((value) => !Number.isFinite(value))
        || shape.reduce((total, size) => total * size, 1) !== values.length
      ) return [];
      const resolvedAxes = axisIds.map((axisId) => axes[axisId]);
      if (resolvedAxes.some((axis, index) => (
        !axis
        || !Array.isArray(axis.values)
        || axis.values.length !== shape[index]
        || axis.values.some((value) => !Number.isFinite(Number(value)))
      ))) return [];
      const imaginary = dataset.imaginary_values;
      if (
        imaginary !== null
        && imaginary !== undefined
        && (!Array.isArray(imaginary)
          || imaginary.length !== values.length
          || imaginary.some((value) => !Number.isFinite(Number(value))))
      ) return [];
      const validity = dataset.validity;
      if (
        validity !== null
        && validity !== undefined
        && (!Array.isArray(validity) || validity.length !== values.length)
      ) return [];
      const kinds = resolvedAxes.map((axis) => String(axis.kind || "index"));
      let plotKind = "table";
      if (axisIds.length === 0) plotKind = "metric";
      else if (imaginary && axisIds.length === 1) plotKind = "complex_response";
      else if (axisIds.length === 1) plotKind = "curve";
      else if (axisIds.length === 2 && kinds.includes("position")) plotKind = "profile_family";
      else if (axisIds.length === 2 && shape.includes(1)) plotKind = "curve_family";
      else if (axisIds.length === 2) plotKind = "heatmap";
      return [{
        name,
        id: String(dataset.id || name),
        label: String(dataset.label || label(name)),
        unit: String(dataset.unit || "1"),
        axes: resolvedAxes.map((axis) => ({
          ...axis,
          values: axis.values.map(Number),
        })),
        shape,
        values,
        imaginaryValues: imaginary ? imaginary.map(Number) : null,
        validity: validity ? validity.map(Boolean) : null,
        centering: String(dataset.centering || "node"),
        source: String(dataset.source || "simulator"),
        plotKind,
      }];
    });
  }

  function comparisonDatasetOptions(payloads) {
    return (Array.isArray(payloads) ? payloads : []).flatMap((payload, runIndex) => {
      const runLabel = String(payload?.bundle_path || payload?.manifest?.run_id || `run ${runIndex + 1}`);
      return datasetOptions(payload).map((dataset) => ({
        ...dataset,
        id: `${runIndex}:${runLabel}:${dataset.id}`,
        name: `${runIndex}:${runLabel}:${dataset.name}`,
        label: `${dataset.label} · ${runLabel}`,
        runLabel,
        runIndex,
        canonicalDatasetId: dataset.id,
        canonicalDatasetName: dataset.name,
      }));
    });
  }

  function compatibleOverlayOptions(primary, datasets) {
    if (!primary) return [];
    const axisSignature = JSON.stringify(
      primary.axes.map((axis) => ({id: axis.id, values: axis.values})),
    );
    return datasets.filter((candidate) => (
      candidate.id !== primary.id
      && candidate.unit === primary.unit
      && JSON.stringify(candidate.shape) === JSON.stringify(primary.shape)
      && JSON.stringify(candidate.axes.map((axis) => ({id: axis.id, values: axis.values})))
        === axisSignature
      && candidate.plotKind === primary.plotKind
    ));
  }

  function comparisonCsv(primarySeries, primaryDataset, overlaySeries, overlayDataset) {
    const cell = (value) => {
      const text = String(value ?? "");
      return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
    };
    const headers = [
      `${primarySeries.axis.label} (${primarySeries.axis.unit})`,
      `${primaryDataset.label} (${primarySeries.valueUnit || primaryDataset.unit})`,
    ];
    if (overlaySeries && overlayDataset) {
      headers.push(`${overlayDataset.label} (${overlaySeries.valueUnit || overlayDataset.unit})`);
    }
    const rows = primarySeries.axis.values.map((coordinate, index) => {
      const row = [coordinate, primarySeries.values[index]];
      if (overlaySeries && overlayDataset) row.push(overlaySeries.values[index]);
      return row;
    });
    return `${[headers, ...rows].map((row) => row.map(cell).join(",")).join("\n")}\n`;
  }

  function fieldOptions(payload) {
    const canonical = datasetOptions(payload).flatMap((dataset) => {
      if (dataset.shape.length !== 1 || dataset.axes[0]?.kind !== "position") return [];
      return [{
        name: dataset.name,
        positions: dataset.axes[0].values,
        values: dataset.values,
        validity: dataset.validity,
        unit: dataset.unit,
      }];
    });
    if (canonical.length) return canonical;
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

  function operatingPoints(payload) {
    const result = payload?.result || {};
    if (result.operating_points?.length) return result.operating_points.map((point) => ({
      ...point, converged: point.state === "converged",
    }));
    return result.bias_points || [];
  }

  function pointLabel(point, payload) {
    if (!point.coordinates) return `${formatNumber(point.bias_v)} V`;
    return Object.entries(point.coordinates).map(([kind, value]) => {
      const axis = Object.values(payload.result?.axes || {}).find((item) => item.kind === kind || item.id === kind);
      return `${axis?.label || label(kind)}: ${formatNumber(value)}${axis?.unit ? ` ${axis.unit}` : ""}`;
    }).join(" · ");
  }

  function sampleCounts(payload) {
    const records = new Map();
    const frequencies = new Set();
    datasetOptions(payload).filter((dataset) => dataset.axes.some((axis) => axis.kind === "frequency"))
      .forEach((dataset) => dataset.values.forEach((_value, flatIndex) => {
        let remainder = flatIndex;
        const coordinates = {};
        for (let index = dataset.shape.length - 1; index >= 0; index -= 1) {
          const axis = dataset.axes[index];
          const value = axis.values[remainder % dataset.shape[index]];
          remainder = Math.floor(remainder / dataset.shape[index]);
          if (axis.kind !== "position") coordinates[axis.id] = value;
          if (axis.kind === "frequency") frequencies.add(value);
        }
        const key = JSON.stringify(Object.entries(coordinates).sort(([a], [b]) => a.localeCompare(b)));
        const valid = !dataset.validity || dataset.validity[flatIndex];
        const previous = records.get(key);
        records.set(key, {coordinates, valid: Boolean(valid && (!previous || previous.valid))});
      }));
    return {
      operatingPoints: operatingPoints(payload).length,
      frequencies: frequencies.size,
      frequencySamples: records.size,
      validFrequencySamples: [...records.values()].filter((point) => point.valid).length,
      frequencyGrid: [...records.values()],
    };
  }

  function statusDimensions(payload) {
    const assessment = payload?.assessment;
    const checks = validationPresentation((payload?.validation?.checks || [])
      .filter((check) => !check.level || ["numerical", "physical"].includes(check.level)));
    const executionState = payload?.execution_state || payload?.manifest?.execution_state
      || payload?.manifest?.state || payload?.result?.status || "unknown";
    const executionPassed = assessment ? assessment.execution?.status === "passed" : executionState === "completed";
    const scientificStatus = assessment?.numerical?.status;
    const scientificState = scientificStatus
      ? scientificStatus === "passed" ? "passed" : scientificStatus === "not_applicable" ? "unavailable" : "needs_review"
      : !checks.applicable ? "unavailable" : checks.failed ? "needs_review" : "passed";
    const traces = payload?.traceability?.records;
    const outputStatus = assessment?.output_coverage?.status;
    const deliverableState = outputStatus
      ? outputStatus === "passed" ? "complete" : outputStatus === "not_applicable" ? "unavailable" : "incomplete"
      : payload?.deliverable_state || payload?.manifest?.deliverable_state
        || (Array.isArray(traces) && traces.length ? traces.every((item) => item.status === "satisfied") ? "complete" : "incomplete" : "unavailable");
    return {
      execution: {label: "Execution", state: executionPassed ? "completed" : executionState,
        tone: executionPassed ? "success" : "warning",
        detail: assessment?.execution?.message || (executionPassed ? "Canonical execution completed" : "Execution is incomplete")},
      scientific: {label: "Scientific validation", state: scientificState,
        tone: scientificState === "passed" ? "success" : scientificState === "unavailable" ? "neutral" : "warning",
        detail: assessment?.numerical?.message || checks.headline},
      deliverables: {label: "Requested outputs", state: deliverableState,
        tone: deliverableState === "complete" ? "success" : deliverableState === "unavailable" ? "neutral" : "warning",
        detail: assessment?.output_coverage?.message || (deliverableState === "complete" ? "Requested outputs delivered" : deliverableState === "unavailable" ? "Output coverage evidence unavailable" : "Requested outputs need review")},
    };
  }

  function validationEvidence(check) {
    const evidence = [check.level && label(check.level), check.evidence_origin && label(check.evidence_origin)].filter(Boolean);
    const quantity = (value) => `${typeof value === "number" ? formatNumber(value) : String(value)}${check.unit ? ` ${check.unit}` : ""}`;
    [["measured", check.measured_value], ["limit", check.limit],
      ["absolute tolerance", check.absolute_tolerance], ["scale", check.scale]]
      .forEach(([name, value]) => { if (value !== null && value !== undefined) evidence.push(`${name} ${quantity(value)}`); });
    if (check.relative_tolerance !== null && check.relative_tolerance !== undefined) evidence.push(`relative tolerance ${formatNumber(check.relative_tolerance)}`);
    if (check.applicability_reason) evidence.push(check.applicability_reason);
    return evidence.join(" · ");
  }

  function summarize(payload) {
    const fields = payload?.result?.fields || {};
    const datasets = payload?.result?.datasets || {};
    const potential = finiteValues(datasets.potential?.values || fields.potential?.values);
    const electricField = finiteValues(
      datasets.electric_field?.values || fields.electric_field?.values,
    );
    const currents = operatingPoints(payload).flatMap(
      (point) => finiteValues(Object.values(point.terminal_currents_a_per_m2 || {})),
    );
    const checks = Array.isArray(payload?.validation?.checks)
      ? payload.validation.checks
      : [];
    const validationPassed = checks.filter((check) => check.status === "passed").length;
    const validationFailed = checks.filter(
      (check) => !["passed", "not_applicable"].includes(check.status),
    ).length;
    const validationNotApplicable = checks.filter(
      (check) => check.status === "not_applicable",
    ).length;
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
      operatingPointCount: operatingPoints(payload).length,
      ...sampleCounts(payload),
      fieldCount: Object.keys(datasets).length || Object.keys(fields).length,
      validationPassed,
      validationApplicable: checks.length - validationNotApplicable,
      validationFailed,
      validationNotApplicable,
      validationTotal: checks.length,
    };
  }

  function validationGroups(checks) {
    const values = Array.isArray(checks) ? checks : [];
    return {
      actionable: values.filter((check) => !["passed", "not_applicable"].includes(check.status)),
      passed: values.filter((check) => check.status === "passed"),
      notApplicable: values.filter((check) => check.status === "not_applicable"),
    };
  }

  function validationPresentation(checks) {
    const groups = validationGroups(checks);
    const passed = groups.passed.length;
    const failed = groups.actionable.length;
    const notApplicable = groups.notApplicable.length;
    const applicable = passed + failed;
    let headline = "No applicable validation checks";
    if (applicable && !failed) headline = `All ${applicable} applicable checks passed`;
    else if (applicable) headline = `${passed} of ${applicable} applicable checks passed`;
    return {
      ...groups,
      applicable,
      failed,
      headline,
      notApplicableCount: notApplicable,
      passedCount: passed,
      summary: `${passed} passed · ${failed} failed · ${notApplicable} not applicable`,
      tone: failed ? "failed" : applicable ? "success" : "neutral",
    };
  }

  function availableSelection(current, values) {
    const options = Array.isArray(values) ? values.map(String) : [];
    const selected = String(current || "");
    if (options.includes(selected)) return selected;
    return options[0] || "";
  }

  function resultStatus(payload) {
    const execution = String(
      payload?.execution_state || payload?.manifest?.execution_state || payload?.manifest?.state || "unknown",
    );
    const validation = String(
      payload?.validation_state
      || payload?.manifest?.validation_state
      || payload?.validation?.overall
      || "unknown",
    );
    if (execution !== "completed") {
      return {
        title: "Execution did not complete",
        detail: "Canonical evidence is incomplete and must not be treated as a finished result.",
        tone: "danger",
      };
    }
    if (!["passed", "completed"].includes(validation)) {
      return {
        title: "Execution completed · validation needs review",
        detail: "The converged canonical data remains viewable, but scientific validation did not pass.",
        tone: "warning",
      };
    }
    return {
      title: "Execution and validation completed",
      detail: "The result is backed by the verified canonical bundle and its validation record.",
      tone: "success",
    };
  }

  function seriesForDataset(dataset, sliceIndex = 0, complexMode = "magnitude") {
    const chart = globalThis.AgentKronigScientificChart;
    if (!dataset || !dataset.axes?.length) return null;
    let values = dataset.values;
    if (dataset.imaginaryValues) {
      const response = chart?.complexResponse(dataset.values, dataset.imaginaryValues);
      if (complexMode === "phase") values = response?.phaseDegrees || [];
      else if (complexMode === "real") values = dataset.values;
      else if (complexMode === "imaginary") values = dataset.imaginaryValues;
      else values = response?.magnitude || [];
    }
    if (dataset.shape.length === 1) {
      return {
        axis: dataset.axes[0],
        values,
        validity: dataset.validity,
        valueUnit: complexMode === "phase" ? "°" : dataset.unit,
        label: dataset.label,
      };
    }
    if (dataset.shape.length !== 2) return null;
    const positionIndex = dataset.axes.some((axis) => axis.kind === "position")
      ? dataset.axes.findIndex((axis) => axis.kind === "position")
      : Math.max(0, dataset.shape.findIndex((size) => size > 1));
    const otherIndex = positionIndex === 0 ? 1 : 0;
    const boundedSlice = Math.min(
      dataset.shape[otherIndex] - 1,
      Math.max(0, Number(sliceIndex) || 0),
    );
    const profile = [];
    const validity = [];
    for (let position = 0; position < dataset.shape[positionIndex]; position += 1) {
      const flatIndex = positionIndex === 1
        ? boundedSlice * dataset.shape[1] + position
        : position * dataset.shape[1] + boundedSlice;
      profile.push(values[flatIndex]);
      validity.push(dataset.validity ? dataset.validity[flatIndex] : true);
    }
    return {
      axis: dataset.axes[positionIndex],
      values: profile,
      validity,
      valueUnit: complexMode === "phase" ? "°" : dataset.unit,
      label: dataset.label,
      sliceAxis: dataset.axes[otherIndex],
      sliceIndex: boundedSlice,
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

  function axisValueLabel(value, axis) {
    if (axis?.kind === "position") return positionLabel(value);
    return `${formatNumber(value)}${axis?.unit && axis.unit !== "1" ? ` ${axis.unit}` : ""}`;
  }

  function regionMarkers(payload) {
    return (payload?.experiment?.regions || []).slice(0, -1).flatMap((region) => {
      const value = Number(region.x1?.magnitude_si);
      return Number.isFinite(value) ? [{value, label: region.id, kind: "interface"}] : [];
    });
  }

  function structureMarkers(payload) {
    const regions = payload?.experiment?.regions || [];
    if (!regions.length) return [];
    const start = Number(regions[0]?.x0?.magnitude_si);
    const stop = Number(regions.at(-1)?.x1?.magnitude_si);
    const contacts = (payload?.experiment?.contacts || []).flatMap((contact) => {
      const value = contact.location === "x_min" ? start
        : contact.location === "x_max" ? stop : Number.NaN;
      return Number.isFinite(value)
        ? [{value, label: String(contact.id || contact.location), kind: "contact"}]
        : [];
    });
    return [...contacts, ...regionMarkers(payload)].sort((left, right) => left.value - right.value);
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

  function controlField(name, control) {
    const field = element("label", "result-control-field");
    field.append(element("span", "", name), control);
    return field;
  }

  function chartNavigation() {
    const root = element("div", "result-chart-navigation");
    const zoomIn = element("button", "result-chart-action", "Zoom in");
    const zoomOut = element("button", "result-chart-action", "Zoom out");
    const reset = element("button", "result-chart-action", "Reset view");
    const status = element("span", "result-chart-viewport", "Full range");
    [zoomIn, zoomOut, reset].forEach((button) => { button.type = "button"; });
    root.append(zoomIn, zoomOut, reset, status);
    return {root, zoomIn, zoomOut, reset, status};
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
    const contacts = element("div", "result-contact-labels");
    (payload.experiment?.contacts || []).forEach((contact) => {
      contacts.append(element("span", "", `${contact.id} · ${contact.location}`));
    });
    if (contacts.children.length) section.append(contacts);
    return section;
  }

  function renderMetrics(payload) {
    const values = summarize(payload);
    const grid = element("section", "result-metrics");
    grid.append(
      metricCard("Potential range", formatNumber(values.potentialRange), values.potentialRange === null ? "" : "V"),
      metricCard("Peak electric field", formatNumber(values.peakElectricField), values.peakElectricField === null ? "" : "V/m"),
      metricCard("Maximum terminal current", formatNumber(values.maximumTerminalCurrent), values.maximumTerminalCurrent === null ? "" : "A/m²"),
      metricCard(
        "Validation",
        `${values.validationPassed} passed`,
        `${values.validationFailed} failed · ${values.validationNotApplicable} not applicable`,
      ),
    );
    return grid;
  }

  function drawFieldChart(
    svg,
    tooltip,
    field,
    scaleMode = "linear",
    viewport = null,
    onViewportChange = null,
    markers = [],
    overlays = [],
  ) {
    svg.replaceChildren();
    tooltip.classList.add("hidden");
    const points = field.positions.map((position, index) => ({
      position,
      value: field.values[index],
      valid: field.validity ? Boolean(field.validity[index]) : true,
    }));
    let useLog = scaleMode === "log";
    const useSignedLog = scaleMode === "signed_log";
    if (useLog && points.some((point) => point.valid && point.value <= 0)) useLog = false;
    const effectiveScale = useLog ? "log" : useSignedLog ? "signed_log" : "linear";
    const chart = globalThis.AgentKronigScientificChart;
    const plotted = points.map((point) => ({
      ...point,
      plotted: chart.valueForScale(point.value, effectiveScale),
    }));
    const overlayPoints = overlays.flatMap((overlay) => overlay.positions.map((position, index) => {
      const value = overlay.values[index];
      return {
        position,
        value,
        valid: overlay.validity ? Boolean(overlay.validity[index]) : true,
        plotted: chart.valueForScale(value, effectiveScale),
      };
    }));
    const validPlotted = plotted.filter((point) => point.valid);
    const candidates = validPlotted.length ? validPlotted : plotted;
    const fullExtent = {
      minimum: Math.min(...candidates.map((point) => point.position)),
      maximum: Math.max(...candidates.map((point) => point.position)),
    };
    const currentViewport = globalThis.AgentKronigScientificChart?.clampViewport(
      viewport || fullExtent,
      fullExtent,
    ) || fullExtent;
    let xMinimum = currentViewport.minimum;
    let xMaximum = currentViewport.maximum;
    if (xMinimum === xMaximum) {
      const padding = Math.abs(xMinimum || 1) * 0.05;
      xMinimum -= padding;
      xMaximum += padding;
    }
    const withinViewport = candidates.filter(
      (point) => point.position >= xMinimum && point.position <= xMaximum,
    );
    const displayedPrimary = withinViewport.length ? withinViewport : candidates;
    const displayedOverlays = overlayPoints.filter(
      (point) => point.valid && point.position >= xMinimum && point.position <= xMaximum,
    );
    const displayed = [...displayedPrimary, ...displayedOverlays];
    let yMinimum = Math.min(...displayed.map((point) => point.plotted));
    let yMaximum = Math.max(...displayed.map((point) => point.plotted));
    if (yMinimum === yMaximum) {
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
        svgNode("text", {x: xCoordinate, y: dimensions.top + dimensions.height + 25, class: "result-chart-tick", "text-anchor": "middle"}, axisValueLabel(xMinimum + (xMaximum - xMinimum) * fraction, field.axis)),
        svgNode("text", {x: dimensions.left - 12, y: yCoordinate + 4, class: "result-chart-tick", "text-anchor": "end"}, formatNumber(chart.tickValueForScale(yMinimum + (yMaximum - yMinimum) * fraction, effectiveScale))),
      );
    }
    const segments = globalThis.AgentKronigScientificChart?.segmentSeries(
      plotted.map((point) => point.position),
      plotted.map((point) => point.plotted),
      plotted.map(
        (point) => point.valid && point.position >= xMinimum && point.position <= xMaximum,
      ),
    ) || [];
    svg.append(
      svgNode("line", {x1: dimensions.left, y1: dimensions.top + dimensions.height, x2: dimensions.left + dimensions.width, y2: dimensions.top + dimensions.height, class: "result-chart-axis"}),
      svgNode("line", {x1: dimensions.left, y1: dimensions.top, x2: dimensions.left, y2: dimensions.top + dimensions.height, class: "result-chart-axis"}),
      svgNode("text", {x: 18, y: 160, transform: "rotate(-90 18 160)", class: "result-chart-label", "text-anchor": "middle"}, useLog ? `log₁₀(${field.unit})` : useSignedLog ? `signed log₁₀(${field.unit})` : field.unit),
    );
    markers.filter((marker) => marker.value >= xMinimum && marker.value <= xMaximum).forEach(
      (marker) => svg.append(
        svgNode("line", {x1: x(marker.value), y1: dimensions.top, x2: x(marker.value), y2: dimensions.top + dimensions.height, class: marker.kind === "contact" ? "result-chart-contact" : "result-chart-interface"}),
        svgNode("text", {x: x(marker.value) + 4, y: dimensions.top + 12, class: "result-chart-tick"}, marker.label),
      ),
    );
    segments.forEach((segment) => svg.append(svgNode("path", {
      d: segment.map((point, index) => `${index ? "L" : "M"} ${x(point.x)} ${y(point.value)}`).join(" "),
      class: "result-chart-line",
    })));
    overlays.forEach((overlay) => {
      const transformed = overlay.values.map((value) => (
        useLog ? Math.log10(value)
          : useSignedLog ? Math.sign(value) * Math.log10(1 + Math.abs(value)) : value
      ));
      const overlaySegments = globalThis.AgentKronigScientificChart?.segmentSeries(
        overlay.positions,
        transformed,
        overlay.positions.map((position, index) => (
          (!overlay.validity || Boolean(overlay.validity[index]))
          && position >= xMinimum && position <= xMaximum
          && (!useLog || overlay.values[index] > 0)
        )),
      ) || [];
      overlaySegments.forEach((segment) => svg.append(svgNode("path", {
        d: segment.map((point, index) => `${index ? "L" : "M"} ${x(point.x)} ${y(point.value)}`).join(" "),
        class: "result-chart-line is-overlay",
      })));
    });
    const crosshair = svgNode("line", {class: "result-chart-crosshair hidden"});
    const marker = svgNode("circle", {r: 4, class: "result-chart-marker hidden"});
    const hitArea = svgNode("rect", {x: dimensions.left, y: dimensions.top, width: dimensions.width, height: dimensions.height, class: "result-chart-hit"});
    svg.append(crosshair, marker, hitArea);
    hitArea.addEventListener("pointermove", (event) => {
      const bounds = svg.getBoundingClientRect();
      const pointerX = ((event.clientX - bounds.left) / bounds.width) * 880;
      const target = xMinimum + ((pointerX - dimensions.left) / dimensions.width) * (xMaximum - xMinimum);
      const validPoints = plotted.filter(
        (point) => point.valid && point.position >= xMinimum && point.position <= xMaximum,
      );
      if (!validPoints.length) return;
      const nearest = validPoints.reduce((best, point) => (
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
      tooltip.textContent = `${axisValueLabel(nearest.position, field.axis)} · ${formatNumber(nearest.value)} ${field.unit}`;
      tooltip.classList.remove("hidden");
    });
    hitArea.addEventListener("pointerleave", () => {
      crosshair.classList.add("hidden");
      marker.classList.add("hidden");
      tooltip.classList.add("hidden");
    });
    hitArea.addEventListener("wheel", (event) => {
      if (!onViewportChange || fullExtent.minimum === fullExtent.maximum) return;
      event.preventDefault();
      const bounds = svg.getBoundingClientRect();
      const pointerX = ((event.clientX - bounds.left) / bounds.width) * 880;
      const center = xMinimum
        + ((pointerX - dimensions.left) / dimensions.width) * (xMaximum - xMinimum);
      const factor = event.deltaY < 0 ? 0.75 : 1.35;
      const next = globalThis.AgentKronigScientificChart.clampViewport(
        globalThis.AgentKronigScientificChart.zoomViewport(
          {minimum: xMinimum, maximum: xMaximum},
          center,
          factor,
        ),
        fullExtent,
      );
      onViewportChange(next);
    }, {passive: false});
    let dragStart = null;
    hitArea.addEventListener("pointerdown", (event) => {
      dragStart = event.clientX;
      hitArea.setPointerCapture?.(event.pointerId);
    });
    hitArea.addEventListener("pointerup", (event) => {
      if (!onViewportChange || dragStart === null) return;
      const delta = -(event.clientX - dragStart) / Math.max(svg.getBoundingClientRect().width, 1)
        * (xMaximum - xMinimum);
      dragStart = null;
      onViewportChange(globalThis.AgentKronigScientificChart.clampViewport(
        globalThis.AgentKronigScientificChart.panViewport(
          {minimum: xMinimum, maximum: xMaximum},
          delta,
        ),
        fullExtent,
      ));
    });
    hitArea.addEventListener("dblclick", () => onViewportChange?.(fullExtent));
    return {
      extent: fullExtent,
      logAccepted: !scaleMode || scaleMode !== "log" || useLog,
      viewport: currentViewport,
    };
  }

  function renderFields(payload, comparisonRuns = []) {
    const datasets = comparisonDatasetOptions([payload, ...comparisonRuns]).filter(
      (dataset) => ["curve", "complex_response", "profile_family", "curve_family", "heatmap"].includes(
        dataset.plotKind,
      ),
    );
    if (datasets.length) return renderDatasets(payload, datasets);
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
    [["linear", "Linear scale"], ["log", "Logarithmic scale"], ["signed_log", "Signed-log scale"]].forEach(([value, text]) => {
      const option = element("option", "", text);
      option.value = value;
      scale.append(option);
    });
    const navigation = chartNavigation();
    controls.append(controlField("Dataset", select), controlField("Scale", scale), navigation.root);
    section.append(controls);
    const chart = element("div", "result-chart");
    const svg = svgNode("svg", {viewBox: "0 0 880 330", role: "img"});
    const tooltip = element("div", "result-chart-tooltip hidden");
    chart.append(svg, tooltip);
    section.append(chart);
    let viewport = null;
    let chartState = null;
    const redraw = () => {
      const field = fields.find((candidate) => candidate.name === select.value) || fields[0];
      chartState = drawFieldChart(
        svg,
        tooltip,
        {...field, axis: {kind: "position", unit: "m"}},
        scale.value,
        viewport,
        (next) => {
          viewport = next;
          redraw();
        },
        structureMarkers(payload),
      );
      if (scale.value === "log" && !chartState.logAccepted) scale.value = "linear";
      navigation.status.textContent = viewport ? "Zoomed range" : "Full range";
      svg.setAttribute("aria-label", `${label(field.name)} across device position`);
    };
    select.addEventListener("change", () => {
      viewport = null;
      redraw();
    });
    scale.addEventListener("change", redraw);
    const navigate = (action) => {
      if (!chartState?.extent) return;
      viewport = globalThis.AgentKronigScientificChart.viewportForAction(
        viewport || chartState.viewport,
        chartState.extent,
        action,
      );
      if (action === "reset") viewport = null;
      redraw();
    };
    navigation.zoomIn.addEventListener("click", () => navigate("zoom_in"));
    navigation.zoomOut.addEventListener("click", () => navigate("zoom_out"));
    navigation.reset.addEventListener("click", () => navigate("reset"));
    redraw();
    return section;
  }

  function triggerDownload(name, content, type) {
    const link = document.createElement("a");
    link.download = name;
    link.href = URL.createObjectURL(new Blob([content], {type}));
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function renderHeatmap(svg, dataset) {
    svg.replaceChildren();
    const chart = globalThis.AgentKronigScientificChart;
    const cells = chart?.heatmapCells(
      dataset.axes[0].values,
      dataset.axes[1].values,
      dataset.values,
    ) || [];
    if (!cells.length) return;
    const values = cells.map((cell) => cell.value);
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const width = 760 / dataset.shape[0];
    const height = 260 / dataset.shape[1];
    cells.forEach((cell, index) => {
      const fraction = maximum === minimum ? 0.5 : (cell.value - minimum) / (maximum - minimum);
      const hue = 215 - 175 * fraction;
      svg.append(svgNode("rect", {
        x: 82 + Math.floor(index / dataset.shape[1]) * width,
        y: 22 + (dataset.shape[1] - 1 - index % dataset.shape[1]) * height,
        width: Math.max(width, 1),
        height: Math.max(height, 1),
        fill: `hsl(${hue} 48% ${35 + fraction * 20}%)`,
      }));
    });
    svg.append(
      svgNode("text", {x: 462, y: 315, class: "result-chart-label", "text-anchor": "middle"}, `${dataset.axes[0].label} (${dataset.axes[0].unit})`),
      svgNode("text", {x: 18, y: 152, transform: "rotate(-90 18 152)", class: "result-chart-label", "text-anchor": "middle"}, `${dataset.axes[1].label} (${dataset.axes[1].unit})`),
      svgNode("text", {x: 846, y: 16, class: "result-chart-tick", "text-anchor": "end"}, `${formatNumber(minimum)} to ${formatNumber(maximum)} ${dataset.unit}`),
    );
  }

  function renderDatasets(payload, datasets) {
    const section = element("section", "result-section result-fields");
    const heading = element("div", "result-section-heading");
    heading.append(element("h2", "", "Scientific datasets"));
    heading.append(element("span", "", `${datasets.length} graphable`));
    section.append(heading);
    const controls = element("div", "result-field-controls");
    const select = element("select");
    select.setAttribute("aria-label", "Displayed result dataset");
    datasets.forEach((dataset) => {
      const option = element("option", "", dataset.label);
      option.value = dataset.name;
      select.append(option);
    });
    const slice = element("select");
    slice.setAttribute("aria-label", "Displayed operating point");
    const mode = element("select");
    mode.setAttribute("aria-label", "Complex result view");
    [["magnitude", "Magnitude"], ["phase", "Phase"], ["real", "Real"], ["imaginary", "Imaginary"]].forEach(([value, text]) => {
      const option = element("option", "", text);
      option.value = value;
      mode.append(option);
    });
    const scale = element("select");
    scale.setAttribute("aria-label", "Result dataset scale");
    [["linear", "Linear scale"], ["log", "Logarithmic scale"], ["signed_log", "Signed-log scale"]].forEach(([value, text]) => {
      const option = element("option", "", text);
      option.value = value;
      scale.append(option);
    });
    const exportCsv = element("button", "result-export", "CSV");
    exportCsv.type = "button";
    const exportSvg = element("button", "result-export", "SVG");
    exportSvg.type = "button";
    const exportPng = element("button", "result-export", "PNG");
    exportPng.type = "button";
    const overlay = element("select");
    overlay.setAttribute("aria-label", "Compatible result overlay");
    const navigation = chartNavigation();
    const exportGroup = element("div", "result-export-group");
    exportGroup.append(exportCsv, exportSvg, exportPng);
    const datasetField = controlField("Dataset", select);
    const sliceField = controlField("Operating point", slice);
    const modeField = controlField("Complex view", mode);
    const scaleField = controlField("Scale", scale);
    const overlayField = controlField("Overlay", overlay);
    controls.append(
      datasetField,
      sliceField,
      modeField,
      scaleField,
      overlayField,
      navigation.root,
      exportGroup,
    );
    section.append(controls);
    const chartRoot = element("div", "result-chart");
    const svg = svgNode("svg", {viewBox: "0 0 880 330", role: "img"});
    const tooltip = element("div", "result-chart-tooltip hidden");
    chartRoot.append(svg, tooltip);
    section.append(chartRoot);

    const identity = element("p", "result-dataset-identity");
    section.append(identity);

    let viewport = null;
    let chartState = null;
    const redraw = () => {
      const dataset = datasets.find((candidate) => candidate.name === select.value) || datasets[0];
      identity.textContent = `${dataset.label} · ${dataset.unit}`;
      select.title = identity.textContent;
      if (overlay.dataset.primary !== dataset.id) {
        overlay.replaceChildren();
        const none = element("option", "", "No overlay");
        none.value = "";
        overlay.append(none);
        compatibleOverlayOptions(dataset, datasets).forEach((candidate) => {
          const option = element("option", "", candidate.label);
          option.value = candidate.id;
          overlay.append(option);
        });
        overlay.dataset.primary = dataset.id;
      }
      overlayField.classList.toggle("hidden", overlay.options.length <= 1);
      modeField.classList.toggle("hidden", !dataset.imaginaryValues);
      scaleField.classList.toggle("hidden", dataset.plotKind === "heatmap");
      const previousSlice = slice.value;
      slice.replaceChildren();
      if (["profile_family", "curve_family"].includes(dataset.plotKind)) {
        const positionIndex = dataset.axes.some((axis) => axis.kind === "position")
          ? dataset.axes.findIndex((axis) => axis.kind === "position")
          : Math.max(0, dataset.shape.findIndex((size) => size > 1));
        const sliceAxis = dataset.axes[positionIndex === 0 ? 1 : 0];
        const preferred = payload.result?.metadata?.profile_bias_values_v || [];
        sliceAxis.values.forEach((value, index) => {
          const requested = sliceAxis.kind === "bias" && preferred.some(bias=>Math.abs(bias-value)<1e-10);
          const option = element("option", "", `${sliceAxis.label}: ${formatNumber(value)} ${sliceAxis.unit}${requested ? " · requested profile" : ""}`);
          option.value = String(index);
          slice.append(option);
        });
        slice.value = availableSelection(
          previousSlice || String(Math.max(0, sliceAxis.values.findIndex(value=>preferred.some(bias=>Math.abs(bias-value)<1e-10)))),
          Array.from(slice.options).map((option) => option.value),
        );
        slice.title = slice.selectedOptions?.[0]?.textContent || "";
        sliceField.classList.remove("hidden");
      } else {
        sliceField.classList.add("hidden");
      }
      if (dataset.plotKind === "heatmap") {
        renderHeatmap(svg, dataset);
        chartState = null;
        navigation.root.classList.add("hidden");
      } else {
        navigation.root.classList.remove("hidden");
        const series = seriesForDataset(dataset, slice.value, mode.value);
        const field = {
          positions: series.axis.values,
          values: series.values,
          validity: series.validity,
          unit: series.valueUnit,
          axis: series.axis,
        };
        const overlayDataset = datasets.find((candidate) => candidate.id === overlay.value);
        const overlaySeries = overlayDataset
          ? seriesForDataset(overlayDataset, slice.value, mode.value)
          : null;
        chartState = drawFieldChart(
          svg,
          tooltip,
          field,
          scale.value,
          viewport,
          (next) => {
            viewport = next;
            redraw();
          },
          series.axis.kind === "position" ? structureMarkers(payload) : [],
          overlaySeries ? [{
            positions: overlaySeries.axis.values,
            values: overlaySeries.values,
            validity: overlaySeries.validity,
          }] : [],
        );
        if (scale.value === "log" && !chartState.logAccepted) scale.value = "linear";
      }
      navigation.status.textContent = viewport ? "Zoomed range" : "Full range";
      svg.setAttribute("aria-label", `${dataset.label} scientific plot`);
    };
    select.addEventListener("change", () => {
      viewport = null;
      redraw();
    });
    [slice, mode, scale, overlay].forEach((control) => control.addEventListener("change", redraw));
    const navigate = (action) => {
      if (!chartState?.extent) return;
      viewport = globalThis.AgentKronigScientificChart.viewportForAction(
        viewport || chartState.viewport,
        chartState.extent,
        action,
      );
      if (action === "reset") viewport = null;
      redraw();
    };
    navigation.zoomIn.addEventListener("click", () => navigate("zoom_in"));
    navigation.zoomOut.addEventListener("click", () => navigate("zoom_out"));
    navigation.reset.addEventListener("click", () => navigate("reset"));
    exportCsv.addEventListener("click", () => {
      const dataset = datasets.find((candidate) => candidate.name === select.value) || datasets[0];
      const series = seriesForDataset(dataset, slice.value, mode.value);
      if (!series) return;
      const overlayDataset = datasets.find((candidate) => candidate.id === overlay.value);
      const overlaySeries = overlayDataset
        ? seriesForDataset(overlayDataset, slice.value, mode.value)
        : null;
      const content = comparisonCsv(series, dataset, overlaySeries, overlayDataset);
      triggerDownload(`${dataset.id}.csv`, content, "text/csv;charset=utf-8");
    });
    exportSvg.addEventListener("click", () => {
      const dataset = datasets.find((candidate) => candidate.name === select.value) || datasets[0];
      const source = new XMLSerializer().serializeToString(svg);
      triggerDownload(`${dataset.id}.svg`, source, "image/svg+xml;charset=utf-8");
    });
    exportPng.addEventListener("click", () => {
      const dataset = datasets.find((candidate) => candidate.name === select.value) || datasets[0];
      const source = new XMLSerializer().serializeToString(svg);
      const image = new Image();
      const blobUrl = URL.createObjectURL(new Blob([source], {type: "image/svg+xml"}));
      image.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = 1760;
        canvas.height = 660;
        const context = canvas.getContext("2d");
        context?.drawImage(image, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(blobUrl);
        canvas.toBlob((blob) => {
          if (!blob) return;
          const pngUrl = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.download = `${dataset.id}.png`;
          link.href = pngUrl;
          link.click();
          URL.revokeObjectURL(pngUrl);
        }, "image/png");
      };
      image.src = blobUrl;
    });
    redraw();
    return section;
  }

  function renderOperatingPoints(payload) {
    const section = element("section", "result-section");
    const heading = element("div", "result-section-heading");
    const points = operatingPoints(payload);
    const counts = sampleCounts(payload);
    heading.append(element("h2", "", counts.frequencySamples ? "DC operating points" : "Operating points"));
    heading.append(element("span", "", String(points.length)));
    section.append(heading);
    if (!points.length) {
      section.append(element("p", "result-empty", "No operating points are available."));
      if (!counts.frequencySamples) return section;
    }
    const wrap = element("div", "result-table-wrap");
    const table = element("table", "result-table");
    const head = table.createTHead();
    const header = head.insertRow();
    ["Operating point", "Terminal", "Current density", "Converged"].forEach((name) => {
      header.append(element("th", "", name));
    });
    const body = table.createTBody();
    points.forEach((point) => {
      const currents = Object.entries(point.terminal_currents_a_per_m2 || {});
      (currents.length ? currents : [["Unavailable", null]]).forEach(([terminal, current]) => {
        const row = body.insertRow();
        [
          pointLabel(point, payload),
          terminal,
          current === null ? "Unavailable" : `${formatNumber(current)} A/m²`,
          point.converged ? "Yes" : "No",
        ].forEach((value) => row.append(element("td", "", value)));
      });
    });
    wrap.append(table);
    section.append(wrap);
    if (counts.frequencySamples) {
      const acHeading = element("div", "result-section-heading");
      acHeading.append(element("h2", "", "Small-signal sample grid"),
        element("span", "", `${counts.frequencySamples} AC samples · ${counts.validFrequencySamples} valid`));
      const acWrap = element("div", "result-table-wrap");
      const acTable = element("table", "result-table result-ac-grid");
      const acHeader = acTable.createTHead().insertRow();
      ["Sample coordinates", "Valid"].forEach((name) => acHeader.append(element("th", "", name)));
      const acBody = acTable.createTBody();
      counts.frequencyGrid.forEach((point) => {
        const row = acBody.insertRow();
        row.append(element("td", "", pointLabel(point, payload)), element("td", "", point.valid ? "Yes" : "No"));
      });
      acWrap.append(acTable);
      section.append(acHeading, acWrap);
    }
    return section;
  }

  function renderValidation(payload) {
    const section = element("section", "result-section");
    section.dataset.resultSection = "validation";
    const heading = element("div", "result-section-heading");
    heading.append(element("h2", "", "Validation"));
    heading.append(badge(label(payload.validation?.overall || "unavailable"), payload.validation?.overall || ""));
    section.append(heading);
    const presentation = validationPresentation(payload.validation?.checks || []);
    const summary = element("div", `result-validation-summary is-${presentation.tone}`);
    summary.append(
      element("strong", "", presentation.headline),
      element("span", "", presentation.summary),
    );
    section.append(summary);
    const rowForCheck = (check) => {
      const row = element("article", `result-validation is-${check.status}`);
      const mark = element("span", "result-validation-mark", check.status === "passed" ? "✓" : check.status === "not_applicable" ? "N/A" : check.status === "failed" ? "×" : "!");
      const copy = element("div");
      copy.append(element("strong", "", check.message || label(check.id)));
      copy.append(element("small", "", validationEvidence(check)));
      row.append(mark, copy, badge(label(check.status), check.status));
      return row;
    };
    const list = element("div", "result-validation-list");
    [...presentation.actionable, ...presentation.passed].forEach((check) => list.append(rowForCheck(check)));
    if (!list.children.length && !presentation.notApplicable.length) {
      list.append(element("p", "result-empty", "No validation evidence is available."));
    }
    section.append(list);
    if (presentation.notApplicable.length) {
      const deferred = element("details", "result-validation-na");
      const deferredHeading = element(
        "summary",
        "",
        `Checks not applicable to this experiment (${presentation.notApplicable.length})`,
      );
      const deferredList = element("div", "result-validation-list");
      presentation.notApplicable.forEach((check) => deferredList.append(rowForCheck(check)));
      deferred.append(deferredHeading, deferredList);
      section.append(deferred);
    }
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

  function renderInputLedger(payload) {
    const details = element("details", "result-section result-input-ledger");
    details.append(element("summary", "", "Reviewed inputs and authority"));
    details.append(element("p", "result-empty", "Authority identifies responsibility for reviewing the contract, not who originally typed a value. Source IDs identify recorded contract evidence; original prompt-level attribution is unavailable unless explicitly recorded."));
    const ledger = globalThis.AgentKronigAgentView?.inputLedger(payload.completeness?.records || []);
    if (!ledger?.length) {
      details.append(element("p", "result-empty", "Input authority records are unavailable for this bundle. Inspect the recorded experiment and input digest."));
      return details;
    }
    ledger.forEach((group) => {
      const section = element("section", "result-input-group");
      section.append(element("h3", "", group.label));
      const list = element("dl", "result-provenance");
      group.records.forEach((record) => {
        const row = element("div");
        const value = element("dd");
        value.append(element("strong", "", record.value), element("small", "", `${record.source} · ${record.status}`));
        if (record.derivation) value.append(element("small", "", record.derivation));
        if (record.digest) value.append(element("small", "", `Source digest: ${record.digest}`));
        if (record.rationale) value.append(element("small", "", record.rationale));
        row.append(element("dt", "", record.path), value);
        list.append(row);
      });
      section.append(list);
      details.append(section);
    });
    return details;
  }

  function renderRecovery(payload) {
    const section = element("section", "result-section result-recovery");
    const heading = element("div", "result-section-heading");
    heading.append(element("h2", "", "Numerical recovery"));
    section.append(heading, element("p", "result-empty", "Review a proposed numerical change before running a new experiment. The original bundle, physics, requested outputs, and scientific acceptance limits are preserved."));
    const labels = {
      refine_mesh: "Review finer mesh",
      increase_iteration_limit: "Review higher iteration limit",
      reduce_bias_step: "Review smaller continuation steps",
      stop_and_report: "Keep results and stop",
    };
    const actions = [...new Set([...(payload.recovery_actions || []), "stop_and_report"])]
      .filter((action) => Object.hasOwn(labels, action));
    const controls = element("div", "result-recovery-actions");
    actions.forEach((action) => {
      const button = element("button", "", labels[action]);
      button.type = "button";
      button.dataset.recoveryAction = action;
      button.addEventListener("click", () => {
        section.dispatchEvent(new CustomEvent("kronig:review-recovery", {bubbles: true, detail: {
          workspaceId: payload.workspace_id,
          bundleRunId: payload.saved_bundle_id || payload.manifest?.run_id,
          action,
        }}));
      });
      controls.append(button);
    });
    section.append(controls);
    return section;
  }

  function renderRecoveryComparison(comparison) {
    const section = element("details", "result-section result-recovery-comparison");
    section.append(element("summary", "", "Reviewed numerical recovery provenance"));
    const identity = element("dl", "result-provenance");
    [
      ["Original bundle", comparison.original_bundle_id],
      ["New bundle", comparison.new_bundle_id],
      ["Reviewed action", comparison.action],
      ["Original input digest", comparison.original_spec_digest],
      ["New input digest", comparison.candidate_spec_digest],
      ["Preserved physics digest", comparison.preserved_physics_digest],
    ].forEach(([name, value]) => {
      const row = element("div");
      row.append(element("dt", "", name), element("dd", "", String(value || "Unavailable")));
      identity.append(row);
    });
    const changes = element("table", "result-table result-recovery-changes");
    const header = changes.createTHead().insertRow();
    ["Numerical field", "Original value", "Reviewed value"].forEach((name) => header.append(element("th", "", name)));
    const body = changes.createTBody();
    (comparison.changes || []).forEach((change) => {
      const row = body.insertRow();
      [change.path, JSON.stringify(change.before), JSON.stringify(change.after)]
        .forEach((value) => row.append(element("td", "", value ?? "Unavailable")));
    });
    const wrap = element("div", "result-table-wrap");
    wrap.append(changes);
    const limits = element("dl", "result-provenance");
    (comparison.validation_limits || []).forEach((limit) => {
      const row = element("div");
      row.append(element("dt", "", limit.name), element("dd", "", formatNumber(limit.value)));
      limits.append(row);
    });
    section.append(identity, wrap,
      element("h3", "result-comparison-heading", "Unchanged scientific acceptance values"), limits);
    return section;
  }

  function render(root, payload, comparisonRuns = []) {
    root.replaceChildren();
    const workbench = element("article", "results-workbench");
    const header = element("header", "results-workbench-header");
    const identity = element("div");
    identity.append(element("span", "result-eyebrow", "Canonical result"));
    identity.append(element("h1", "", payload.experiment?.name || payload.manifest?.run_id || "Simulation result"));
    identity.append(element(
      "p",
      "",
      (() => {
        const counts = sampleCounts(payload);
        const dc = `${counts.operatingPoints} ${counts.frequencySamples ? "DC " : ""}operating point${counts.operatingPoints === 1 ? "" : "s"}`;
        const ac = counts.frequencySamples ? ` · ${counts.frequencySamples} AC samples · ${counts.validFrequencySamples} valid · ${counts.frequencies} frequencies` : "";
        return `${label(payload.experiment?.study?.kind || "study")} · ${dc}${ac}`;
      })(),
    ));
    const badges = element("div", "result-badges");
    badges.append(
      badge(label(payload.validation?.overall || "unavailable"), payload.validation?.overall || ""),
      badge(`backend: ${payload.result?.backend || "unavailable"}`),
      badge(`schema: ${payload.result?.schema_version || "unavailable"}`),
    );
    identity.append(badges);
    header.append(identity);
    if (globalThis.agentKronigDesktop?.exportResultsPdf) {
      const commands = element("div", "result-command-bar");
      if ((payload.agent_run_id || payload.saved_bundle_id) && payload.workspace_id) {
        const popout = element("button", "result-popout", "Open in window");
        popout.type = "button";
        popout.addEventListener("click", () => {
          void globalThis.agentKronigDesktop.openResultsWindow({
            workspaceId: payload.workspace_id,
            ...(payload.saved_bundle_id ? {bundleRunId: payload.saved_bundle_id} : {runId: payload.agent_run_id}),
          });
        });
        const exportBundle = element("button", "result-export-bundle", "Export bundle");
        exportBundle.type = "button";
        exportBundle.addEventListener("click", async () => {
          exportBundle.disabled = true;
          const original = exportBundle.textContent;
          exportBundle.textContent = "Exporting…";
          try {
            const selection = await globalThis.agentKronigDesktop.chooseBundleExportDestination({
              suggestedName: `${payload.experiment?.name || payload.manifest?.run_id || "results"}.akbundle`,
            });
            if (!selection?.cancelled && selection?.path) {
              const endpoint = payload.saved_bundle_id
                ? `/api/workspaces/${encodeURIComponent(payload.workspace_id)}/saved-results/${encodeURIComponent(payload.saved_bundle_id)}/export`
                : `/api/runs/${encodeURIComponent(payload.agent_run_id)}/bundle/export`;
              const response = await fetch(endpoint, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({destination: selection.path}),
              });
              if (!response.ok) {
                throw new Error("The reproducibility bundle could not be exported.");
              }
            }
          } finally {
            exportBundle.disabled = false;
            exportBundle.textContent = original;
          }
        });
        commands.append(popout, exportBundle);
      }
      const exportPdf = element("button", "result-export-pdf", "Export PDF");
      exportPdf.type = "button";
      exportPdf.addEventListener("click", async () => {
        exportPdf.disabled = true;
        exportPdf.textContent = "Exporting…";
        try {
          await globalThis.agentKronigDesktop.exportResultsPdf({
            suggestedName: `${payload.experiment?.name || payload.manifest?.run_id || "results"}.pdf`,
          });
        } finally {
          exportPdf.disabled = false;
          exportPdf.textContent = "Export PDF";
        }
      });
      commands.append(exportPdf);
      header.append(commands);
    }
    const statusBanner = element("section", "result-status-dimensions");
    Object.entries(statusDimensions(payload)).forEach(([key, dimension]) => {
      const row = element("div", `result-status is-${dimension.tone}`);
      row.dataset.statusDimension = key;
      row.append(element("strong", "", `${dimension.label}: ${label(dimension.state)}`), element("span", "", dimension.detail));
      statusBanner.append(row);
    });
    root.append(workbench);
    workbench.append(header, statusBanner);
    const section = (name, renderer, parent = workbench) => {
      try { parent.append(renderer()); }
      catch (error) {
        const fallback = element("section", "result-section result-section-error");
        fallback.setAttribute("role", "alert");
        fallback.append(element("h2", "", `${name} could not be displayed`),
          element("p", "", "The rest of your results remain available. Refresh the viewer or inspect the canonical result and validation files."));
        parent.append(fallback);
        console.error(`Result section failed: ${name}`, error);
      }
    };
    section("Structure", () => renderStructure(payload));
    section("Metrics", () => renderMetrics(payload));
    section("Plots", () => renderFields(payload, comparisonRuns));
    const lower = element("div", "result-lower-grid");
    workbench.append(lower);
    section("Operating points", () => renderOperatingPoints(payload), lower);
    section("Validation evidence", () => renderValidation(payload), lower);
    if (payload.workspace_id && (payload.saved_bundle_id || payload.manifest?.run_id) && payload.recovery_actions?.length) {
      section("Numerical recovery", () => renderRecovery(payload));
    }
    section("Provenance", () => renderProvenance(payload));
    section("Reviewed inputs", () => renderInputLedger(payload));
    if (payload.recovery_comparison) {
      section("Recovery provenance", () => renderRecoveryComparison(payload.recovery_comparison));
    }
    return workbench;
  }

  globalThis.AgentKronigResults = {
    availableSelection,
    sampleCounts,
    statusDimensions,
    validationEvidence,
    datasetOptions,
    comparisonDatasetOptions,
    compatibleOverlayOptions,
    comparisonCsv,
    fieldOptions,
    findCanonicalResultPath,
    formatNumber,
    isCanonicalResultPath,
    render,
    resultStatus,
    seriesForDataset,
    structureMarkers,
    summarize,
    validationGroups,
    validationPresentation,
  };
})();
