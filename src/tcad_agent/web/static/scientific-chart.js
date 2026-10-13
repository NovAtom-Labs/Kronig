"use strict";

(() => {
  function finiteNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function segmentSeries(axisValues, values, valid = []) {
    const segments = [];
    let current = [];
    const count = Math.min(axisValues.length, values.length);
    for (let index = 0; index < count; index += 1) {
      const x = finiteNumber(axisValues[index]);
      const value = finiteNumber(values[index]);
      const accepted = valid.length ? Boolean(valid[index]) : true;
      if (x === null || value === null || !accepted) {
        if (current.length) segments.push(current);
        current = [];
        continue;
      }
      current.push({x, value, index});
    }
    if (current.length) segments.push(current);
    return segments;
  }

  function logTransform(values) {
    const numbers = values.map(finiteNumber);
    if (numbers.some((value) => value === null || value <= 0)) {
      return {accepted: false, values: []};
    }
    return {accepted: true, values: numbers.map((value) => Math.log10(value))};
  }

  function signedLogTransform(values) {
    const numbers = values.map(finiteNumber);
    if (numbers.some((value) => value === null)) return {accepted: false, values: []};
    return {
      accepted: true,
      values: numbers.map((value) => (
        valueForScale(value, "signed_log")
      )),
    };
  }

  function valueForScale(value, scale) {
    if (scale === "log") return Math.log10(value);
    if (scale === "signed_log") return Math.sign(value) * Math.log1p(Math.abs(value)) / Math.LN10;
    return value;
  }

  function tickValueForScale(value, scale) {
    if (scale === "log") return 10 ** value;
    if (scale === "signed_log") return Math.sign(value) * Math.expm1(Math.abs(value) * Math.LN10);
    return value;
  }

  function complexResponse(realValues, imaginaryValues) {
    if (realValues.length !== imaginaryValues.length) {
      return {magnitude: [], phaseDegrees: []};
    }
    return {
      magnitude: realValues.map((real, index) => Math.hypot(real, imaginaryValues[index])),
      phaseDegrees: realValues.map(
        (real, index) => Math.atan2(imaginaryValues[index], real) * 180 / Math.PI,
      ),
    };
  }

  function heatmapCells(firstAxis, secondAxis, values) {
    if (values.length !== firstAxis.length * secondAxis.length) return [];
    return values.map((value, index) => ({
      x: firstAxis[Math.floor(index / secondAxis.length)],
      y: secondAxis[index % secondAxis.length],
      value,
      index,
    }));
  }

  function zoomViewport(viewport, center, factor) {
    const minimum = Number(viewport.minimum);
    const maximum = Number(viewport.maximum);
    const boundedFactor = Math.min(10, Math.max(0.01, Number(factor)));
    const boundedCenter = Math.min(maximum, Math.max(minimum, Number(center)));
    const left = (boundedCenter - minimum) * boundedFactor;
    const right = (maximum - boundedCenter) * boundedFactor;
    return {minimum: boundedCenter - left, maximum: boundedCenter + right};
  }

  function panViewport(viewport, delta) {
    return {
      minimum: Number(viewport.minimum) + Number(delta),
      maximum: Number(viewport.maximum) + Number(delta),
    };
  }

  function clampViewport(viewport, extent) {
    const extentMinimum = Number(extent.minimum);
    const extentMaximum = Number(extent.maximum);
    const extentWidth = extentMaximum - extentMinimum;
    const width = Number(viewport.maximum) - Number(viewport.minimum);
    if (!(width > 0) || width >= extentWidth) {
      return {minimum: extentMinimum, maximum: extentMaximum};
    }
    if (Number(viewport.minimum) < extentMinimum) {
      return {minimum: extentMinimum, maximum: extentMinimum + width};
    }
    if (Number(viewport.maximum) > extentMaximum) {
      return {minimum: extentMaximum - width, maximum: extentMaximum};
    }
    return {minimum: Number(viewport.minimum), maximum: Number(viewport.maximum)};
  }

  function viewportForAction(viewport, extent, action) {
    if (action === "reset") {
      return {minimum: Number(extent.minimum), maximum: Number(extent.maximum)};
    }
    const current = clampViewport(viewport, extent);
    const center = (current.minimum + current.maximum) / 2;
    const factor = action === "zoom_in" ? 0.7 : action === "zoom_out" ? 1.25 : 1;
    return clampViewport(zoomViewport(current, center, factor), extent);
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }

  function toCsv(points, xLabel, valueLabel) {
    const rows = [[xLabel, valueLabel], ...points.map((point) => [point.x, point.value])];
    return `${rows.map((row) => row.map(csvCell).join(",")).join("\n")}\n`;
  }

  globalThis.AgentKronigScientificChart = {
    clampViewport,
    complexResponse,
    heatmapCells,
    logTransform,
    panViewport,
    segmentSeries,
    signedLogTransform,
    valueForScale,
    tickValueForScale,
    toCsv,
    viewportForAction,
    zoomViewport,
  };
})();
