"use strict";

const fs = require("node:fs");
const path = require("node:path");

const DEFAULTS = Object.freeze({
  region: "ap-south-1",
  model: "bedrock/global.anthropic.claude-sonnet-4-6",
  reasoningEffort: "medium",
});
const REASONING_EFFORTS = new Set(["low", "medium", "high"]);
const {
  normalizeExtra,
  normalizeSimulator,
  simulatorEnvironment,
  simulatorFromEnvironment,
} = require("./simulator-settings");

function validatedText(value, label, pattern, maximum = 256) {
  if (typeof value !== "string" || !value.trim() || value.length > maximum) {
    throw new Error(`${label} is required and must be at most ${maximum} characters`);
  }
  const result = value.trim();
  if (!pattern.test(result)) throw new Error(`${label} is invalid`);
  return result;
}

function writePrivateFile(filePath, value) {
  const temporary = `${filePath}.tmp`;
  fs.writeFileSync(temporary, value, {mode: 0o600});
  fs.renameSync(temporary, filePath);
  fs.chmodSync(filePath, 0o600);
}

class DesktopSettingsStore {
  constructor({dataDir, safeStorage, platform = process.platform, baseEnvironment = {}}) {
    this.dataDir = path.resolve(dataDir);
    this.safeStorage = safeStorage;
    this.platform = platform;
    this.settingsPath = path.join(this.dataDir, "settings.json");
    this.secretsPath = path.join(this.dataDir, "secrets.bin");
    this.hpcSecretsPath = path.join(this.dataDir, "simulator-secrets.bin");
    this.sessionCredential = null;
    this.sessionHpcPassword = null;
    this.defaults = {...DEFAULTS};
    this.defaultSimulator = simulatorFromEnvironment(baseEnvironment);
    try {
      if (baseEnvironment.AWS_REGION_NAME) {
        this.defaults.region = validatedText(
          baseEnvironment.AWS_REGION_NAME,
          "Region",
          /^[a-z0-9-]+$/,
        );
      }
      if (baseEnvironment.LLM_MODEL) {
        this.defaults.model = validatedText(
          baseEnvironment.LLM_MODEL,
          "Model",
          /^bedrock\/[A-Za-z0-9._:/-]+$/,
        );
      }
      if (REASONING_EFFORTS.has(baseEnvironment.TCAD_REASONING_EFFORT)) {
        this.defaults.reasoningEffort = baseEnvironment.TCAD_REASONING_EFFORT;
      }
    } catch {
      this.defaults = {...DEFAULTS};
    }
    this.baseCredential = (
      typeof baseEnvironment.AWS_BEARER_TOKEN_BEDROCK === "string"
      && baseEnvironment.AWS_BEARER_TOKEN_BEDROCK
      && !/[\r\n\0]/.test(baseEnvironment.AWS_BEARER_TOKEN_BEDROCK)
    ) ? baseEnvironment.AWS_BEARER_TOKEN_BEDROCK : null;
  }

