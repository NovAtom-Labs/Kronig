"use strict";

// Sentaurus-over-SSH connection settings. Each field maps to one environment variable that the
// Python backend already reads, so the desktop only writes what a .env file would hold.
const FIELDS = Object.freeze([
  {key: "host", env: "TCAD_HPSC_HOST", label: "HPC address", pattern: /^[A-Za-z0-9._:-]{1,253}$/},
  {key: "port", env: "TCAD_HPSC_PORT", label: "SSH port", pattern: /^[0-9]{1,5}$/},
  {key: "user", env: "TCAD_HPSC_USER", label: "HPC user", pattern: /^[A-Za-z0-9._-]{1,64}$/},
  {key: "release", env: "TCAD_SENTAURUS_VERSION", label: "Sentaurus release", pattern: /^[A-Za-z0-9._-]{1,32}$/},
  {key: "remoteRoot", env: "TCAD_HPSC_REMOTE_ROOT", label: "Remote work folder", pattern: /^[~A-Za-z0-9._/+-]{1,512}$/},
  {key: "setup", env: "TCAD_SENTAURUS_SETUP", label: "Setup command", pattern: /^[^\r\n\0]{1,500}$/},
  {key: "bin", env: "TCAD_SENTAURUS_BIN", label: "Sentaurus bin folder", pattern: /^[A-Za-z0-9._/+~-]{1,512}$/},
  {key: "license", env: "TCAD_SENTAURUS_LICENSE", label: "License server", pattern: /^[A-Za-z0-9@._:,/-]{1,512}$/},
]);

// Managed by a dedicated field (or a secret) so they cannot also be set as free-form variables.
const RESERVED = new Set([
  ...FIELDS.map((field) => field.env),
  "TCAD_SENTAURUS_RUNNER",
  "TCAD_HPSC_PASSWORD",
]);
const EXTRA_NAME = /^TCAD_[A-Z0-9_]{1,64}$/;
const MAXIMUM_EXTRA = 32;

function emptySimulator() {
  return Object.fromEntries(FIELDS.map((field) => [field.key, ""]));
}

function normalizeSimulator(input, fallback = emptySimulator()) {
  if (input === undefined) return {...fallback};
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Simulator settings are invalid");
  }
  const result = {};
  for (const field of FIELDS) {
    const raw = input[field.key] === undefined ? fallback[field.key] : input[field.key];
    const value = typeof raw === "string" ? raw.trim() : "";
    if (value && !field.pattern.test(value)) throw new Error(`${field.label} is invalid`);
    result[field.key] = value;
  }
  if (result.port && (Number(result.port) < 1 || Number(result.port) > 65535)) {
    throw new Error("SSH port is invalid");
  }
  return result;
}

function normalizeExtra(input, fallback = {}) {
  if (input === undefined) return {...fallback};
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("Extra environment variables are invalid");
  }
  const entries = Object.entries(input);
  if (entries.length > MAXIMUM_EXTRA) {
    throw new Error(`At most ${MAXIMUM_EXTRA} extra environment variables are allowed`);
  }
  const result = {};
  for (const [name, value] of entries) {
    if (!EXTRA_NAME.test(name)) throw new Error(`${name} must look like TCAD_NAME`);
    if (RESERVED.has(name)) throw new Error(`${name} has its own field and cannot be set here`);
    if (typeof value !== "string" || value.length > 1024 || /[\r\n\0]/.test(value)) {
      throw new Error(`${name} has an invalid value`);
    }
    result[name] = value;
  }
  return result;
}

function simulatorEnvironment(simulator, extra, password) {
  const environment = {};
  for (const field of FIELDS) {
    if (simulator[field.key]) environment[field.env] = simulator[field.key];
  }
  // The SSH pathway is selected as soon as a host and login are saved.
  if (simulator.host && simulator.user) environment.TCAD_SENTAURUS_RUNNER = "ssh";
  if (password) environment.TCAD_HPSC_PASSWORD = password;
  return {...extra, ...environment};
}

function simulatorFromEnvironment(baseEnvironment) {
  const result = emptySimulator();
  for (const field of FIELDS) {
    const value = baseEnvironment[field.env];
    if (typeof value === "string" && field.pattern.test(value.trim())) result[field.key] = value.trim();
  }
  return result;
}

module.exports = {
  FIELDS,
  normalizeExtra,
  normalizeSimulator,
  simulatorEnvironment,
  simulatorFromEnvironment,
};
