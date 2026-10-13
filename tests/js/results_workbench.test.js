"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual}`);
}

const results = globalThis.AgentKronigResults;

const independentStatuses = results.statusDimensions({
  execution_state: "completed", validation: {overall: "failed", checks: [{status: "failed"}]},
  deliverable_state: "complete",
});
assertEqual(independentStatuses.execution.state, "completed", "failed scientific checks cannot erase completed execution");
assertEqual(independentStatuses.scientific.state, "needs_review", "scientific failure stays explicit");
assertEqual(independentStatuses.deliverables.state, "complete", "scientific failure cannot erase delivered outputs");
assertEqual(results.statusDimensions({execution_state: "completed", validation: {overall: "passed", checks: []}}).scientific.state,
  "unavailable", "an empty validation report cannot imply scientific success");
assertEqual(results.statusDimensions({execution_state: "completed", validation: {checks: [{level: "execution", status: "passed"}, {level: "provenance", status: "passed"}]}}).scientific.state,
  "unavailable", "execution and provenance checks do not substitute for scientific validation");
assertEqual(results.statusDimensions({execution_state: "completed", validation: {checks: [{status: "passed"}]}}).deliverables.state,
  "unavailable", "unknown output coverage is never fabricated");

const acCountPayload = {result: {operating_points: [{state: "converged"}], axes: {
  frequency: {id: "frequency", kind: "frequency", label: "Frequency", unit: "Hz", values: [1e3, 1e4, 1e5]},
}, datasets: {
  admittance: {axes: ["frequency"], shape: [3], values: [1, 2, 3], validity: [true, false, true]},
  capacitance: {axes: ["frequency"], shape: [3], values: [1, 1, 1], validity: [true, false, true]},
}}};
const acCounts = results.sampleCounts(acCountPayload);
assertEqual(acCounts.operatingPoints, 1, "frequency response retains its one DC baseline");
assertEqual(acCounts.frequencySamples, 3, "frequency samples are not summed across datasets");
assertEqual(acCounts.validFrequencySamples, 2, "invalid AC samples remain distinct from DC convergence");
assertEqual(acCounts.frequencies, 3, "unique frequency count uses the canonical frequency axis");
assertEqual(results.sampleCounts({result: {fields: {}}}).frequencySamples, 0, "no AC data implies no fabricated AC samples");
const coupledCounts = results.sampleCounts({result: {operating_points: [{state: "converged"}, {state: "failed"}],
  axes: {bias: {id: "bias", kind: "bias", values: [0, 1]}, frequency: {id: "frequency", kind: "frequency", values: [1e3, 1e4]}},
  datasets: {admittance: {axes: ["bias", "frequency"], shape: [2, 2], values: [1, 2, 3, 4], validity: [true, true, false, false]}}}});
assertEqual(coupledCounts.operatingPoints, 2, "coupled sweeps keep DC accounting independent");
assertEqual(coupledCounts.frequencySamples, 4, "coupled AC grid counts bias-frequency pairs");
assertEqual(coupledCounts.frequencies, 2, "a coupled AC grid does not inflate unique frequency count");
const assessed = results.statusDimensions({assessment: {
  execution: {status: "passed", message: "Execution recorded"},
  numerical: {status: "not_applicable", message: "No physical evidence"},
  output_coverage: {status: "failed", message: "Missing charge"},
}});
assertEqual(assessed.scientific.state, "unavailable", "assessment applicability does not receive a scientific pass");
assertEqual(assessed.deliverables.detail, "Missing charge", "the backend's output coverage reason stays visible");

const residual = results.validationEvidence({level: "physical", evidence_origin: "derived",
  measured_value: 2.96e-6, limit: 1e-6, unit: "A/m^2", absolute_tolerance: 1e-6,
  relative_tolerance: 1e-4, scale: 2e-8,
});
assertEqual(residual.includes("measured 2.960e-6 A/m^2"), true, "tiny residuals retain scientific units");
assertEqual(residual.includes("absolute tolerance 1.000e-6 A/m^2"), true, "absolute acceptance limit stays inspectable");
assertEqual(residual.includes("scale 2.000e-8 A/m^2"), true, "near-zero current scale stays inspectable");
assertEqual(results.validationEvidence({status: "not_applicable", applicability_reason: "No terminal currents"}).includes("No terminal currents"), true,
  "excluded scientific checks state their applicability reason");

const temperatureSummary = results.summarize({result: {operating_points: [
  {state: "converged", coordinates: {temperature: 300}, terminal_currents_a_per_m2: {left: 1e-8, right: -1e-8}},
]}});
assertEqual(temperatureSummary.operatingPointCount, 1, "canonical non-voltage study points are visible");
assertEqual(temperatureSummary.maximumTerminalCurrent, 1e-8, "temperature currents are not labelled unavailable");

const biasAc = results.datasetOptions({result:{axes:{
  bias:{id:"bias",kind:"bias",unit:"V",values:[-1,0,1]},
  frequency:{id:"frequency",kind:"frequency",unit:"Hz",values:[1e6]},
},datasets:{capacitance:{axes:["bias","frequency"],shape:[3,1],values:[1,2,3],unit:"F/m^2"}}}})[0];
assertEqual(biasAc.plotKind, "curve_family", "a single-frequency bias sweep must be an interactive C-V curve, not a degenerate heatmap");
assertEqual(results.seriesForDataset(biasAc).values.join(","), "1,2,3", "bias capacitance extraction follows canonical axes");

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
assertEqual(summary.validationApplicable, 2, "validation summary counts only checks that apply");
assertEqual(summary.validationFailed, 0, "validation summary keeps failures explicit");
assertEqual(summary.validationNotApplicable, 0, "validation summary keeps skipped checks separate");

