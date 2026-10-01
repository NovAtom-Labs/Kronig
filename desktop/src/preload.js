"use strict";

const CHANNELS = Object.freeze({
  selectDirectory: "desktop:select-directory",
  getDesktopInfo: "desktop:get-info",
  getUpdateState: "desktop:get-update-state",
  checkForUpdates: "desktop:check-for-updates",
  chooseBundleExportDestination: "desktop:choose-bundle-export-destination",
  copyDiagnosticSummary: "desktop:copy-diagnostic-summary",
  exportResultsPdf: "desktop:export-results-pdf",
  openDiagnostics: "desktop:open-diagnostics",
  openResultsWindow: "desktop:open-results-window",
  applyUpdateWhenSafe: "desktop:apply-update-when-safe",
  getSettings: "desktop:get-settings",
  saveSettings: "desktop:save-settings",
});

function createDesktopApi(ipcRenderer) {
  return Object.freeze(
    Object.fromEntries(
      Object.entries(CHANNELS).map(([name, channel]) => [
        name,
        (...args) => ipcRenderer.invoke(channel, ...args),
      ]),
    ),
  );
}

function installPreload({contextBridge, ipcRenderer}) {
  contextBridge.exposeInMainWorld("agentKronigDesktop", createDesktopApi(ipcRenderer));
}

if (process.type === "renderer") {
  installPreload(require("electron"));
}

module.exports = {CHANNELS, createDesktopApi, installPreload};
