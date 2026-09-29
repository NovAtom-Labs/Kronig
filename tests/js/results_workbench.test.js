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

const datasetPayload = {
  result: {
    axes: {
      bias: {id: "bias", kind: "bias", label: "Bias", unit: "V", values: [-1, 0, 1]},
      position: {id: "position", kind: "position", label: "Position", unit: "m", values: [0, 1e-6]},
      frequency: {id: "frequency", kind: "frequency", label: "Frequency", unit: "Hz", values: [1e3, 1e4]},
    },
    datasets: {
      current: {id: "current", label: "Current", unit: "A/m^2", axes: ["bias"], shape: [3], values: [-1, 0, 1], validity: [true, false, true]},
      potential_map: {id: "potential_map", label: "Potential map", unit: "V", axes: ["bias", "position"], shape: [3, 2], values: [0, 1, 1, 2, 2, 3], validity: [true, true, false, false, true, true]},
      admittance: {id: "admittance", label: "Admittance", unit: "S/m^2", axes: ["frequency"], shape: [2], values: [1, 2], imaginary_values: [3, 4]},
      peak: {id: "peak", label: "Peak", unit: "V/m", axes: [], shape: [], centering: "scalar", values: [7]},
    },
  },
};
const datasets = results.datasetOptions(datasetPayload);
assertEqual(datasets.length, 4, "every well-formed canonical dataset is discoverable");
assertEqual(datasets[0].plotKind, "curve", "a rank-one dataset is a generic curve");
assertEqual(datasets[1].plotKind, "profile_family", "bias-position data is a profile family");
assertEqual(datasets[2].plotKind, "complex_response", "complex rank-one data is a response");
assertEqual(datasets[3].plotKind, "metric", "rank-zero data is a metric");
const overlayPayload = {
  result: {
    axes: datasetPayload.result.axes,
    datasets: {
      electron_current: {id: "electron_current", label: "Electron current", unit: "A/m^2", axes: ["bias"], shape: [3], values: [1, 2, 3]},
      hole_current: {id: "hole_current", label: "Hole current", unit: "A/m^2", axes: ["bias"], shape: [3], values: [3, 2, 1]},
      voltage: {id: "voltage", label: "Voltage", unit: "V", axes: ["bias"], shape: [3], values: [-1, 0, 1]},
    },
  },
};
const overlayDatasets = results.datasetOptions(overlayPayload);
assertEqual(
  results.compatibleOverlayOptions(overlayDatasets[0], overlayDatasets).map((item) => item.id).join(","),
  "hole_current",
  "overlay discovery accepts only datasets with matching axes, shape, and units",
);
const profile = results.seriesForDataset(datasets[1], 1);
assertEqual(profile.values.join(","), "1,2", "profile selection slices a generic rank-two dataset");
assertEqual(profile.validity.join(","), "false,false", "profile selection preserves failed-point masks");
assertEqual(profile.sliceAxis.kind, "bias", "the non-position axis controls profile selection");
const markers = results.structureMarkers({
  experiment: {
    regions: [
      {id: "left_region", x0: {magnitude_si: 0}, x1: {magnitude_si: 1e-6}},
      {id: "right_region", x0: {magnitude_si: 1e-6}, x1: {magnitude_si: 2e-6}},
    ],
    contacts: [
      {id: "left_contact", location: "x_min"},
      {id: "right_contact", location: "x_max"},
    ],
  },
});
assertEqual(markers.length, 3, "the viewer exposes one interface and both contact markers");
assertEqual(markers[0].kind, "contact", "left boundary marker identifies its contact");
assertEqual(markers[1].kind, "interface", "internal boundary marker identifies its interface");
assertEqual(markers[2].label, "right_contact", "right boundary marker preserves contact identity");
assertEqual(
  results.datasetOptions({result: {axes: {}, datasets: {broken: {id: "broken", label: "Broken", unit: "V", axes: ["missing"], shape: [2], values: [1, 2]}}}}).length,
  0,
  "datasets with unresolved axes never reach the viewer",
);
