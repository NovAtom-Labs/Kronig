const assert = require("node:assert/strict");
const test = require("node:test");

const {
  attachNavigationPolicy,
  configureApplicationIdentity,
  createLaunchToken,
  developmentIconPath,
  shouldAutoStart,
  installGracefulQuit,
  installWindowCloseGuard,
  installPermissionPolicy,
  resultWindowUrl,
  sanitizeDiagnosticSummary,
  retireReplacedWindow,
} = require("../src/main");

test("denies every renderer permission request and check", () => {
  let requestHandler;
  let checkHandler;
  installPermissionPolicy({
    setPermissionRequestHandler(handler) { requestHandler = handler; },
    setPermissionCheckHandler(handler) { checkHandler = handler; },
  });

  let decision = true;
  requestHandler({}, "media", (allowed) => { decision = allowed; });
  assert.equal(decision, false);
  assert.equal(checkHandler({}, "clipboard-read"), false);
});

test("navigation policy allows only the authenticated loopback origin", () => {
  let openHandler;
  let navigateHandler;
  const webContents = {
    setWindowOpenHandler(handler) {
      openHandler = handler;
    },
    on(event, handler) {
      if (event === "will-navigate") navigateHandler = handler;
    },
  };
  attachNavigationPolicy(webContents, "http://127.0.0.1:43127");

  assert.deepEqual(openHandler(), {action: "deny"});
  let prevented = false;
  navigateHandler({preventDefault: () => { prevented = true; }}, "http://127.0.0.1:43127/workspaces/1");
  assert.equal(prevented, false);
  navigateHandler({preventDefault: () => { prevented = true; }}, "https://example.com/");
  assert.equal(prevented, true);
});

test("result pop-out URL is restricted to typed local workspace and run identifiers", () => {
  assert.equal(
    resultWindowUrl("http://127.0.0.1:43127", {
      workspaceId: "11111111-1111-4111-8111-111111111111",
      runId: "22222222-2222-4222-8222-222222222222",
    }),
    "http://127.0.0.1:43127/workspaces/11111111-1111-4111-8111-111111111111?result_run_id=22222222-2222-4222-8222-222222222222",
  );
  assert.throws(
    () => resultWindowUrl("https://example.com", {workspaceId: "../outside", runId: "x"}),
    /identifier/,
  );
});

test("clipboard diagnostic summaries are bounded and redact secrets", () => {
  const summary = sanitizeDiagnosticSummary({
    diagnosticId: "diag-0123456789abcdef",
    code: "local_state_operation_failed",
    message: "token=secret-value " + "x".repeat(9000),
  });

  assert.match(summary, /diag-0123456789abcdef/);
  assert.doesNotMatch(summary, /secret-value/);
  assert.ok(summary.length <= 4096);
});

test("saved-result popouts accept bounded bundle identities without a chat run", () => {
  const payload = {workspaceId:"11111111-1111-4111-8111-111111111111", bundleRunId:"run-04d255359017"};
  assert.equal(resultWindowUrl("http://127.0.0.1:43127", payload),
    "http://127.0.0.1:43127/workspaces/11111111-1111-4111-8111-111111111111?saved_bundle_id=run-04d255359017");
  for (const bundleRunId of ["../outside", "x/y", "", "x".repeat(129)]) {
    assert.throws(() => resultWindowUrl("http://127.0.0.1:43127", {...payload,bundleRunId}), /identifier/);
  }
  assert.throws(() => resultWindowUrl("http://127.0.0.1:43127", {...payload,
    runId:"22222222-2222-4222-8222-222222222222"}), /identifier/);
});

test("launch token contains at least 32 random bytes", () => {
  const first = createLaunchToken();
  const second = createLaunchToken();
  assert.notEqual(first, second);
  assert.ok(Buffer.from(first, "base64url").length >= 32);
});

test("desktop entrypoint auto-starts only in Electron's browser process", () => {
  assert.equal(shouldAutoStart({type: "browser"}), true);
  assert.equal(shouldAutoStart({type: "renderer"}), false);
  assert.equal(shouldAutoStart({}), false);
});

test("development windows use the tracked Agent Kronig icon", () => {
  const path = require("node:path");
  const icon = developmentIconPath(false, path.resolve(__dirname, ".."));

  assert.equal(icon, path.resolve(__dirname, "../assets/icon.png"));
  assert.equal(developmentIconPath(true, path.resolve(__dirname, "..")), undefined);
});

test("development runtime identifies itself as Agent Kronig", () => {
  const names = [];

  configureApplicationIdentity({setName(name) { names.push(name); }});

  assert.deepEqual(names, ["Agent Kronig"]);
});

test("application quit waits for backend shutdown", async () => {
  let handler;
  let quitCalls = 0;
  let releaseStop;
  const stopped = new Promise((resolve) => { releaseStop = resolve; });
  const isShutdownComplete = installGracefulQuit(
    {
      on(event, callback) {
        if (event === "before-quit") handler = callback;
      },
      quit() {
        quitCalls += 1;
      },
    },
    () => stopped,
  );
  let prevented = false;
  handler({preventDefault: () => { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(quitCalls, 0);
  assert.equal(isShutdownComplete(), false);
  releaseStop();
  await stopped;
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(quitCalls, 1);
  assert.equal(isShutdownComplete(), true);
});

test("window close keeps the renderer alive until graceful shutdown completes", () => {
  let closeHandler;
  let quitCalls = 0;
  let shutdownComplete = false;
  installWindowCloseGuard(
    {on(event, callback) { if (event === "close") closeHandler = callback; }},
    {quit() { quitCalls += 1; }},
    () => shutdownComplete,
  );

  let prevented = false;
  closeHandler({preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(quitCalls, 1);

  shutdownComplete = true;
  prevented = false;
  closeHandler({preventDefault() { prevented = true; }});
  assert.equal(prevented, false);
  assert.equal(quitCalls, 1);
});

test("retiring a replaced window does not initiate application quit", () => {
  let retired = false;
  const oldWindow = {destroy() {retired = true;}, close() {throw new Error("replacement initiated quit");}};
  retireReplacedWindow(oldWindow, {});
  assert.equal(retired, true);
  retired = false;
  retireReplacedWindow(oldWindow, oldWindow);
  assert.equal(retired, false);
});

test("application quit remains open when backend work is active", async () => {
  let handler;
  let quitCalls = 0;
  let blockedCalls = 0;
  installGracefulQuit(
    {
      on(_event, callback) { handler = callback; },
      quit() { quitCalls += 1; },
    },
    async () => { throw new Error("active work"); },
    async () => { blockedCalls += 1; },
  );
  handler({preventDefault() {}});
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(quitCalls, 0);
  assert.equal(blockedCalls, 1);
});

test("application quit can never be trapped by backend cleanup failure", async () => {
  let handler;
  let quitCalls = 0;
  let forcedStops = 0;
  installGracefulQuit(
    {
      on(_event, callback) { handler = callback; },
      quit() { quitCalls += 1; },
    },
    async () => { throw new Error("cleanup failed"); },
    async () => "quit-anyway",
    async () => { forcedStops += 1; },
  );

  handler({preventDefault() {}});
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(forcedStops, 1);
  assert.equal(quitCalls, 1);
});
