"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const {BackendSupervisor} = require("./backend-supervisor");
const {DesktopSettingsStore} = require("./settings-store");
const {createLinuxUpdateVerifier} = require("./linux-update-verifier");
const {UpdateController} = require("./update-controller");

function createLaunchToken() {
  return crypto.randomBytes(32).toString("base64url");
}

function shouldAutoStart(processLike) {
  return processLike.type === "browser";
}

function developmentIconPath(isPackaged, applicationRoot = path.resolve(__dirname, "..")) {
  if (isPackaged) return undefined;
  return path.join(applicationRoot, "assets", "icon.png");
}

function configureApplicationIdentity(app) {
  app.setName("Agent Kronig");
}

function attachNavigationPolicy(webContents, allowedOrigin) {
  webContents.setWindowOpenHandler(() => ({action: "deny"}));
  webContents.on("will-navigate", (event, destination) => {
    try {
      if (new URL(destination).origin !== allowedOrigin) event.preventDefault();
    } catch {
      event.preventDefault();
    }
  });
}

function installPermissionPolicy(electronSession) {
  electronSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });
  electronSession.setPermissionCheckHandler(() => false);
}

function resultWindowUrl(origin, payload = {}) {
  const base = new URL(origin);
  const identifier = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  if (
    base.protocol !== "http:"
    || !["127.0.0.1", "localhost", "::1"].includes(base.hostname)
    || !identifier.test(String(payload.workspaceId || ""))
    || !identifier.test(String(payload.runId || ""))
  ) throw new Error("Result window identifier is invalid");
  const destination = new URL(`/workspaces/${payload.workspaceId}`, base.origin);
  destination.searchParams.set("result_run_id", payload.runId);
  return destination.toString();
}

function sanitizeDiagnosticSummary(payload = {}) {
  const redacted = [
    `Diagnostic: ${String(payload.diagnosticId || "unavailable")}`,
    `Code: ${String(payload.code || "unclassified")}`,
    `Message: ${String(payload.message || "No message was provided.")}`,
  ].join("\n").replace(
    /\b(token|password|secret|api[-_]?key|authorization)\s*[:=]\s*[^\s,;]+/gi,
    "$1=[REDACTED]",
  );
  return redacted.slice(0, 4096);
}

function installGracefulQuit(
  app,
  stopBackend,
  onBlocked = async () => "keep-working",
  forceStopBackend = async () => {},
) {
  let shutdownComplete = false;
  let shutdownStarted = false;
  app.on("before-quit", (event) => {
    if (shutdownComplete) return;
    event.preventDefault();
    if (shutdownStarted) return;
    shutdownStarted = true;
    void Promise.resolve()
      .then(stopBackend)
      .then(() => {
        shutdownComplete = true;
        app.quit();
      })
      .catch(async (error) => {
        shutdownStarted = false;
        const decision = await onBlocked(error);
        if (decision === "retry") {
          app.quit();
          return;
        }
        if (decision === "quit-anyway") {
          try {
            await forceStopBackend();
          } finally {
            shutdownComplete = true;
            app.quit();
          }
        }
      });
  });
  return () => shutdownComplete;
}

function installWindowCloseGuard(window, app, isShutdownComplete) {
  window.on("close", (event) => {
    if (isShutdownComplete()) return;
    event.preventDefault();
    app.quit();
  });
}

