const assert = require("node:assert/strict");
const test = require("node:test");

const {installPreload} = require("../src/preload");

test("preload exposes only the allowlisted desktop contract", () => {
  let exposedName;
  let exposedApi;
  const calls = [];
  installPreload({
    contextBridge: {
      exposeInMainWorld(name, api) {
        exposedName = name;
        exposedApi = api;
      },
    },
    ipcRenderer: {
      invoke(channel) {
        calls.push(channel);
        return Promise.resolve({channel});
      },
    },
  });

  assert.equal(exposedName, "agentKronigDesktop");
  assert.deepEqual(Object.keys(exposedApi).sort(), [
    "applyUpdateWhenSafe",
    "checkForUpdates",
    "chooseBundleExportDestination",
    "copyDiagnosticSummary",
    "exportResultsPdf",
    "getDesktopInfo",
    "getSettings",
    "getUpdateState",
    "openDiagnostics",
    "openResultsWindow",
    "saveSettings",
    "selectDirectory",
  ]);
  assert.equal(Object.isFrozen(exposedApi), true);
  assert.equal("invoke" in exposedApi, false);

  return Promise.all(Object.values(exposedApi).map((fn) => fn())).then(() => {
    assert.deepEqual(calls.sort(), [
      "desktop:apply-update-when-safe",
      "desktop:check-for-updates",
      "desktop:choose-bundle-export-destination",
      "desktop:copy-diagnostic-summary",
      "desktop:export-results-pdf",
      "desktop:get-info",
      "desktop:get-settings",
      "desktop:get-update-state",
      "desktop:open-diagnostics",
      "desktop:open-results-window",
      "desktop:save-settings",
      "desktop:select-directory",
    ]);
  });
});
