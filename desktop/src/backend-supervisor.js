"use strict";

const {execFile, spawn} = require("node:child_process");
const {EventEmitter} = require("node:events");
const path = require("node:path");

const {MAX_READINESS_BYTES, parseReadinessLine} = require("./readiness");

const MAX_DIAGNOSTIC_BYTES = 8 * 1024;

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function sanitizeDiagnostics(value) {
  return value
    .replace(/(token|password|secret|api[-_]?key)\s*[:=]\s*[^\s]+/gi, "$1=[REDACTED]")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .slice(-MAX_DIAGNOSTIC_BYTES);
}

function developmentPython(projectRoot, platform = process.platform) {
  const relative = platform === "win32"
    ? [".venv", "Scripts", "python.exe"]
    : [".venv", "bin", "python"];
  return path.join(projectRoot, ...relative);
}

function resolveBackendLaunch({
  isPackaged = false,
  resourcesPath = process.resourcesPath,
  projectRoot = path.resolve(__dirname, "../.."),
  platform = process.platform,
  environment = process.env,
} = {}) {
  if (isPackaged) {
    const executable = platform === "win32" ? "agent-kronig-backend.exe" : "agent-kronig-backend";
    return {
      command: path.join(resourcesPath, "sidecars", "backend", executable),
      args: [],
    };
  }
  return {
    command: environment.AGENT_KRONIG_PYTHON || developmentPython(projectRoot, platform),
    args: ["-m", "tcad_agent.desktop.server"],
    environment: {
      PYTHONPATH: [path.join(projectRoot, "src"), environment.PYTHONPATH]
        .filter(Boolean)
        .join(path.delimiter),
    },
  };
}

