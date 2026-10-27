const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {DesktopSettingsStore} = require("../src/settings-store");

function temporaryDirectory() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "agent-kronig-settings-"));
}

function protectedStorage() {
  return {
    isEncryptionAvailable: () => true,
    getSelectedStorageBackend: () => "keychain",
    encryptString: (value) => Buffer.from([...value].reverse().join(""), "utf8"),
    decryptString: (value) => [...value.toString("utf8")].reverse().join(""),
  };
}

test("stores non-secret settings and protects the Bedrock credential", () => {
  const dataDir = temporaryDirectory();
  const store = new DesktopSettingsStore({
    dataDir,
    safeStorage: protectedStorage(),
    platform: "darwin",
  });

  const state = store.save({
    region: "ap-south-1",
    model: "bedrock/global.anthropic.claude-sonnet-4-6",
    reasoningEffort: "medium",
    bedrockApiKey: "test-secret-value",
  });

  assert.equal(state.hasBedrockCredential, true);
  assert.equal(state.credentialStorage, "protected");
  assert.equal(JSON.stringify(state).includes("test-secret-value"), false);
  assert.equal(fs.readFileSync(path.join(dataDir, "settings.json"), "utf8").includes("test-secret-value"), false);
  assert.equal(fs.readFileSync(path.join(dataDir, "secrets.bin"), "utf8").includes("test-secret-value"), false);

  const environment = store.environment();
  assert.equal(environment.AWS_BEARER_TOKEN_BEDROCK, "test-secret-value");
  assert.equal(environment.AWS_REGION_NAME, "ap-south-1");
  assert.equal(environment.LLM_MODEL, "bedrock/global.anthropic.claude-sonnet-4-6");
  assert.equal(environment.TCAD_REASONING_EFFORT, "medium");
});

test("keeps a credential in memory when Linux protected storage is unavailable", () => {
  const dataDir = temporaryDirectory();
  const store = new DesktopSettingsStore({
    dataDir,
    safeStorage: {
      isEncryptionAvailable: () => true,
      getSelectedStorageBackend: () => "basic_text",
      encryptString: () => { throw new Error("must not persist"); },
      decryptString: () => { throw new Error("must not persist"); },
    },
    platform: "linux",
  });

  const state = store.save({
    region: "us-east-1",
    model: "bedrock/example",
    reasoningEffort: "low",
    bedrockApiKey: "session-only",
  });

  assert.equal(state.credentialStorage, "session");
  assert.equal(store.environment().AWS_BEARER_TOKEN_BEDROCK, "session-only");
  assert.equal(fs.existsSync(path.join(dataDir, "secrets.bin")), false);
});

test("never returns secrets and validates every setting", () => {
  const store = new DesktopSettingsStore({
    dataDir: temporaryDirectory(),
    safeStorage: protectedStorage(),
    platform: "win32",
  });

  assert.throws(() => store.save({region: "", model: "bedrock/example", reasoningEffort: "low"}), /region/i);
  assert.throws(() => store.save({region: "us-east-1", model: "invalid", reasoningEffort: "low"}), /model/i);
  assert.throws(() => store.save({region: "us-east-1", model: "bedrock/example", reasoningEffort: "extreme"}), /reasoning/i);

  const state = store.save({
    region: "us-east-1",
    model: "bedrock/example",
    reasoningEffort: "high",
    bedrockApiKey: "hidden",
  });
  assert.equal("bedrockApiKey" in state, false);
  const cleared = store.save({
    region: "us-east-1",
    model: "bedrock/example",
    reasoningEffort: "high",
    clearCredential: true,
  });
  assert.equal(cleared.hasBedrockCredential, false);
  assert.equal("AWS_BEARER_TOKEN_BEDROCK" in store.environment(), false);
});

test("uses managed launch configuration until the researcher saves overrides", () => {
  const store = new DesktopSettingsStore({
    dataDir: temporaryDirectory(),
    safeStorage: protectedStorage(),
    platform: "linux",
    baseEnvironment: {
      AWS_REGION_NAME: "eu-west-1",
      LLM_MODEL: "bedrock/managed-profile",
      TCAD_REASONING_EFFORT: "high",
      AWS_BEARER_TOKEN_BEDROCK: "managed-secret",
    },
  });

  assert.deepEqual(store.environment(), {
    AWS_REGION_NAME: "eu-west-1",
    LLM_MODEL: "bedrock/managed-profile",
    TCAD_REASONING_EFFORT: "high",
    AWS_BEARER_TOKEN_BEDROCK: "managed-secret",
  });
  assert.equal(store.getPublicSettings().hasBedrockCredential, true);
});

const MODEL = {region: "us-east-1", model: "bedrock/example", reasoningEffort: "low"};

