const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {execFile} = require("node:child_process");

const {
  BackendSupervisor,
  resolveBackendLaunch,
} = require("../src/backend-supervisor");

function fixture(source) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "agent-kronig-sidecar-"));
  const script = path.join(directory, "fixture.js");
  fs.writeFileSync(script, source);
  return {directory, script};
}

function supervisorFor(script, overrides = {}) {
  return new BackendSupervisor({
    command: process.execPath,
    args: [script],
    dataDir: path.dirname(script),
    tokenFactory: () => "t".repeat(43),
    startupTimeoutMs: 750,
    healthCheck: async () => true,
    ...overrides,
  });
}

test("starts from one valid readiness line and keeps secrets out of argv", async (context) => {
  const {directory, script} = fixture(`
    const record = {protocol: 1, url: "http://127.0.0.1:43127", pid: process.pid, runtime_fingerprint: "abc123"};
    process.stdout.write(JSON.stringify(record) + "\\n");
    setInterval(() => {}, 1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const supervisor = supervisorFor(script);
  const ready = await supervisor.start();

  assert.equal(ready.url, "http://127.0.0.1:43127");
  assert.equal(supervisor.readiness.launchToken, "t".repeat(43));
  assert.equal(supervisor.spawnArguments.includes("t".repeat(43)), false);
  assert.equal(supervisor.spawnEnvironment.AGENT_KRONIG_DESKTOP_TOKEN, "t".repeat(43));
  assert.equal(supervisor.spawnEnvironment.AGENT_KRONIG_DATA_DIR, directory);
  assert.equal(supervisor.spawnEnvironment.PYTHONUTF8, "1");
  await supervisor.stop();
  await supervisor.stop();
});

test("rejects malformed readiness and terminates the fixture", async (context) => {
  const {directory, script} = fixture(`
    process.stdout.write("not-json\\n");
    setInterval(() => {}, 1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const supervisor = supervisorFor(script);
  await assert.rejects(supervisor.start(), /readiness/i);
  assert.equal(supervisor.running, false);
});

test("reports early sidecar exit with bounded sanitized diagnostics", async (context) => {
  const {directory, script} = fixture(`
    process.stderr.write("launch-token=secret\\n");
    process.exit(7);
  `);
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const supervisor = supervisorFor(script);
  await assert.rejects(supervisor.start(), /exited.*7/i);
  assert.doesNotMatch(supervisor.diagnostics, /secret/);
});

test("times out and terminates a silent fixture", async (context) => {
  const {directory, script} = fixture("setInterval(() => {}, 1000);");
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const supervisor = supervisorFor(script, {startupTimeoutMs: 80});
  await assert.rejects(supervisor.start(), /timed out/i);
  assert.equal(supervisor.running, false);
});

test("development launch imports the current source tree with host-native paths", () => {
  const projectRoot = path.resolve(os.tmpdir(), "agent-kronig-development");
  const existingPython = path.resolve(os.tmpdir(), "existing-python");
  const launch = resolveBackendLaunch({
    projectRoot,
    platform: process.platform,
    environment: {PYTHONPATH: existingPython},
  });
  const pythonParts = process.platform === "win32"
    ? [".venv", "Scripts", "python.exe"]
    : [".venv", "bin", "python"];
  assert.equal(launch.command, path.join(projectRoot, ...pythonParts));
  assert.deepEqual(launch.args, ["-m", "tcad_agent.desktop.server"]);
  assert.equal(
    launch.environment.PYTHONPATH,
    `${path.join(projectRoot, "src")}${path.delimiter}${existingPython}`,
  );
});

test("stop escalates when a sidecar ignores graceful termination", async (context) => {
  const {directory, script} = fixture(`
    process.on("SIGTERM", () => {});
    const record = {protocol: 1, url: "http://127.0.0.1:43127", pid: process.pid, runtime_fingerprint: "abc123"};
    process.stdout.write(JSON.stringify(record) + "\\n");
    setInterval(() => {}, 1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const supervisor = supervisorFor(script);
  context.after(async () => { await supervisor.stop(); });
  await supervisor.start();
  const pid = supervisor.readiness.pid;
  await supervisor.stop();
  await new Promise((resolve) => setTimeout(resolve, 50));
  assert.throws(() => process.kill(pid, 0), /ESRCH/);
});

test("concurrent shutdown callers await the same process-tree cleanup", async (context) => {
  const {directory, script} = fixture(`
    process.on("SIGTERM", () => {});
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123"}) + "\\n");
    setInterval(() => {}, 1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  const supervisor = supervisorFor(script);
  await supervisor.start();
  let firstFinished = false;
  const first = supervisor.stop().then(() => {firstFinished = true;});
  await supervisor.stop();
  assert.equal(firstFinished, true, "a second quit must not exit before cleanup finishes");
  await first;
});

test("reports a backend exit after successful readiness", async (context) => {
  const {directory, script} = fixture(`
    const record = {protocol: 1, url: "http://127.0.0.1:43127", pid: process.pid, runtime_fingerprint: "abc123"};
    process.stdout.write(JSON.stringify(record) + "\\n");
    setTimeout(() => process.exit(9), 20);
  `);
  context.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const supervisor = supervisorFor(script);
  const failure = new Promise((resolve) => supervisor.once("unexpected-exit", resolve));
  await supervisor.start();
  const event = await failure;
  assert.equal(event.code, 9);
  assert.equal(supervisor.readiness, null);
});

test("restart cannot acquire ownership while cleanup is pending", async (context) => {
  const {directory, script} = fixture(`
    process.on("SIGTERM", () => {});
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123"}) + "\\n");
    setInterval(() => {}, 1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  const supervisor = supervisorFor(script);
  await supervisor.start();
  const stopping = supervisor.stop();
  await assert.rejects(supervisor.start(), /cleanup|already.*started/i);
  await stopping;
  await supervisor.start();
  await supervisor.stop();
});

test("a stopped startup cannot publish stale readiness after its health check", async (context) => {
  const {directory, script} = fixture(`
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123"}) + "\\n");
    setInterval(() => {},1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  let healthStarted;
  const started = new Promise((resolve) => {healthStarted = resolve;});
  let releaseHealth;
  const health = new Promise((resolve) => {releaseHealth = resolve;});
  const supervisor = supervisorFor(script, {healthCheck:() => {healthStarted(); return health;}});
  const launching = supervisor.start();
  await started;
  await supervisor.stop();
  releaseHealth(true);
  await assert.rejects(launching, /interrupted|shutdown/);
  assert.equal(supervisor.readiness, null);
});

test("failure of an older startup cannot stop its healthy replacement", async (context) => {
  const {directory, script} = fixture(`
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123"}) + "\\n");
    setInterval(() => {},1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  let healthStarted;
  const started = new Promise((resolve) => {healthStarted = resolve;});
  let releaseOldHealth;
  const oldHealth = new Promise((resolve) => {releaseOldHealth = resolve;});
  let checks = 0;
  const supervisor = supervisorFor(script, {healthCheck:() => {
    checks += 1;
    if (checks === 1) {healthStarted(); return oldHealth;}
    return Promise.resolve(true);
  }});
  context.after(async () => {await supervisor.stop();});
  const oldStartup = supervisor.start();
  await started;
  await supervisor.stop();
  const replacement = await supervisor.start();
  const rejected = assert.rejects(oldStartup, /interrupted|shutdown/);
  releaseOldHealth(true);
  await rejected;
  assert.equal(supervisor.running, true, "stale startup cleanup killed the new generation");
  assert.equal(supervisor.readiness, replacement);
  assert.equal(supervisor.child.pid, replacement.pid);
  assert.doesNotThrow(() => process.kill(replacement.pid, 0));
});

test("a failed cleanup retains ownership so stop can be retried", async (context) => {
  const {directory, script} = fixture(`
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123"}) + "\\n");
    setInterval(() => {}, 1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  let denyCleanup = true;
  const supervisor = supervisorFor(script, {execFileImpl: (...args) => {
    if (args[0] === "taskkill.exe" && denyCleanup) {
      args.at(-1)(Object.assign(new Error("cleanup denied"), {code:"EPERM"}));
    } else {
      execFile(...args);
    }
  }});
  await supervisor.start();
  const child = supervisor.child;
  const originalKill = process.kill;
  if (process.platform !== "win32") {
    process.kill = () => {throw Object.assign(new Error("cleanup denied"), {code:"EPERM"});};
  }
  try {
    await assert.rejects(supervisor.stop(), /cleanup denied/);
    assert.equal(supervisor.child, child, "failed cleanup must retain the process identity");
    await assert.rejects(supervisor.start(), /cleanup|already.*started/i);
  } finally {
    denyCleanup = false;
    process.kill = originalKill;
    await supervisor.stop();
  }
  assert.throws(() => process.kill(child.pid, 0), /ESRCH/);
});

test("Windows forced-cleanup failure retains a real backend for retry", async (context) => {
  const {directory, script} = fixture(`
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123"}) + "\\n");
    setInterval(() => {},1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  let denied = true;
  let child;
  const supervisor = supervisorFor(script, {execFileImpl: (command, args, options, callback) => {
    assert.equal(command, "taskkill.exe");
    assert.deepEqual(args.slice(0, 3), ["/PID", String(child.pid), "/T"]);
    if (denied) callback(Object.assign(new Error("cleanup denied"), {code:"EPERM"}));
    else {child.kill(); callback(null);}
  }});
  await supervisor.start();
  child = supervisor.child;
  const platform = Object.getOwnPropertyDescriptor(process, "platform");
  Object.defineProperty(process, "platform", {...platform, value:"win32"});
  try {
    await assert.rejects(supervisor.stop(), /cleanup denied/);
    assert.equal(supervisor.child, child);
    assert.equal(child.exitCode, null);
    denied = false;
    await supervisor.stop();
    assert.equal(supervisor.child, null);
  } finally {
    Object.defineProperty(process, "platform", platform);
    await supervisor.stop();
  }
});

test("cleanup escalates for a resistant worker even after the backend exits", async (context) => {
  const {directory, script} = fixture(`
    const {spawn} = require("node:child_process");
    const child = spawn(process.execPath, ["-e", "process.on('SIGTERM', () => {}); process.stdout.write('ready'); setInterval(() => {},1000)"], {stdio:["ignore","pipe","ignore"]});
    child.stdout.once("data", () => {
      process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"worker_" + child.pid}) + "\\n");
    });
    setInterval(() => {}, 1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  const supervisor = supervisorFor(script);
  const ready = await supervisor.start();
  const pid = Number(ready.runtime_fingerprint.replace("worker_", ""));
  context.after(() => {try {process.kill(pid, "SIGKILL");} catch {}});
  await supervisor.stop();
  assert.throws(() => process.kill(pid, 0), /ESRCH/);
});

test("stop waits for independent worker cleanup confirmation", async (context) => {
  const {directory, script} = fixture(`
    const {spawn} = require("node:child_process");
    const monitor = spawn(process.execPath, ["-e", "setTimeout(() => {}, 500)"], {detached:true,stdio:"ignore"});
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123",owner_monitor_pid:monitor.pid}) + "\\n");
    setInterval(() => {},1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  const supervisor = supervisorFor(script);
  context.after(async () => {await supervisor.stop();});
  const readiness = await supervisor.start();
  assert.ok(readiness.owner_monitor_pid, "ownership completion PID must survive the handshake");
  await supervisor.stop();
  assert.throws(() => process.kill(readiness.owner_monitor_pid, 0), /ESRCH/);
});

test("signal-zero success cannot keep a confirmed empty process group owned",
  {skip:process.platform === "win32"}, async (context) => {
  const {directory, script} = fixture(`
    process.stdout.write(JSON.stringify({protocol:1,url:"http://127.0.0.1:43127",pid:process.pid,runtime_fingerprint:"abc123"}) + "\\n");
    setInterval(() => {},1000);
  `);
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  const supervisor = supervisorFor(script);
  const ready = await supervisor.start();
  const originalKill = process.kill;
  // Linux may successfully probe unreaped zombies. The real process table is
  // authoritative about whether any executable worker remains in the group.
  process.kill = (pid, signal) => pid === -ready.pid && signal === 0
    ? true : originalKill(pid, signal);
  try {
    await supervisor.stop();
    assert.equal(supervisor.child, null);
  } finally {
    process.kill = originalKill;
    await supervisor.stop();
  }
});

test("stops descendants in the owned process group", async (context) => {
  const childRecord = path.join(os.tmpdir(), `agent-kronig-child-${process.pid}-${Date.now()}`);
  const {directory, script} = fixture(`
    const fs = require("node:fs");
    const {spawn} = require("node:child_process");
    const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], {stdio: "ignore"});
    fs.writeFileSync(${JSON.stringify(childRecord)}, String(child.pid));
    const record = {protocol: 1, url: "http://127.0.0.1:43127", pid: process.pid, runtime_fingerprint: "abc123"};
    process.stdout.write(JSON.stringify(record) + "\\n");
    setInterval(() => {}, 1000);
  `);
  context.after(() => {
    fs.rmSync(directory, {recursive: true, force: true});
    fs.rmSync(childRecord, {force: true});
  });
  const supervisor = supervisorFor(script);
  await supervisor.start();
  const descendantPid = Number(fs.readFileSync(childRecord, "utf8"));
  await supervisor.stop();
  assert.throws(() => process.kill(descendantPid, 0), /ESRCH/);
});
