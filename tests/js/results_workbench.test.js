"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual}`);
}

const results = globalThis.AgentKronigResults;

assertEqual(
  results.isCanonicalResultPath("runs/equilibrium/results/canonical.json"),
  true,
  "the canonical bundle artifact should open in the workbench",
);
assertEqual(
  results.isCanonicalResultPath("runs\\equilibrium\\results\\canonical.json"),
  true,
  "canonical bundle recognition should remain portable on Windows",
);
assertEqual(
  results.isCanonicalResultPath("notes/canonical.json"),
  false,
  "an unrelated JSON file must remain in the generic viewer",
);

assertEqual(
  results.findCanonicalResultPath({
    files: [
      {path: "README.md", operation: "modified"},
      {path: "run/results/canonical.json", operation: "created"},
      {path: "old/results/canonical.json", operation: "deleted"},
    ],
  }),
  "run/results/canonical.json",
  "run completion should select the newly written canonical result",
);
assertEqual(
  results.findCanonicalResultPath({
    files: [{path: "old/results/canonical.json", operation: "deleted"}],
  }),
  null,
  "a deleted result must never auto-open",
);

const payload = {
  result: {
    backend: "devsim",
    status: "completed",
    bias_points: [{
      bias_v: 0,
      converged: true,
      terminal_currents_a_per_m2: {left: 2e-16, right: -2e-16},
    }],
    fields: {
      potential: {positions_m: [0, 1e-6, 2e-6], values: [0, 0.41, 0.82], unit: "V"},
      electric_field: {positions_m: [0, 1e-6, 2e-6], values: [0, -1.6e7, 0], unit: "V/m"},
      malformed: {positions_m: [0], values: [Number.NaN], unit: "1"},
    },
  },
  validation: {
    overall: "passed",
    checks: [
      {id: "execution", status: "passed"},
      {id: "physics", status: "passed"},
    ],
  },
};
const summary = results.summarize(payload);
assertEqual(summary.potentialRange, 0.82, "potential range comes from canonical field values");
assertEqual(summary.peakElectricField, 1.6e7, "peak field uses absolute canonical values");
assertEqual(summary.maximumTerminalCurrent, 2e-16, "terminal current summary uses canonical bias points");
assertEqual(summary.fieldCount, 3, "field count reports the canonical field inventory");
assertEqual(summary.validationPassed, 2, "validation summary counts passed checks");
assertEqual(summary.validationTotal, 2, "validation summary counts every check");

const empty = results.summarize({result: {fields: {}, bias_points: []}, validation: {checks: []}});
assertEqual(empty.potentialRange, null, "missing potential is unavailable rather than zero");
assertEqual(empty.peakElectricField, null, "missing electric field is unavailable rather than zero");
assertEqual(empty.maximumTerminalCurrent, null, "missing current is unavailable rather than zero");
assertEqual(results.formatNumber(null), "Unavailable", "a missing metric must never format as zero");

const fields = results.fieldOptions(payload);
assertEqual(fields.length, 2, "only finite aligned field series are graphable");
assertEqual(fields[0].name, "potential", "field order follows canonical result order");
assertEqual(fields[1].name, "electric_field", "all valid canonical fields remain selectable");