  #ensureDirectory() {
    fs.mkdirSync(this.dataDir, {recursive: true, mode: 0o700});
  }

  #persistentProtectionAvailable() {
    if (!this.safeStorage?.isEncryptionAvailable()) return false;
    if (this.platform !== "linux") return true;
    return this.safeStorage.getSelectedStorageBackend?.() !== "basic_text";
  }

  #readSettings() {
    try {
      const value = JSON.parse(fs.readFileSync(this.settingsPath, "utf8"));
      if (!value || value.version !== 1) return this.#withDefaultSimulator({...this.defaults});
      return {
        region: validatedText(value.region, "Region", /^[a-z0-9-]+$/),
        model: validatedText(value.model, "Model", /^bedrock\/[A-Za-z0-9._:/-]+$/),
        reasoningEffort: REASONING_EFFORTS.has(value.reasoningEffort)
          ? value.reasoningEffort
          : this.defaults.reasoningEffort,
        ...this.#readSimulator(value),
      };
    } catch {
      return this.#withDefaultSimulator({...this.defaults});
    }
  }

  #withDefaultSimulator(settings) {
    return {...settings, simulator: {...this.defaultSimulator}, extraEnvironment: {}};
  }

  #readSimulator(value) {
    // A damaged simulator section must not discard the model settings next to it.
    try {
      return {
        simulator: normalizeSimulator(value.simulator, this.defaultSimulator),
        extraEnvironment: normalizeExtra(value.extraEnvironment, {}),
      };
    } catch {
      return {simulator: {...this.defaultSimulator}, extraEnvironment: {}};
    }
  }

  #persistHpcPassword(password) {
    if (this.#persistentProtectionAvailable()) {
      writePrivateFile(this.hpcSecretsPath, this.safeStorage.encryptString(password));
      this.sessionHpcPassword = null;
    } else {
      fs.rmSync(this.hpcSecretsPath, {force: true});
      this.sessionHpcPassword = password;
    }
  }

  #readHpcPassword() {
    if (this.sessionHpcPassword) return this.sessionHpcPassword;
    if (!this.#persistentProtectionAvailable()) return null;
    try {
      return this.safeStorage.decryptString(fs.readFileSync(this.hpcSecretsPath));
    } catch {
      return null;
    }
  }

  #readCredential() {
    if (this.sessionCredential) return this.sessionCredential;
    if (!this.#persistentProtectionAvailable()) return this.baseCredential;
    try {
      return this.safeStorage.decryptString(fs.readFileSync(this.secretsPath));
    } catch {
      return this.baseCredential;
    }
  }

  getPublicSettings() {
    const settings = this.#readSettings();
    return Object.freeze({
      ...settings,
      hasBedrockCredential: Boolean(this.#readCredential()),
      hasHpcPassword: Boolean(this.#readHpcPassword()),
      credentialStorage: this.baseCredential && !fs.existsSync(this.secretsPath)
        ? "managed"
        : (this.#persistentProtectionAvailable() ? "protected" : "session"),
    });
  }

  environment() {
    const settings = this.#readSettings();
    const credential = this.#readCredential();
    return {
      AWS_REGION_NAME: settings.region,
      LLM_MODEL: settings.model,
      TCAD_REASONING_EFFORT: settings.reasoningEffort,
      ...(credential ? {AWS_BEARER_TOKEN_BEDROCK: credential} : {}),
      ...simulatorEnvironment(
        settings.simulator,
        settings.extraEnvironment,
        this.#readHpcPassword(),
      ),
    };
  }

  save(input) {
    if (!input || typeof input !== "object" || Array.isArray(input)) {
      throw new Error("Settings payload is invalid");
    }
    const region = validatedText(input.region, "Region", /^[a-z0-9-]+$/);
    const model = validatedText(input.model, "Model", /^bedrock\/[A-Za-z0-9._:/-]+$/);
    if (!REASONING_EFFORTS.has(input.reasoningEffort)) {
      throw new Error("Reasoning effort must be low, medium, or high");
    }
    const credential = input.bedrockApiKey;
    if (credential !== undefined && credential !== "") {
      if (typeof credential !== "string" || credential.length > 8192 || /[\r\n\0]/.test(credential)) {
        throw new Error("Bedrock API key is invalid");
      }
    }

    // Omitted sections keep what is stored, so older callers do not erase simulator settings.
    const stored = this.#readSettings();
    const simulator = normalizeSimulator(input.simulator, stored.simulator);
    const extraEnvironment = normalizeExtra(input.extraEnvironment, stored.extraEnvironment);
    const hpcPassword = input.hpcPassword;
    if (hpcPassword !== undefined && hpcPassword !== "") {
      if (typeof hpcPassword !== "string" || hpcPassword.length > 1024 || /[\r\n\0]/.test(hpcPassword)) {
        throw new Error("HPC password is invalid");
      }
    }

    this.#ensureDirectory();
    writePrivateFile(
      this.settingsPath,
      `${JSON.stringify({
        version: 1,
        region,
        model,
        reasoningEffort: input.reasoningEffort,
        simulator,
        extraEnvironment,
      }, null, 2)}\n`,
    );

    if (input.clearHpcPassword === true) {
      this.sessionHpcPassword = null;
      fs.rmSync(this.hpcSecretsPath, {force: true});
    } else if (hpcPassword) {
      this.#persistHpcPassword(hpcPassword);
    }

    if (input.clearCredential === true) {
      this.sessionCredential = null;
      fs.rmSync(this.secretsPath, {force: true});
    } else if (credential) {
      if (this.#persistentProtectionAvailable()) {
        writePrivateFile(this.secretsPath, this.safeStorage.encryptString(credential));
        this.sessionCredential = null;
      } else {
        fs.rmSync(this.secretsPath, {force: true});
        this.sessionCredential = credential;
      }
    }
    return this.getPublicSettings();
  }
}

module.exports = {DEFAULTS, DesktopSettingsStore};
