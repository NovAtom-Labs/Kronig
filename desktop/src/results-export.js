"use strict";

const fs = require("node:fs");

const PREPARE_PRINT = `(() => {
  const source = document.querySelector('.results-workbench');
  if (!source) throw new Error('Scientific results are unavailable for PDF export');
  document.querySelector('.ak-print-document')?.remove();
  document.getElementById('ak-results-print-style')?.remove();
  const printable = document.createElement('main');
  printable.className = 'ak-print-document';
  const results = source.cloneNode(true);
  results.querySelectorAll('details').forEach((detail) => {detail.open = true;});
  results.querySelectorAll('.result-chart svg[aria-label]').forEach((chart) => {
    const label = document.createElement('p');
    label.textContent = chart.getAttribute('aria-label');
    chart.parentElement.prepend(label);
  });
  printable.append(results);
  const style = document.createElement('style');
  style.id = 'ak-results-print-style';
  style.textContent = \`
    .ak-print-document { display: none !important; }
    @media print {
      @page { size: A4; margin: 14mm; }
      html, body { width: auto !important; height: auto !important; min-height: 0 !important;
        overflow: visible !important; background: white !important; color: #17202a !important; }
      body > :not(.ak-print-document) { display: none !important; }
      .ak-print-document { display: block !important; }
      .ak-print-document .results-workbench { padding: 0 !important; width: auto !important; }
      .ak-print-document * { color: #17202a !important; background: transparent !important;
        text-shadow: none !important; overflow: visible !important; }
      .ak-print-document .result-command-bar, .ak-print-document .result-field-controls,
      .ak-print-document .result-chart-tooltip { display: none !important; }
      .ak-print-document .result-lower-grid { display: block !important; }
      .ak-print-document .result-section { margin-top: 14px !important; border: 1px solid #c5ccd2;
        break-inside: avoid; }
      .ak-print-document .result-status, .ak-print-document .result-metric { min-width: 0 !important; }
      .ak-print-document .result-metric-value { display: block !important; }
      .ak-print-document .result-metric-value strong,
      .ak-print-document .result-provenance dd { white-space: normal !important;
        text-overflow: clip !important; overflow-wrap: anywhere; }
      .ak-print-document .result-metric-value strong { display: block !important; }
      .ak-print-document svg text { fill: #263240 !important; }
      .ak-print-document .result-chart-grid { stroke: #d6dce1 !important; }
      .ak-print-document .result-chart-line { stroke: #285f96 !important; }
      .ak-print-document .result-chart-line.is-overlay { stroke: #92591d !important; }
      .ak-print-document .result-chart { break-inside: avoid; }
    }
  \`;
  document.head.append(style);
  document.body.append(printable);
})()`;

const RESTORE_PRINT = `(() => {
  document.querySelector('.ak-print-document')?.remove();
  document.getElementById('ak-results-print-style')?.remove();
})()`;

async function exportResultsPdf({dialog, sender, parent = null, payload = {}}) {
  const baseName = String(payload.suggestedName || "agent-kronig-results")
    .replace(/[^a-z0-9._-]+/gi, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96) || "agent-kronig-results";
  const result = await dialog.showSaveDialog(parent, {
    title: "Export scientific results PDF",
    defaultPath: `${baseName.replace(/\.pdf$/i, "")}.pdf`,
    filters: [{name: "PDF document", extensions: ["pdf"]}],
  });
  if (result.canceled || !result.filePath) {
    return Object.freeze({cancelled: true, path: null});
  }
  let pdf;
  try {
    await sender.executeJavaScript(PREPARE_PRINT);
    pdf = await sender.printToPDF({
      printBackground: true,
      preferCSSPageSize: true,
      pageSize: "A4",
    });
  } finally {
    try {await sender.executeJavaScript(RESTORE_PRINT);} catch { /* Renderer may have closed. */ }
  }
  fs.writeFileSync(result.filePath, pdf, {mode: 0o600});
  return Object.freeze({cancelled: false, path: result.filePath});
}

module.exports = {exportResultsPdf};