const mixedValidation = results.summarize({
  result: {fields: {}, bias_points: []},
  validation: {
    checks: [
      {id: "convergence", status: "passed"},
      {id: "conservation", status: "passed"},
      {id: "band-ordering", status: "failed"},
      {id: "unexpected", status: "unknown"},
      {id: "ac-consistency", status: "not_applicable"},
      {id: "sweep-continuity", status: "not_applicable"},
    ],
  },
});
assertEqual(mixedValidation.validationPassed, 2, "passed checks remain visible");
assertEqual(mixedValidation.validationApplicable, 4, "not-applicable checks never dilute the applicable denominator");
assertEqual(mixedValidation.validationFailed, 2, "every non-passing applicable status remains actionable");
assertEqual(mixedValidation.validationNotApplicable, 2, "irrelevant checks are explained separately");

const validationGroups = results.validationGroups([
  {id: "pass", status: "passed"},
  {id: "skip", status: "not_applicable"},
  {id: "fail", status: "failed"},
  {id: "review", status: "warning"},
]);
assertEqual(validationGroups.actionable.map((check) => check.id).join(","), "fail,review", "failures and warnings are prioritized");
assertEqual(validationGroups.passed.map((check) => check.id).join(","), "pass", "passed evidence remains available");
assertEqual(validationGroups.notApplicable.map((check) => check.id).join(","), "skip", "not-applicable evidence is isolated from failures");

const passingPresentation = results.validationPresentation([
  {id: "convergence", status: "passed"},
  {id: "conservation", status: "passed"},
  {id: "ac", status: "not_applicable"},
  {id: "sweep", status: "not_applicable"},
]);
assertEqual(passingPresentation.headline, "All 2 applicable checks passed", "successful validation does not count irrelevant checks as missing passes");
assertEqual(passingPresentation.summary, "2 passed · 0 failed · 2 not applicable", "validation status has an unambiguous breakdown");
assertEqual(passingPresentation.tone, "success", "all applicable checks receive success styling");
assertEqual([...passingPresentation.passed].length, 2, "the renderer can iterate passed checks");
assertEqual([...passingPresentation.notApplicable].length, 2, "the renderer can iterate excluded checks");

const failingPresentation = results.validationPresentation([
  {id: "convergence", status: "passed"},
  {id: "conservation", status: "failed"},
  {id: "ac", status: "not_applicable"},
]);
assertEqual(failingPresentation.headline, "1 of 2 applicable checks passed", "failed applicable checks remain visible in the headline");
assertEqual(failingPresentation.tone, "failed", "a failed scientific check cannot receive success styling");

assertEqual(results.availableSelection("1", ["0", "1", "2"]), "1", "a redraw preserves the selected operating point");
assertEqual(results.availableSelection("missing", ["0", "1", "2"]), "0", "a removed option falls back predictably");
assertEqual(results.availableSelection("", []), "", "an empty control has no fabricated selection");

const empty = results.summarize({result: {fields: {}, bias_points: []}, validation: {checks: []}});
assertEqual(empty.potentialRange, null, "missing potential is unavailable rather than zero");
assertEqual(empty.peakElectricField, null, "missing electric field is unavailable rather than zero");
assertEqual(empty.maximumTerminalCurrent, null, "missing current is unavailable rather than zero");
assertEqual(results.formatNumber(null), "Unavailable", "a missing metric must never format as zero");
const reviewStatus = results.resultStatus({
  execution_state: "completed",
  validation_state: "needs_review",
  validation: {overall: "failed"},
});
assertEqual(reviewStatus.title, "Execution completed · validation needs review", "execution and validation states remain distinct");
assertEqual(reviewStatus.tone, "warning", "failed validation never receives success styling");

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

const crossRun = results.comparisonDatasetOptions([
  {bundle_path: "run-a", result: overlayPayload.result},
  {bundle_path: "run-b", result: overlayPayload.result},
]);
assertEqual(crossRun.length, 6, "comparison discovery preserves every verified run dataset");
assertEqual(crossRun[3].runLabel, "run-b", "comparison datasets retain run provenance");
assertEqual(
  results.compatibleOverlayOptions(crossRun[0], crossRun).map((item) => item.runLabel).join(","),
  "run-a,run-b,run-b",
  "compatible overlays can span verified runs while refusing unit mismatches",
);
const comparisonCsv = results.comparisonCsv(
  {axis: {label: "Bias", unit: "V", values: [-1, 0, 1]}, values: [1, 2, 3]},
  crossRun[0],
  {axis: {label: "Bias", unit: "V", values: [-1, 0, 1]}, values: [3, 2, 1]},
  crossRun[1],
);
assertEqual(
  comparisonCsv.split("\n")[0],
  "Bias (V),Electron current · run-a (A/m^2),Hole current · run-a (A/m^2)",
  "comparison CSV exports every visible series with run provenance",
);
