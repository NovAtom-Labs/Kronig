const assert = require("node:assert/strict");
const test = require("node:test");
const {BackendLifecycle} = require("../src/backend-lifecycle");

test("closing during a pending restart prevents a replacement backend", async () => {
  let release;
  const cleanup = new Promise((resolve) => {release = resolve;});
  let launches = 0;
  const oldBackend = {async stop() {await cleanup;}, async start() {return {};}};
  const lifecycle = new BackendLifecycle(() => {launches += 1; return oldBackend;});
  await lifecycle.launch({});
  const restart = lifecycle.launch({});
  lifecycle.preventLaunch();
  const stop = lifecycle.stop();
  release();
  assert.equal(await restart, null);
  await stop;
  assert.equal(launches, 1, "close must prevent reacquiring backend ownership");
});

test("closing during startup waits for cleanup and never presents readiness", async () => {
  let release;
  const ready = new Promise((resolve) => {release = resolve;});
  let cleaned = false;
  const lifecycle = new BackendLifecycle(() => ({
    async start() {return ready;}, async stop() {cleaned = true;},
  }));
  const launch = lifecycle.launch({});
  await new Promise((resolve) => setImmediate(resolve));
  lifecycle.preventLaunch();
  const stop = lifecycle.stop();
  release({url:"http://127.0.0.1:12345"});
  assert.equal(await launch, null);
  await stop;
  assert.equal(cleaned, true);
  assert.equal(await lifecycle.launch({}), null);
  lifecycle.resumeLaunch();
  assert.ok(await lifecycle.launch({}));
});
