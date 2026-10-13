"use strict";

// Headless audit of the actual workbench's dataset and slice selection logic.
// Reads canonical API payloads or result files; never modifies them.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const root = path.resolve(__dirname, "..");
for (const filename of ["scientific-chart.js", "results-workbench.js"]) {
  vm.runInThisContext(fs.readFileSync(path.join(root, "src/tcad_agent/web/static", filename), "utf8"), {filename});
}
const input = process.argv[2];
if (!input) throw new Error("Supply a canonical result or product result API JSON path");
const document = JSON.parse(fs.readFileSync(input, "utf8"));
const payload = document.result ? document : {result: document};
const result = payload.result;
const workbench = globalThis.AgentKronigResults;
const chart = globalThis.AgentKronigScientificChart;
const options = workbench.datasetOptions(payload);
assert.equal(options.length, Object.keys(result.datasets).length, "No valid canonical dataset may disappear from selection");
let slices = 0;
let samples = 0;
let signedSamples = 0;
for (const dataset of options) {
  const canonical = result.datasets[dataset.name];
  assert.equal(dataset.unit, canonical.unit);
  assert.equal(dataset.source, canonical.source);
  assert.deepEqual(dataset.values, canonical.values, "Plot source values must be unmodified canonical numbers");
  if (!dataset.shape.length || dataset.shape.length > 2) continue;
  const positionIndex = dataset.shape.length === 1 ? 0
    : dataset.axes.some(axis => axis.kind === "position")
      ? dataset.axes.findIndex(axis => axis.kind === "position")
      : Math.max(0, dataset.shape.findIndex(size => size > 1));
  const otherIndex = positionIndex === 0 ? 1 : 0;
  const count = dataset.shape.length === 1 ? 1 : dataset.shape[otherIndex];
  for (let index = 0; index < count; index += 1) {
    const series = workbench.seriesForDataset(dataset, index, "real");
    assert.deepEqual(series.axis.values, result.axes[canonical.axes[positionIndex]].values);
    assert.equal(series.valueUnit, canonical.unit);
    for (let position = 0; position < series.values.length; position += 1) {
      const flat = dataset.shape.length === 1 ? position
        : positionIndex === 1 ? index * dataset.shape[1] + position
          : position * dataset.shape[1] + index;
      assert.equal(series.values[position], canonical.values[flat], "Bias selector must select the exact requested profile");
      assert.equal(series.validity ? series.validity[position] : true, canonical.validity ? canonical.validity[flat] : true);
      const value = series.values[position];
      const plotted = chart.valueForScale(value, "signed_log");
      if (value !== 0) assert.equal(Math.sign(plotted), Math.sign(value), "Nonzero signed values must remain nonzero on a signed-log graph");
      const restored = chart.tickValueForScale(plotted, "signed_log");
      assert.ok(Math.abs(restored - value) <= 1e-12 * Math.abs(value) + Number.MIN_VALUE, "Scientific ticks must invert to original units");
      samples += 1;
      if (value < 0) signedSamples += 1;
    }
    slices += 1;
  }
}
console.log(JSON.stringify({source: input, datasets: options.length, slices, samples, signedSamples, status: "passed"}));