async function defaultHealthCheck(origin, deadline) {
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${origin}/health`, {cache: "no-store"});
      if (response.ok) return true;
    } catch {
      // Uvicorn can still be entering its serve loop after emitting readiness.
    }
    await delay(50);
  }
  return false;
}

class BackendSupervisor extends EventEmitter {
  constructor(options = {}) {
    super();
    const launch = options.command
      ? {command: options.command, args: options.args || []}
      : resolveBackendLaunch(options);
    this.command = launch.command;
    this.args = [...launch.args];
    this.dataDir = path.resolve(options.dataDir);
    this.devsimRunner = options.devsimRunner ? path.resolve(options.devsimRunner) : null;
    this.tokenFactory = options.tokenFactory;
    this.startupTimeoutMs = options.startupTimeoutMs || 15000;
    this.healthCheck = options.healthCheck || defaultHealthCheck;
    this.spawnImpl = options.spawnImpl || spawn;
    this.execFileImpl = options.execFileImpl || execFile;
    this.environment = {
      ...(options.environment || process.env),
      ...(launch.environment || {}),
    };
    this.child = null;
    this.readiness = null;
    this.diagnostics = "";
    this.spawnArguments = [];
    this.spawnEnvironment = {};
    this.stopping = false;
    this.stopPromise = null;
    this.ownerMonitorPid = null;
  }

  get running() {
    return Boolean(this.child && this.child.exitCode === null && this.child.signalCode === null);
  }

  async start() {
    if (this.stopPromise || this.stopping) throw new Error("Backend cleanup is still pending");
    if (this.child) throw new Error("Backend supervisor has already been started");
    const token = this.tokenFactory();
    const environment = {
      ...this.environment,
      AGENT_KRONIG_DESKTOP_HOST: "127.0.0.1",
      AGENT_KRONIG_DESKTOP_PORT: "0",
      AGENT_KRONIG_DESKTOP_TOKEN: token,
      AGENT_KRONIG_DATA_DIR: this.dataDir,
      AGENT_KRONIG_DESKTOP_OWNER_PIPE: "1",
      PYTHONUNBUFFERED: "1",
      PYTHONUTF8: "1",
    };
    if (this.devsimRunner) environment.AGENT_KRONIG_DEVSIM_RUNNER = this.devsimRunner;
    this.spawnArguments = [...this.args];
    this.spawnEnvironment = {...environment};

    const child = this.spawnImpl(this.command, this.args, {
      env: environment,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
      detached: process.platform !== "win32",
    });
    this.child = child;
    child.once("exit", (code, signal) => {
      if (this.child !== child || this.stopping || !this.readiness) return;
      this.readiness = null;
      // Retain the owned group identity until descendants have been cleaned up.
      this.emit("unexpected-exit", Object.freeze({code, signal}));
    });

    try {
      const readiness = await this.#waitForReadiness(child);
      this.ownerMonitorPid = readiness.owner_monitor_pid || null;
      const healthy = await this.healthCheck(readiness.url, Date.now() + this.startupTimeoutMs);
      if (!healthy) throw new Error("Backend health check timed out");
      if (this.child !== child || this.stopping || this.stopPromise
        || child.exitCode !== null || child.signalCode !== null) {
        throw new Error("Backend startup was interrupted by shutdown");
      }
      this.readiness = Object.freeze({...readiness, launchToken: token});
      return this.readiness;
    } catch (error) {
      if (this.child === child) await this.stop();
      throw error;
    }
  }

  #waitForReadiness(child) {
    return new Promise((resolve, reject) => {
      let stdout = Buffer.alloc(0);
      let settled = false;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        callback(value);
      };
      const timer = setTimeout(
        () => finish(reject, new Error("Backend readiness timed out")),
        this.startupTimeoutMs,
      );

      child.stderr.on("data", (chunk) => {
        this.diagnostics = sanitizeDiagnostics(this.diagnostics + chunk.toString("utf8"));
      });
      child.stdout.on("data", (chunk) => {
        if (settled) return;
        stdout = Buffer.concat([stdout, chunk]);
        if (stdout.length > MAX_READINESS_BYTES) {
          finish(reject, new Error("Backend readiness output exceeded the size limit"));
          return;
        }
        const newline = stdout.indexOf(0x0a);
        if (newline === -1) return;
        try {
          finish(resolve, parseReadinessLine(stdout.subarray(0, newline).toString("utf8")));
        } catch (error) {
          finish(reject, error);
        }
      });
      child.once("error", (error) => {
        finish(reject, new Error(`Backend could not be started: ${error.message}`));
      });
      child.once("exit", (code, signal) => {
        if (settled) return;
        const suffix = code === null ? `signal ${signal}` : `code ${code}`;
        finish(reject, new Error(`Backend exited before readiness with ${suffix}`));
      });
    });
  }

  stop() {
    if (this.stopPromise) return this.stopPromise;
    this.stopPromise = this.#stopOwnedTree().finally(() => {this.stopPromise = null;});
    return this.stopPromise;
  }

  async #stopOwnedTree() {
    const child = this.child;
    this.readiness = null;
    if (!child) return;

    this.stopping = true;
    try {
      await this.#signalTree(child, "SIGTERM");
      if (!await this.#waitForTreeExit(child, 750)) {
        await this.#signalTree(child, "SIGKILL");
        if (!await this.#waitForTreeExit(child, 750)) {
          throw new Error("Backend process tree did not terminate");
        }
      }
      child.stdin?.destroy();
      if (this.child === child) this.child = null;
      this.ownerMonitorPid = null;
    } finally {
      this.stopping = false;
    }
  }

  async #waitForTreeExit(child, timeout) {
    const deadline = Date.now() + timeout;
    do {
      const backendExited = child.exitCode !== null || child.signalCode !== null;
      let groupAlive = false;
      if (process.platform !== "win32" && Number.isInteger(child.pid)) {
        try {process.kill(-child.pid, 0); groupAlive = true;}
        catch (error) {
          if (error.code === "EPERM") groupAlive = true;
          else if (error.code !== "ESRCH") throw error;
        }
      }
      let monitorAlive = false;
      if (this.ownerMonitorPid) {
        try {process.kill(this.ownerMonitorPid, 0); monitorAlive = true;}
        catch (error) {if (error.code !== "ESRCH") throw error;}
      }
      if (process.platform !== "win32" && backendExited && (groupAlive || monitorAlive)) {
        // Signal-zero sees unreaped zombies on Linux; Darwin may return EPERM.
        // Release ownership only when the table confirms no live owned work.
        const records = await new Promise((resolve, reject) => {
          execFile("ps", ["-axo", "pid=,pgid=,stat="], (failure, stdout) => {
            if (failure) {reject(failure); return;}
            resolve(stdout.split("\n").map((line) => line.trim().split(/\s+/)));
          });
        });
        groupAlive = records.some(([pid, group, state]) =>
          Number(group) === child.pid && state && !state.startsWith("Z"));
        monitorAlive = Boolean(this.ownerMonitorPid && records.some(([pid, group, state]) =>
          Number(pid) === this.ownerMonitorPid && state && !state.startsWith("Z")));
      }
      if (backendExited && !groupAlive && !monitorAlive) return true;
      await delay(25);
    } while (Date.now() < deadline);
    return false;
  }

  async #signalTree(child, signal) {
    if (!Number.isInteger(child.pid)) return;
    if (process.platform === "win32") {
      const arguments_ = ["/PID", String(child.pid), "/T"];
      if (signal === "SIGKILL") arguments_.push("/F");
      await new Promise((resolve, reject) => {
        this.execFileImpl("taskkill.exe", arguments_, {windowsHide: true}, (error) => {
          // A failed graceful request may still need force escalation. A failed
          // forced request must retain ownership and its cause for a retry.
          if (error && signal === "SIGKILL"
            && child.exitCode === null && child.signalCode === null) reject(error);
          else resolve();
        });
      });
      return;
    }
    try {
      process.kill(-child.pid, signal);
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  }
}

module.exports = {
  BackendSupervisor,
  defaultHealthCheck,
  developmentPython,
  resolveBackendLaunch,
  sanitizeDiagnostics,
};
