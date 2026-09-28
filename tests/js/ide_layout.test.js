"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual}`);
}

function assertDeepEqual(actual, expected, message) {
  assertEqual(JSON.stringify(actual), JSON.stringify(expected), message);
}

const layout = globalThis.AgentKronigLayout;

assertDeepEqual(
  layout.clampLayout({viewport: 1180, explorer: 410, agent: 610}),
  {mode: "desktop", explorer: 360, agent: 320, center: 500},
  "overflow shrinks the agent first while preserving the center",
);
assertEqual(
  layout.clampLayout({viewport: 680, explorer: 218, agent: 356}).mode,
  "narrow",
  "narrow widths use drawers",
);
assertEqual(layout.clampLayout({viewport: 720, explorer: 218, agent: 356}).mode, "narrow", "720px uses drawers");
assertEqual(layout.clampLayout({viewport: 799, explorer: 218, agent: 356}).mode, "narrow", "799px uses drawers");
assertEqual(layout.clampLayout({viewport: 800, explorer: 218, agent: 356}).mode, "tablet", "800px preserves the 480px center minimum");
assertEqual(layout.clampLayout({viewport: 995, explorer: 218, agent: 356}).mode, "tablet", "995px remains tablet");
assertEqual(layout.clampLayout({viewport: 996, explorer: 218, agent: 356}).mode, "desktop", "996px enters the three-pane layout");
assertEqual(
  layout.clampLayout({viewport: 900, explorer: 218, agent: 356}).mode,
  "tablet",
  "tablet widths remove the explorer from the grid",
);
assertDeepEqual(
  layout.clampLayout({viewport: 1200, explorer: "broken", agent: -90}),
  {mode: "desktop", explorer: 218, agent: 320, center: 662},
  "corrupt stored values fall back or clamp safely",
);

const resizedExplorer = layout.resizeByKey(
  {viewport: 1200, explorer: 218, agent: 356},
  "explorer",
  "ArrowRight",
);
assertEqual(resizedExplorer.explorer, 230, "keyboard resizing uses a bounded 12 pixel step");
const resizedAgent = layout.resizeByKey(
  {viewport: 1200, explorer: 218, agent: 356},
  "agent",
  "ArrowLeft",
);
assertEqual(resizedAgent.agent, 368, "moving the right divider left widens the agent pane");
assertDeepEqual(
  layout.resetSide({viewport: 1200, explorer: 300, agent: 470}, "agent"),
  {mode: "desktop", explorer: 300, agent: 420, center: 480},
  "double-click reset restores the agent default",
);
assertDeepEqual(
  layout.parseStoredLayout("not-json"),
  {explorer: 218, agent: 420},
  "invalid persisted JSON is ignored",
);
assertDeepEqual(
  layout.parseStoredLayout('{"explorer":240,"agent":400}'),
  {explorer: 240, agent: 400},
  "valid persisted widths are restored",
);
assertDeepEqual(
  layout.resolvePanelAction(
    {mode: "desktop", collapsed: false, open: false},
    "close",
  ),
  {collapsed: true, open: false},
  "closing a desktop sidebar retracts it",
);
assertDeepEqual(
  layout.resolvePanelAction(
    {mode: "desktop", collapsed: true, open: false},
    "toggle",
  ),
  {collapsed: false, open: false},
  "toggling a retracted desktop sidebar restores it",
);
assertDeepEqual(
  layout.resolvePanelAction(
    {mode: "narrow", collapsed: false, open: false},
    "toggle",
  ),
  {collapsed: false, open: true},
  "narrow sidebars continue to use drawers",
);
assertDeepEqual(
  layout.resolvePanelAction(
    {mode: "tablet", collapsed: false, open: true},
    "close",
  ),
  {collapsed: false, open: false},
  "closing a responsive drawer hides it",
);

function fakeElement(rect = {left: 0, right: 1200, width: 1200}) {
  const listeners = {};
  const attributes = {};
  const properties = {};
  return {
    dataset: {},
    listeners,
    attributes,
    style: {setProperty(name, value) { properties[name] = value; }},
    properties,
    classList: {add() {}, remove() {}},
    addEventListener(name, callback) { listeners[name] = callback; },
    removeEventListener(name) { delete listeners[name]; },
    setAttribute(name, value) { attributes[name] = value; },
    getBoundingClientRect() { return rect; },
  };
}

const shell = fakeElement();
const explorerHandle = fakeElement();
const agentHandle = fakeElement();
const windowListeners = {};
const windowRef = {
  innerWidth: 1200,
  addEventListener(name, callback) { windowListeners[name] = callback; },
  removeEventListener(name) { delete windowListeners[name]; },
};
const stored = {};
const storage = {
  getItem(key) { return stored[key] || null; },
  setItem(key, value) { stored[key] = value; },
};
const controller = layout.createController({
  shell,
  explorerHandle,
  agentHandle,
  workspaceId: "workspace-1",
  storage,
  windowRef,
});
assertEqual(shell.dataset.layoutMode, "desktop", "controller applies desktop mode");
assertEqual(shell.properties["--explorer-width"], "218px", "controller applies explorer width");
assertEqual(shell.properties["--agent-width"], "420px", "controller applies the readable agent default");
assertEqual(explorerHandle.attributes["aria-valuenow"], "218", "separator reports its width");
assertEqual(agentHandle.attributes["aria-valuenow"], "420", "agent separator reports its width");
assertEqual(typeof controller.destroy, "function", "controller exposes lifecycle cleanup");
controller.destroy();
assertEqual(windowListeners.pointermove, undefined, "destroy removes global pointer listener");
