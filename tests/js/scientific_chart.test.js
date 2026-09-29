"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual}`);
}

const chart = globalThis.AgentKronigScientificChart;

const segmented = chart.segmentSeries(
  [0, 1, 2, 3],
  [10, 20, 30, 40],
  [true, false, true, true],
);
assertEqual(segmented.length, 2, "failed operating points create visible gaps");
assertEqual(segmented[0].length, 1, "the first valid point is preserved");
assertEqual(segmented[1].length, 2, "the later valid run is preserved");

assertEqual(chart.logTransform([1, 10, 100]).accepted, true, "positive values support log scale");
assertEqual(chart.logTransform([1, 0, 100]).accepted, false, "zero rejects log scale safely");
const signed = chart.signedLogTransform([-100, -1, 0, 1, 100]);
assertEqual(signed.accepted, true, "signed-log accepts bipolar and zero-valued data");
assertEqual(Math.round(signed.values[0]), -2, "signed-log preserves negative sign");
assertEqual(signed.values[2], 0, "signed-log preserves zero");
assertEqual(Math.round(signed.values[4]), 2, "signed-log preserves positive sign");

const complex = chart.complexResponse([3, 0], [4, 1]);
assertEqual(complex.magnitude[0], 5, "complex magnitude is derived generically");
assertEqual(Math.round(complex.phaseDegrees[1]), 90, "complex phase is available in degrees");

const cells = chart.heatmapCells([0, 1], [10, 20, 30], [1, 2, 3, 4, 5, 6]);
assertEqual(cells.length, 6, "rank-two flattened data maps to every heatmap cell");
assertEqual(cells[4].x, 1, "heatmap coordinates preserve first-axis order");
assertEqual(cells[4].y, 20, "heatmap coordinates preserve second-axis order");

const zoomed = chart.zoomViewport({minimum: 0, maximum: 10}, 5, 0.5);
assertEqual(zoomed.minimum, 2.5, "zoom preserves the data-space center");
assertEqual(zoomed.maximum, 7.5, "zoom changes range deterministically");
const panned = chart.panViewport(zoomed, 1);
assertEqual(panned.minimum, 3.5, "pan moves the viewport in data units");
assertEqual(panned.maximum, 8.5, "pan preserves viewport width");
const clamped = chart.clampViewport({minimum: -3, maximum: 3}, {minimum: 0, maximum: 10});
assertEqual(clamped.minimum, 0, "panning is clamped at the dataset boundary");
assertEqual(clamped.maximum, 6, "clamping preserves the visible width");
const reset = chart.clampViewport({minimum: -5, maximum: 15}, {minimum: 0, maximum: 10});
assertEqual(reset.minimum, 0, "an oversized viewport resets to the full extent");
assertEqual(reset.maximum, 10, "an oversized viewport cannot exceed the full extent");

assertEqual(
  chart.toCsv([{x: 0, value: 1}, {x: 2, value: 3}], "Bias (V)", "Current (A/m^2)"),
  "Bias (V),Current (A/m^2)\n0,1\n2,3\n",
  "CSV export is deterministic and contains labels",
);