function createApplication(
  electron = require("electron"),
  updater = require("electron-updater").autoUpdater,
) {
  const {app, BrowserWindow, clipboard, dialog, ipcMain, safeStorage, session, shell} = electron;
  configureApplicationIdentity(app);
  let mainWindow = null;
  let supervisor = null;
  let settingsStore = null;
  let isShutdownComplete = () => false;
  const windowIcon = developmentIconPath(app.isPackaged);
  const updateFeedUrl = process.env.AGENT_KRONIG_UPDATE_URL || "";
  let verifyDownload = async () => {};
  if (process.platform === "linux" && updateFeedUrl) {
    const publicKeyPath = path.join(__dirname, "linux-update-public-key.pem");
    verifyDownload = createLinuxUpdateVerifier({
      feedUrl: updateFeedUrl,
      publicKey: fs.readFileSync(publicKeyPath, "utf8"),
    });
  }
  const updateController = new UpdateController({
    updater,
    feedUrl: updateFeedUrl,
    channel: process.env.AGENT_KRONIG_UPDATE_CHANNEL || "stable",
    statusClient: backendActivity,
    verifyDownload,
  });

  const desktopInfo = () => Object.freeze({
    application: "Agent Kronig",
    version: app.getVersion(),
    platform: process.platform,
    architecture: process.arch,
    packaged: app.isPackaged,
  });

  function sidecarRoot() {
    return path.join(process.resourcesPath, "sidecars");
  }

  function backendOptions() {
    const projectRoot = path.resolve(__dirname, "../..");
    const resourceRoot = app.isPackaged ? process.resourcesPath : projectRoot;
    const options = {
      dataDir: app.getPath("userData"),
      tokenFactory: createLaunchToken,
      startupTimeoutMs: app.isPackaged ? 120000 : 15000,
      isPackaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      projectRoot,
      environment: {
        ...process.env,
        ...settingsStore.environment(),
        TCAD_KNOWLEDGE_INDEX: path.join(
          resourceRoot,
          "knowledge-sources",
          "index",
          "knowledge.sqlite3",
        ),
        TCAD_SKILLS_ROOT: path.join(resourceRoot, "skills"),
        OPENHANDS_SUPPRESS_BANNER: "1",
      },
    };
    if (app.isPackaged) {
      const suffix = process.platform === "win32" ? ".exe" : "";
      options.devsimRunner = path.join(
        sidecarRoot(),
        "devsim",
        `agent-kronig-devsim${suffix}`,
      );
    }
    return options;
  }

  function createWindow() {
    const window = new BrowserWindow({
      width: 1500,
      height: 940,
      minWidth: 1080,
      minHeight: 680,
      backgroundColor: "#0b0f14",
      show: false,
      title: "Agent Kronig",
      icon: windowIcon,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
        webSecurity: true,
        devTools: !app.isPackaged,
      },
    });
    installWindowCloseGuard(window, app, isShutdownComplete);
    window.once("ready-to-show", () => window.show());
    window.on("closed", () => {
      if (mainWindow === window) mainWindow = null;
    });
    return window;
  }

  async function backendActivity() {
    if (!supervisor?.readiness) return {active: true};
    const response = await fetch(`${supervisor.readiness.url}/api/desktop/status`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Desktop activity status is unavailable");
    return response.json();
  }

  async function assertBackendIdle() {
    const status = await backendActivity();
    if (!status || status.active !== false) {
      throw new Error("Finish or stop active work before closing or restarting Agent Kronig.");
    }
  }

  async function prepareBackendShutdown() {
    if (!supervisor?.readiness) return;
    const response = await fetch(
      `${supervisor.readiness.url}/api/desktop/prepare-shutdown`,
      {
        method: "POST",
        cache: "no-store",
        headers: {Authorization: `Bearer ${supervisor.readiness.launchToken}`},
      },
    );
    if (response.ok) return;
    let message = "Agent Kronig could not prepare the local service for shutdown.";
    try {
      const payload = await response.json();
      if (payload?.message) message = payload.message;
    } catch {
      // Keep the sanitized fallback message.
    }
    throw new Error(message);
  }

  async function launchWorkspace(previousWindow = null) {
    const candidate = new BackendSupervisor(backendOptions());
    supervisor = candidate;
    candidate.once("unexpected-exit", (event) => {
      if (supervisor !== candidate) return;
      const suffix = event.code === null ? `signal ${event.signal}` : `code ${event.code}`;
      void showStartupError(new Error(`Backend exited unexpectedly with ${suffix}`), mainWindow);
    });
    try {
      const ready = await candidate.start();
      const window = createWindow();
      attachNavigationPolicy(window.webContents, ready.url);
      await window.loadURL(
        `${ready.url}/desktop/bootstrap?token=${encodeURIComponent(ready.launchToken)}`,
      );
      mainWindow = window;
      if (previousWindow && previousWindow !== window) previousWindow.close();
    } catch (error) {
      await showStartupError(error, previousWindow);
    }
  }

  async function showStartupError(error, previousWindow = null) {
    const logDirectory = app.getPath("logs");
    fs.mkdirSync(logDirectory, {recursive: true});
    const logPath = path.join(logDirectory, "desktop-startup.log");
    const category = error && /lock/i.test(error.message)
      ? "Workspace already open"
      : "Local service could not start";
    fs.writeFileSync(
      logPath,
      `${new Date().toISOString()} ${category}\n${supervisor?.diagnostics || "No backend diagnostics were emitted."}\n`,
      {encoding: "utf8", mode: 0o600},
    );
    const window = createWindow();
    window.webContents.on("will-navigate", (event, destination) => {
      if (!destination.startsWith("agent-kronig-error://")) return;
      event.preventDefault();
      if (destination === "agent-kronig-error://retry") {
        void launchWorkspace(window);
      } else if (destination === "agent-kronig-error://quit") {
        app.quit();
      }
    });
    await window.loadFile(path.join(__dirname, "error.html"), {
      query: {category, logPath},
    });
    mainWindow = window;
    if (previousWindow && previousWindow !== window) previousWindow.close();
  }

  function registerIpc() {
    ipcMain.handle("desktop:select-directory", async () => {
      const result = await dialog.showOpenDialog(mainWindow, {
        title: "Open repository folder",
        properties: ["openDirectory"],
      });
      return Object.freeze({
        cancelled: result.canceled || result.filePaths.length === 0,
        path: result.canceled ? null : result.filePaths[0] || null,
      });
    });
    ipcMain.handle("desktop:get-info", () => desktopInfo());
    ipcMain.handle("desktop:choose-bundle-export-destination", async (_event, payload = {}) => {
      const baseName = String(payload.suggestedName || "agent-kronig-results")
        .replace(/[^a-z0-9._-]+/gi, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 96) || "agent-kronig-results";
      const result = await dialog.showSaveDialog(mainWindow, {
        title: "Export reproducibility bundle",
        defaultPath: `${baseName.replace(/\.akbundle$/i, "")}.akbundle`,
        filters: [{name: "Agent Kronig reproducibility bundle", extensions: ["akbundle"]}],
      });
      return Object.freeze({
        cancelled: result.canceled || !result.filePath,
        path: result.canceled ? null : result.filePath || null,
      });
    });
    ipcMain.handle("desktop:copy-diagnostic-summary", (_event, payload = {}) => {
      const summary = sanitizeDiagnosticSummary(payload);
      clipboard.writeText(summary);
      return Object.freeze({copied: true});
    });
    ipcMain.handle("desktop:open-diagnostics", async () => {
      const directory = path.join(app.getPath("userData"), "diagnostics");
      fs.mkdirSync(directory, {recursive: true});
      const error = await shell.openPath(directory);
      if (error) throw new Error("The diagnostics folder could not be opened.");
      return Object.freeze({opened: true});
    });
    ipcMain.handle("desktop:open-results-window", async (_event, payload = {}) => {
      if (!supervisor?.readiness) throw new Error("The local result service is unavailable.");
      const destination = resultWindowUrl(supervisor.readiness.url, payload);
      const resultWindow = new BrowserWindow({
        width: 1280,
        height: 860,
        minWidth: 900,
        minHeight: 600,
        backgroundColor: "#0b0f14",
        title: "Agent Kronig Results",
        icon: windowIcon,
        parent: mainWindow,
        webPreferences: {
          preload: path.join(__dirname, "preload.js"),
          contextIsolation: true,
          sandbox: true,
          nodeIntegration: false,
          webSecurity: true,
          devTools: !app.isPackaged,
        },
      });
      attachNavigationPolicy(resultWindow.webContents, supervisor.readiness.url);
      await resultWindow.loadURL(destination);
      return Object.freeze({opened: true});
    });
    ipcMain.handle("desktop:export-results-pdf", async (event, payload = {}) => {
      const baseName = String(payload.suggestedName || "agent-kronig-results")
        .replace(/[^a-z0-9._-]+/gi, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 96) || "agent-kronig-results";
      const result = await dialog.showSaveDialog(mainWindow, {
        title: "Export scientific results PDF",
        defaultPath: `${baseName.replace(/\.pdf$/i, "")}.pdf`,
        filters: [{name: "PDF document", extensions: ["pdf"]}],
      });
      if (result.canceled || !result.filePath) {
        return Object.freeze({cancelled: true, path: null});
      }
      const pdf = await event.sender.printToPDF({
        printBackground: true,
        preferCSSPageSize: true,
        pageSize: "A4",
      });
      fs.writeFileSync(result.filePath, pdf, {mode: 0o600});
      return Object.freeze({cancelled: false, path: result.filePath});
    });
    ipcMain.handle("desktop:get-settings", () => settingsStore.getPublicSettings());
    ipcMain.handle("desktop:save-settings", async (_event, payload) => {
      await assertBackendIdle();
      const state = settingsStore.save(payload);
      setTimeout(async () => {
        const previousWindow = mainWindow;
        try {
          await stopBackendWhenIdle();
          await launchWorkspace(previousWindow);
        } catch (error) {
          await dialog.showMessageBox(previousWindow, {
            type: "warning",
            message: error.message,
          });
        }
      }, 50);
      return Object.freeze({...state, restarting: true});
    });
    ipcMain.handle("desktop:get-update-state", () => updateController.getState());
    ipcMain.handle("desktop:check-for-updates", () => updateController.checkForUpdates());
    ipcMain.handle(
      "desktop:apply-update-when-safe",
      () => updateController.applyUpdateWhenSafe(),
    );
  }

  async function stopBackend() {
    await supervisor?.stop();
  }

  async function stopBackendWhenIdle() {
    await prepareBackendShutdown();
    await stopBackend();
  }

  async function run() {
    if (!app.requestSingleInstanceLock()) {
      app.quit();
      return;
    }
    app.on("second-instance", () => {
      if (mainWindow) {
        if (mainWindow.isMinimized()) mainWindow.restore();
        mainWindow.focus();
      }
    });
    isShutdownComplete = installGracefulQuit(app, stopBackendWhenIdle, async (error) => {
      const result = await dialog.showMessageBox(mainWindow, {
        type: "warning",
        title: "Agent Kronig could not finish closing",
        message: error.message,
        detail: "Project files remain in place. You can retry cleanup, keep working, or quit the application anyway.",
        buttons: ["Retry", "Quit anyway", "Keep working"],
        defaultId: 0,
        cancelId: 2,
      });
      return ["retry", "quit-anyway", "keep-working"][result.response] || "keep-working";
    }, stopBackend);
    app.on("window-all-closed", () => app.quit());
    await app.whenReady();
    if (windowIcon && app.dock?.setIcon) app.dock.setIcon(windowIcon);
    installPermissionPolicy(session.defaultSession);
    settingsStore = new DesktopSettingsStore({
      dataDir: app.getPath("userData"),
      safeStorage,
      baseEnvironment: process.env,
    });
    registerIpc();
    await launchWorkspace();
  }

  return {run, stopBackend};
}

if (shouldAutoStart(process)) {
  void createApplication().run();
}

module.exports = {
  attachNavigationPolicy,
  configureApplicationIdentity,
  createApplication,
  createLaunchToken,
  developmentIconPath,
  installGracefulQuit,
  installWindowCloseGuard,
  installPermissionPolicy,
  resultWindowUrl,
  sanitizeDiagnosticSummary,
  shouldAutoStart,
};