test("stores the Sentaurus connection and keeps the HPC password out of every plain file", () => {
  const dataDir = temporaryDirectory();
  const store = new DesktopSettingsStore({dataDir, safeStorage: protectedStorage(), platform: "darwin"});

  const state = store.save({
    ...MODEL,
    simulator: {host: "192.0.2.10", user: "alice", release: "O-2018.06-SP2", port: "22"},
    extraEnvironment: {TCAD_BACKEND: "sentaurus"},
    hpcPassword: "hpc-secret-value",
  });

  assert.equal(state.hasHpcPassword, true);
  assert.equal(JSON.stringify(state).includes("hpc-secret-value"), false);
  for (const name of ["settings.json", "simulator-secrets.bin", "secrets.bin"]) {
    const file = path.join(dataDir, name);
    if (fs.existsSync(file)) assert.equal(fs.readFileSync(file, "utf8").includes("hpc-secret-value"), false);
  }
  const environment = store.environment();
  assert.equal(environment.TCAD_HPSC_HOST, "192.0.2.10");
  assert.equal(environment.TCAD_HPSC_USER, "alice");
  assert.equal(environment.TCAD_SENTAURUS_VERSION, "O-2018.06-SP2");
  assert.equal(environment.TCAD_SENTAURUS_RUNNER, "ssh");
  assert.equal(environment.TCAD_HPSC_PASSWORD, "hpc-secret-value");
  assert.equal(environment.TCAD_BACKEND, "sentaurus");
  assert.equal("TCAD_SENTAURUS_SETUP" in environment, false);
});

test("a save that omits the simulator sections keeps them, and fields can be cleared", () => {
  const store = new DesktopSettingsStore({
    dataDir: temporaryDirectory(),
    safeStorage: protectedStorage(),
    platform: "darwin",
  });
  store.save({...MODEL, simulator: {host: "hpc.example.edu", user: "bob", release: "V-2023.12"}, hpcPassword: "pw"});

  store.save({...MODEL});
  assert.equal(store.environment().TCAD_HPSC_HOST, "hpc.example.edu");
  assert.equal(store.environment().TCAD_HPSC_PASSWORD, "pw");

  store.save({...MODEL, simulator: {host: ""}, clearHpcPassword: true});
  const environment = store.environment();
  assert.equal("TCAD_HPSC_HOST" in environment, false);
  assert.equal("TCAD_SENTAURUS_RUNNER" in environment, false);
  assert.equal("TCAD_HPSC_PASSWORD" in environment, false);
  assert.equal(store.environment().TCAD_HPSC_USER, "bob");
});

test("validates simulator fields and refuses reserved or malformed extra variables", () => {
  const store = new DesktopSettingsStore({
    dataDir: temporaryDirectory(),
    safeStorage: protectedStorage(),
    platform: "darwin",
  });
  assert.throws(() => store.save({...MODEL, simulator: {host: "bad host; rm"}}), /HPC address/);
  assert.throws(() => store.save({...MODEL, simulator: {port: "70000"}}), /port/i);
  assert.throws(() => store.save({...MODEL, simulator: {setup: "a\nb"}}), /Setup command/);
  assert.throws(() => store.save({...MODEL, extraEnvironment: {PATH: "x"}}), /TCAD_NAME/);
  assert.throws(() => store.save({...MODEL, extraEnvironment: {TCAD_HPSC_HOST: "x"}}), /own field/);
  assert.throws(() => store.save({...MODEL, extraEnvironment: {TCAD_HPSC_PASSWORD: "x"}}), /own field/);
  assert.throws(() => store.save({...MODEL, extraEnvironment: {TCAD_X: "a\nb"}}), /invalid value/);
  assert.throws(() => store.save({...MODEL, hpcPassword: "a\nb"}), /password/i);
});

test("keeps the HPC password in memory when protected storage is unavailable", () => {
  const dataDir = temporaryDirectory();
  const store = new DesktopSettingsStore({
    dataDir,
    safeStorage: {
      isEncryptionAvailable: () => true,
      getSelectedStorageBackend: () => "basic_text",
      encryptString: () => { throw new Error("must not persist"); },
      decryptString: () => { throw new Error("must not persist"); },
    },
    platform: "linux",
  });
  store.save({...MODEL, simulator: {host: "h", user: "u"}, hpcPassword: "session-pw"});
  assert.equal(store.environment().TCAD_HPSC_PASSWORD, "session-pw");
  assert.equal(fs.existsSync(path.join(dataDir, "simulator-secrets.bin")), false);
});

test("seeds the simulator fields from the launch environment", () => {
  const store = new DesktopSettingsStore({
    dataDir: temporaryDirectory(),
    safeStorage: protectedStorage(),
    platform: "linux",
    baseEnvironment: {TCAD_HPSC_HOST: "10.0.0.5", TCAD_HPSC_USER: "carol"},
  });
  const settings = store.getPublicSettings();
  assert.equal(settings.simulator.host, "10.0.0.5");
  assert.equal(settings.simulator.user, "carol");
});