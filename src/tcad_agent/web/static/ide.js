"use strict";

const workspaceForm = document.querySelector("#workspace-form");
const workspacePath = document.querySelector("#workspace-path");
const browseWorkspace = document.querySelector("#browse-workspace");
const workspaceStatus = document.querySelector("#workspace-status");
const workspaceContextName = document.querySelector("#workspace-context-name");
const workspaceContextState = document.querySelector("#workspace-context-state");
const gitState = document.querySelector("#git-state");
const repositoryTree = document.querySelector("#repository-tree");
const experimentProjects = document.querySelector("#experiment-projects");
const experimentProjectList = document.querySelector("#experiment-project-list");
const experimentProjectCount = document.querySelector("#experiment-project-count");
const ideShell = document.querySelector(".ide-shell");
const agentPanel = document.querySelector("#agent-panel");
const toggleAgentPanel = document.querySelector("#toggle-agent-panel");
const closeAgentPanel = document.querySelector("#close-agent-panel");
const refreshSession = document.querySelector("#refresh-session");
const sessionState = document.querySelector("#session-state");
const sessionMessages = document.querySelector("#session-messages");
const jumpToLatest = document.querySelector("#jump-to-latest");
const clarificationCard = document.querySelector("#clarification-card");
const clarificationProgress = document.querySelector("#clarification-progress");
const clarificationSummary = document.querySelector("#clarification-summary");
const clarificationForm = document.querySelector("#clarification-form");
const clarificationQuestions = document.querySelector("#clarification-questions");
const clarificationSteps = document.querySelector("#clarification-steps");
const clarificationBack = document.querySelector("#clarification-back");
const clarificationNext = document.querySelector("#clarification-next");
const submitClarification = document.querySelector("#submit-clarification");
const planReviewCard = document.querySelector("#plan-review-card");
const planReviewTitle = document.querySelector("#plan-review-title");
const planReviewSummary = document.querySelector("#plan-review-summary");
const planReviewFacts = document.querySelector("#plan-review-facts");
const planReviewPath = document.querySelector("#plan-review-path");
const openPlan = document.querySelector("#open-plan");
const revisePlan = document.querySelector("#revise-plan");
const approvePlan = document.querySelector("#approve-plan");
const approvePlanUnattended = document.querySelector("#approve-plan-unattended");
const planRevisionForm = document.querySelector("#plan-revision-form");
const planRevisionInstruction = document.querySelector("#plan-revision-instruction");
const cancelPlanRevision = document.querySelector("#cancel-plan-revision");
const agentTabs = Array.from(document.querySelectorAll("[data-agent-view]"));
const agentViews = Array.from(document.querySelectorAll("[data-agent-panel]"));
const agentActivity = document.querySelector("#agent-activity");
const agentRunSummary = document.querySelector("#agent-run-summary");
const agentReasoning = document.querySelector("#agent-reasoning");
const agentChanges = document.querySelector("#agent-changes");
const changesState = document.querySelector("#changes-state");
const changesCount = document.querySelector("#changes-count");
const streamState = document.querySelector("#stream-state");
const runState = document.querySelector("#run-state");
const runControls = document.querySelector("#run-controls");
const pauseRun = document.querySelector("#pause-run");
const resumeRun = document.querySelector("#resume-run");
const stopRun = document.querySelector("#stop-run");
const agentChat = document.querySelector("#agent-view-chat");
const approvalLauncher = document.querySelector("#approval-launcher");
const approvalLauncherSummary = document.querySelector("#approval-launcher-summary");
const approvalLauncherCount = document.querySelector("#approval-launcher-count");
const approvalSection = document.querySelector("#approval-section");
const approvalDrawerTitle = document.querySelector("#approval-drawer-title");
const approvalPosition = document.querySelector("#approval-position");
const minimizeApproval = document.querySelector("#minimize-approval");
const pendingApprovals = document.querySelector("#pending-approvals");
const previousApproval = document.querySelector("#previous-approval");
const nextApproval = document.querySelector("#next-approval");
const approvalActions = document.querySelector("#approval-actions");
const messageForm = document.querySelector("#message-form");
const messageInput = document.querySelector("#message-input");
const sendMessage = document.querySelector("#send-message");
const errorNotice = document.querySelector("#ide-error");
const workspaceWelcome = document.querySelector("#workspace-welcome");
const fileViewer = document.querySelector("#file-viewer");
const fileViewerTitle = document.querySelector("#file-viewer-title");
const fileViewerPath = document.querySelector("#file-viewer-path");
const fileViewerType = document.querySelector("#file-viewer-type");
const fileViewerSize = document.querySelector("#file-viewer-size");
const fileViewerState = document.querySelector("#file-viewer-state");
const fileViewerNotice = document.querySelector("#file-viewer-notice");
const fileViewerBody = document.querySelector("#file-viewer-body");
const fileViewerModes = document.querySelector("#file-viewer-modes");
const fileViewerPreview = document.querySelector("#file-viewer-preview");
const fileViewerSource = document.querySelector("#file-viewer-source");
const fileViewerRefresh = document.querySelector("#file-viewer-refresh");
const fileViewerEdit = document.querySelector("#file-viewer-edit");
const fileViewerSave = document.querySelector("#file-viewer-save");
const fileViewerCancel = document.querySelector("#file-viewer-cancel");
const fileViewerDownload = document.querySelector("#file-viewer-download");
const fileViewerClose = document.querySelector("#file-viewer-close");
const fileEditor = document.querySelector("#file-editor");
const desktopSettings = document.querySelector("#desktop-settings");
const desktopSettingsDialog = document.querySelector("#desktop-settings-dialog");
const desktopSettingsForm = document.querySelector("#desktop-settings-form");
const desktopSettingsRegion = document.querySelector("#desktop-settings-region");
const desktopSettingsModel = document.querySelector("#desktop-settings-model");
const desktopSettingsReasoning = document.querySelector("#desktop-settings-reasoning");
const desktopSettingsKey = document.querySelector("#desktop-settings-key");
const desktopSettingsClear = document.querySelector("#desktop-settings-clear");
let researchTrailSignature = "";
const desktopSettingsStorage = document.querySelector("#desktop-settings-storage");
const desktopSettingsError = document.querySelector("#desktop-settings-error");
const desktopSettingsCancel = document.querySelector("#desktop-settings-cancel");
const desktopSettingsSave = document.querySelector("#desktop-settings-save");
const desktopCheckUpdates = document.querySelector("#desktop-check-updates");
const desktopApplyUpdate = document.querySelector("#desktop-apply-update");
const desktopUpdateStatus = document.querySelector("#desktop-update-status");

let activeWorkspace = null;
let activeSession = null;
let activeRun = null;
let eventSource = null;
let sendingPrompt = false;
let activeFile = null;
let activeResult = null;
let resultComparisonHistory = [];
let editingFile = null;
let fileRequestGeneration = 0;
let selectedRunId = null;
let activeChangeSet = null;
let pendingApprovalQueue = [];
let selectedApprovalId = null;
let approvalQueueSignature = "";
let approvalDrawerMinimized = false;
let approvalPreviousFocus = null;
let activePreparation = null;
let activePlan = null;
let clarificationRenderSignature = "";
let activeClarificationIndex = 0;
let lastErrorEnvelope = null;
const navigationGuard = window.AgentKronigIDEState.createNavigationGuard();
const repositoryRequests = window.AgentKronigIDEState.createRepositoryRequestCoordinator();
const submissions = window.AgentKronigIDEState.createSubmissionTracker();
const runPresentation = window.AgentKronigIDEEvents.createRunPresentation();
const runChanges = window.AgentKronigIDEState.createRunResourceCache();

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {"Content-Type": "application/json"},
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail && typeof data.detail === "object"
      ? data.detail.message
      : data.detail;
    const error = new Error(data.message || detail || "Request failed");
    error.code = data.code || null;
    error.payload = data;
    lastErrorEnvelope = data;
    throw error;
  }
  return data;
}

function showError(message = "") {
  const text = typeof message === "string" ? message : message?.message || "";
  errorNotice.replaceChildren();
  errorNotice.classList.toggle("hidden", !text);
  if (!text) {
    lastErrorEnvelope = null;
    return;
  }
  const copy = document.createElement("span");
  copy.textContent = text;
  errorNotice.append(copy);
  const envelope = lastErrorEnvelope;
  if (!envelope?.diagnostic_id || !window.agentKronigDesktop) return;
  const actions = document.createElement("span");
  actions.className = "ide-error-actions";
  const copyDiagnostic = document.createElement("button");
  copyDiagnostic.type = "button";
  copyDiagnostic.textContent = "Copy diagnostic summary";
  copyDiagnostic.addEventListener("click", () => {
    void window.agentKronigDesktop.copyDiagnosticSummary({
      diagnosticId: envelope.diagnostic_id,
      code: envelope.code,
      message: envelope.message,
    });
  });
  const openDiagnostics = document.createElement("button");
  openDiagnostics.type = "button";
  openDiagnostics.textContent = "Open diagnostics";
  openDiagnostics.addEventListener("click", () => {
    void window.agentKronigDesktop.openDiagnostics();
  });
  actions.append(copyDiagnostic, openDiagnostics);
  errorNotice.append(actions);
}

function renderUpdateState(state) {
  const labels = {
    disabled: "Managed updates are not configured.",
    idle: `Update channel: ${state.channel}.`,
    checking: "Checking for updates…",
    available: `Version ${state.version || "new"} is available.`,
    downloading: `Downloading update${state.progressPercent === null ? "" : `: ${Math.round(state.progressPercent)}%`}…`,
    verifying: "Verifying the update publisher…",
    ready: `Version ${state.version || "new"} is ready to install.`,
    blocked: state.message || "Finish or stop active work before updating.",
    installing: "Restarting to install the update…",
    "up-to-date": "Agent Kronig is up to date.",
    error: state.message || "The update could not be verified.",
  };
  desktopUpdateStatus.textContent = labels[state.state] || "Update status is unavailable.";
  desktopCheckUpdates.disabled = !state.enabled || ["checking", "downloading", "verifying", "installing"].includes(state.state);
  desktopApplyUpdate.hidden = !["ready", "blocked"].includes(state.state);
}

async function refreshUpdateState() {
  const state = await window.agentKronigDesktop.getUpdateState();
  renderUpdateState(state);
  if (desktopSettingsDialog.open && ["checking", "downloading", "verifying", "available"].includes(state.state)) {
    setTimeout(() => void refreshUpdateState().catch(() => {}), 1000);
  }
}

async function openDesktopSettings() {
  if (!window.agentKronigDesktop) return;
  desktopSettings.disabled = true;
  desktopSettingsError.textContent = "";
  try {
    const settings = await window.agentKronigDesktop.getSettings();
    desktopSettingsRegion.value = settings.region;
    desktopSettingsModel.value = settings.model;
    desktopSettingsReasoning.value = settings.reasoningEffort;
    desktopSettingsKey.value = "";
    desktopSettingsClear.checked = false;
    let protection = "The API key is protected by this operating system.";
    if (settings.credentialStorage === "session") {
      protection = "This Linux session has no protected secret service. The API key will remain in memory until the application closes.";
    } else if (settings.credentialStorage === "managed") {
      protection = "The API key is supplied by the managed launch environment.";
    }
    const presence = settings.hasBedrockCredential ? "A key is configured." : "No key is configured.";
    desktopSettingsStorage.textContent = `${presence} ${protection}`;
    desktopSettingsDialog.showModal();
    await refreshUpdateState();
  } catch (error) {
    showError(error.message);
  } finally {
    desktopSettings.disabled = false;
  }
}

async function saveDesktopSettings(event) {
  event.preventDefault();
  desktopSettingsError.textContent = "";
  desktopSettingsSave.disabled = true;
  desktopSettingsSave.textContent = "Saving…";
  try {
    await window.agentKronigDesktop.saveSettings({
      region: desktopSettingsRegion.value,
      model: desktopSettingsModel.value,
      reasoningEffort: desktopSettingsReasoning.value,
      bedrockApiKey: desktopSettingsKey.value,
      clearCredential: desktopSettingsClear.checked,
    });
    desktopSettingsStorage.textContent = "Saved. Agent Kronig is restarting its private service.";
  } catch (error) {
    desktopSettingsError.textContent = error.message;
    desktopSettingsSave.disabled = false;
    desktopSettingsSave.textContent = "Save and restart";
  }
}

function parseRoute() {
  const workspace = window.location.pathname.match(/^\/workspaces\/([0-9a-f-]{36})$/i);
  return workspace ? {workspaceId: workspace[1]} : {workspaceId: null};
}

function sessionEndpoint(workspaceId, suffix = "") {
  return `/api/workspaces/${workspaceId}/session${suffix}`;
}

function navigate(path) {
  window.history.pushState({}, "", path);
  void restoreRoute();
}

function clearNode(node) {
  node.replaceChildren();
}

function emptyCopy(text) {
  const paragraph = document.createElement("p");
  paragraph.className = "empty-copy";
  paragraph.textContent = text;
  return paragraph;
}

function renderWorkspace(workspace) {
  const changedWorkspace = activeWorkspace?.id !== workspace.id;
  activeWorkspace = workspace;
  workspacePath.value = workspace.root;
  const context = window.AgentKronigIDEState.workspaceContext(workspace);
  workspaceContextName.textContent = context.name;
  workspaceContextState.textContent = context.state;
  workspaceStatus.title = context.root;
  workspaceStatus.setAttribute("aria-label", `Repository ${context.name}, ${context.state}`);
  workspaceStatus.hidden = false;
  gitState.textContent = workspace.git.available
    ? `${workspace.git.branch || "DETACHED"}${workspace.git.dirty ? " · MODIFIED" : " · CLEAN"}`
    : "NO GIT";
  if (changedWorkspace) closeFileViewer();
}

function closeFileViewer() {
  fileRequestGeneration += 1;
  activeFile = null;
  activeResult = null;
  editingFile = null;
  setFileEditing(false);
  fileViewer.classList.add("hidden");
  workspaceWelcome.classList.remove("hidden");
  document.querySelectorAll(".tree-entry.is-selected").forEach((entry) => entry.classList.remove("is-selected"));
}

function setViewerNotice(message = "") {
  fileViewerNotice.textContent = message;
  fileViewerNotice.classList.toggle("hidden", !message);
}

function fileCanBeEdited(preview) {
  const editableKinds = new Set(["text", "markdown", "json", "csv", "tsv"]);
  const protectedPath = /(^|\/)(\.env(?:\.[^/]+)?|\.git|\.git-credentials|\.ssh|\.aws|\.gnupg|\.netrc|\.npmrc|\.pypirc|\.dockerconfigjson|auth\.json|credentials|id_rsa|id_ed25519|secrets)(\/|$)/i;
  const protectedSuffix = /\.(key|pem)$/i;
  return !activeResult
    && editableKinds.has(preview.kind)
    && !preview.truncated
    && !protectedPath.test(preview.path)
    && !protectedSuffix.test(preview.path);
}

function setFileEditing(isEditing) {
  fileViewerBody.classList.toggle("hidden", isEditing);
  fileEditor.classList.toggle("hidden", !isEditing);
  fileViewerEdit.hidden = isEditing || !activeFile || !fileCanBeEdited(activeFile);
  fileViewerSave.hidden = !isEditing;
  fileViewerCancel.hidden = !isEditing;
  fileViewerRefresh.disabled = isEditing;
  fileViewerModes.hidden = isEditing || !activeFile
    || window.AgentKronigFileViewer.viewModes(activeFile.kind).length < 2;
  if (activeFile) {
    fileViewerState.textContent = isEditing
      ? "Editing"
      : activeResult ? "Verified result" : "Read only";
  }
}

async function beginFileEdit() {
  if (!activeWorkspace || !activeFile || !fileCanBeEdited(activeFile)) return;
  const workspaceId = activeWorkspace.id;
  const path = activeFile.path;
  showError();
  fileViewerEdit.disabled = true;
  try {
    const editable = await api(
      `/api/workspaces/${workspaceId}/files/content?path=${encodeURIComponent(path)}`,
    );
    if (activeWorkspace?.id !== workspaceId || activeFile?.path !== path) return;
    editingFile = editable;
    fileEditor.value = editable.content;
    setFileEditing(true);
    fileEditor.focus();
  } catch (error) {
    showError(error.message);
  } finally {
    fileViewerEdit.disabled = false;
  }
}

function cancelFileEdit() {
  editingFile = null;
  fileEditor.value = "";
  setFileEditing(false);
}

async function saveFileEdit() {
  if (!activeWorkspace || !editingFile) return;
  const workspaceId = activeWorkspace.id;
  const path = editingFile.path;
  showError();
  fileViewerSave.disabled = true;
  try {
    await api(`/api/workspaces/${workspaceId}/files/content`, {
      method: "PUT",
      body: JSON.stringify({
        path,
        content: fileEditor.value,
        expected_sha256: editingFile.sha256,
      }),
    });
    if (activeWorkspace?.id !== workspaceId || activeFile?.path !== path) return;
    cancelFileEdit();
    await openFile({path});
  } catch (error) {
    showError(error.message);
  } finally {
    fileViewerSave.disabled = false;
  }
}

function renderSource(content) {
  const source = document.createElement("ol");
  const lines = window.AgentKronigFileViewer.sourceLines(content || "");
  const displayLines = lines.slice(0, 20000);
  source.className = "file-source";
  displayLines.forEach((line) => {
    const row = document.createElement("li");
    const code = document.createElement("code");
    code.textContent = line || " ";
    row.append(code);
    source.append(row);
  });
  if (lines.length > displayLines.length) {
    setViewerNotice(`Preview limited to ${displayLines.length.toLocaleString()} lines.`);
  }
  fileViewerBody.append(source);
}

function renderMarkdown(content) {
  const article = document.createElement("article");
  article.className = "markdown-preview";
  window.AgentKronigMarkdown.render(article, content || "");
  fileViewerBody.append(article);
}

function renderJsonValue(value, label, depth = 0, budget = {remaining: 2500}) {
  budget.remaining -= 1;
  if (budget.remaining < 0) {
    const limited = document.createElement("span");
    limited.className = "json-value is-muted";
    limited.textContent = "Preview limit reached";
    return limited;
  }
  if (value !== null && typeof value === "object") {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const entries = Object.entries(value);
    details.open = depth < 2;
    summary.textContent = `${label}${Array.isArray(value) ? ` [${entries.length}]` : ` {${entries.length}}`}`;
    details.append(summary);
    const children = document.createElement("div");
    children.className = "json-children";
    entries.forEach(([key, child]) => children.append(renderJsonValue(child, key, depth + 1, budget)));
    details.append(children);
    return details;
  }
  const row = document.createElement("div");
  const key = document.createElement("span");
  const scalar = document.createElement("code");
  row.className = "json-scalar";
  key.textContent = `${label}:`;
  scalar.textContent = typeof value === "string" ? `"${value}"` : String(value);
  row.append(key, scalar);
  return row;
}

function renderJson(content) {
  try {
    const tree = document.createElement("div");
    tree.className = "json-tree";
    tree.append(renderJsonValue(JSON.parse(content), "root"));
    fileViewerBody.append(tree);
  } catch (_error) {
    setViewerNotice("This JSON is not valid, so the source view is shown.");
    renderSource(content);
  }
}

function renderTable(content, delimiter) {
  const parsed = window.AgentKronigFileViewer.parseDelimited(content || "", delimiter);
  const limited = window.AgentKronigFileViewer.limitTable(parsed, 500, 100);
  const wrap = document.createElement("div");
  const table = document.createElement("table");
  const head = table.createTHead();
  const body = table.createTBody();
  wrap.className = "data-table-wrap";
  table.className = "data-table";
  limited.rows.forEach((row, rowIndex) => {
    const tableRow = document.createElement("tr");
    row.forEach((cell) => {
      const element = document.createElement(rowIndex === 0 ? "th" : "td");
      element.textContent = cell;
      tableRow.append(element);
    });
    (rowIndex === 0 ? head : body).append(tableRow);
  });
  if (limited.truncated) setViewerNotice("Table preview limited to 500 rows and 100 columns.");
  wrap.append(table);
  fileViewerBody.append(wrap);
}

function renderImage(preview) {
  const stage = document.createElement("div");
  const controls = document.createElement("div");
  const image = document.createElement("img");
  let zoom = 1;
  stage.className = "image-stage";
  controls.className = "image-controls";
  image.alt = preview.name;
  image.src = window.AgentKronigFileViewer.fileUrl(activeWorkspace.id, preview.path, false);
  const setZoom = (next) => {
    zoom = Math.min(4, Math.max(0.25, next));
    image.style.transform = `scale(${zoom})`;
    controls.querySelector("span").textContent = `${Math.round(zoom * 100)}%`;
  };
  [["−", () => setZoom(zoom - 0.25)], ["Reset", () => setZoom(1)], ["+", () => setZoom(zoom + 0.25)]].forEach(([label, action]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", action);
    controls.append(button);
  });
  const scale = document.createElement("span");
  scale.textContent = "100%";
  controls.append(scale);
  image.addEventListener("load", () => {
    fileViewerState.textContent = `${image.naturalWidth} × ${image.naturalHeight} px · Read only`;
  });
  stage.append(controls, image);
  fileViewerBody.append(stage);
}

function renderPdf(preview) {
  const frame = document.createElement("iframe");
  frame.className = "pdf-viewer";
  frame.title = preview.name;
  frame.src = window.AgentKronigFileViewer.fileUrl(activeWorkspace.id, preview.path, false);
  fileViewerBody.append(frame);
}

function renderBinary(preview) {
  const card = document.createElement("div");
  const title = document.createElement("strong");
  const copy = document.createElement("p");
  card.className = "binary-preview";
  title.textContent = "Preview unavailable";
  copy.textContent = "This binary format is not rendered in the workspace. Download it to open it with a compatible application.";
  card.append(title, copy);
  fileViewerBody.append(card);
}

function renderFileContent(mode = "preview") {
  if (!activeFile) return;
  clearNode(fileViewerBody);
  setViewerNotice(activeFile.truncated ? "This is a truncated preview of a large file." : "");
  fileViewerPreview.classList.toggle("is-active", mode === "preview");
  fileViewerSource.classList.toggle("is-active", mode === "source");
  if (mode === "source") {
    renderSource(activeFile.content);
  } else if (activeResult) {
    window.AgentKronigResults.render(
      fileViewerBody,
      activeResult,
      resultComparisonHistory.filter((item) => item.bundle_path !== activeResult.bundle_path),
    );
  } else if (activeFile.kind === "markdown") {
    renderMarkdown(activeFile.content);
  } else if (activeFile.kind === "json") {
    renderJson(activeFile.content);
  } else if (activeFile.kind === "csv" || activeFile.kind === "tsv") {
    renderTable(activeFile.content, activeFile.kind === "csv" ? "," : "\t");
  } else if (activeFile.kind === "image") {
    renderImage(activeFile);
  } else if (activeFile.kind === "pdf") {
    renderPdf(activeFile);
  } else if (activeFile.kind === "binary") {
    renderBinary(activeFile);
  } else {
    renderSource(activeFile.content);
  }
}

function showFile(preview) {
  activeFile = preview;
  activeResult = null;
  editingFile = null;
  workspaceWelcome.classList.add("hidden");
  fileViewer.classList.remove("hidden");
  fileViewerTitle.textContent = preview.name;
  fileViewerPath.textContent = preview.path;
  fileViewerType.textContent = preview.mime_type;
  fileViewerSize.textContent = window.AgentKronigFileViewer.formatBytes(preview.size);
  fileViewerState.textContent = "Read only";
  fileViewerRefresh.hidden = false;
  fileViewerEdit.hidden = false;
  fileViewerDownload.hidden = false;
  fileViewerDownload.href = window.AgentKronigFileViewer.fileUrl(activeWorkspace.id, preview.path, true);
  fileViewerDownload.download = preview.name;
  fileViewerPreview.textContent = "Preview";
  fileViewerSource.textContent = "Source";
  const modes = window.AgentKronigFileViewer.viewModes(preview.kind);
  fileViewerModes.hidden = modes.length < 2;
  fileViewerPreview.hidden = !modes.includes("preview");
  fileViewerSource.hidden = !modes.includes("source");
  setFileEditing(false);
  renderFileContent(modes[0]);
}

function showCanonicalResult(preview, payload) {
  activeFile = {...preview, content: JSON.stringify(payload, null, 2)};
  activeResult = payload;
  resultComparisonHistory = [
    payload,
    ...resultComparisonHistory.filter((item) => item.bundle_path !== payload.bundle_path),
  ].slice(0, 8);
  editingFile = null;
  workspaceWelcome.classList.add("hidden");
  fileViewer.classList.remove("hidden");
  fileViewerTitle.textContent = `Results · ${payload.manifest.run_id}`;
  fileViewerPath.textContent = payload.bundle_path;
  fileViewerType.textContent = "CanonicalResult";
  fileViewerSize.textContent = window.AgentKronigFileViewer.formatBytes(preview.size);
  fileViewerState.textContent = "Verified result";
  fileViewerRefresh.hidden = false;
  fileViewerEdit.hidden = true;
  fileViewerDownload.hidden = true;
  fileViewerPreview.textContent = "Results";
  fileViewerSource.textContent = "Evidence";
  fileViewerModes.hidden = false;
  fileViewerPreview.hidden = false;
  fileViewerSource.hidden = false;
  setFileEditing(false);
  renderFileContent("preview");
}

function showDiff(change) {
  activeFile = null;
  activeResult = null;
  editingFile = null;
  workspaceWelcome.classList.add("hidden");
  fileViewer.classList.remove("hidden");
  fileViewerTitle.textContent = change.label.split("/").at(-1) || change.label;
  fileViewerPath.textContent = change.detail || change.label;
  fileViewerType.textContent = "Unified diff";
  fileViewerSize.textContent = change.delta;
  fileViewerState.textContent = change.diffTruncated ? "Diff truncated" : "Run change";
  fileViewerModes.hidden = true;
  fileViewerRefresh.hidden = true;
  fileViewerEdit.hidden = true;
  fileViewerDownload.hidden = true;
  fileViewerSave.hidden = true;
  fileViewerCancel.hidden = true;
  fileEditor.classList.add("hidden");
  fileViewerBody.classList.remove("hidden");
  clearNode(fileViewerBody);
  setViewerNotice(change.uncertain
    ? "This binary or large-file change cannot be compared line by line."
    : change.diffTruncated ? "This diff was limited to keep the workspace responsive." : "");
  if (change.diff) renderSource(change.diff);
  else fileViewerBody.append(emptyCopy("A line-by-line diff is not available for this change."));
}

async function openCanonicalResult(preview, workspaceId) {
  return api(
    `/api/workspaces/${workspaceId}/results?path=${encodeURIComponent(preview.path)}`,
  );
}

async function openManagedResult(runId) {
  const payload = await api(`/api/runs/${runId}/result`);
  const projectPath = payload.project_result_path || "results.json";
  showCanonicalResult(
    {
      path: projectPath,
      name: projectPath.split("/").at(-1),
      size: 0,
    },
    payload,
  );
}

async function openSavedResult(bundleRunId) {
  const workspaceId = activeWorkspace?.id;
  if (!workspaceId) return;
  const payload = await api(`/api/workspaces/${workspaceId}/saved-results/${encodeURIComponent(bundleRunId)}`);
  if (activeWorkspace?.id !== workspaceId) return;
  showCanonicalResult({path: payload.canonical_path, name: "canonical.json", size: 0}, payload);
}

async function reviewSavedCalculation(bundleRunId, action = null) {
  const workspaceId = activeWorkspace?.id;
  if (!workspaceId) return;
  const payload = await api(`/api/workspaces/${workspaceId}/saved-results/${encodeURIComponent(bundleRunId)}/${action ? "recovery" : "recalculate"}`, {
    method: "POST", ...(action ? {body: JSON.stringify({action})} : {}),
  });
  if (activeWorkspace?.id !== workspaceId || payload.stopped) return;
  setRun(payload.run || payload);
  activateAgentView("chat");
  await loadPlan(activeRun);
  await refreshMessages(activeSession.id);
}

async function openFile(entry) {
  const requestGeneration = ++fileRequestGeneration;
  const workspaceId = activeWorkspace.id;
  showError();
  fileViewerRefresh.disabled = true;
  try {
    const preview = await api(
      `/api/workspaces/${workspaceId}/files/preview?path=${encodeURIComponent(entry.path)}`,
    );
    if (requestGeneration !== fileRequestGeneration || activeWorkspace?.id !== workspaceId) return;
    if (window.AgentKronigResults.isCanonicalResultPath(preview.path)) {
      const result = await openCanonicalResult(preview, workspaceId);
      if (requestGeneration !== fileRequestGeneration || activeWorkspace?.id !== workspaceId) return;
      showCanonicalResult(preview, result);
    } else {
      showFile(preview);
    }
    document.querySelectorAll(".tree-entry.is-selected").forEach((button) => button.classList.remove("is-selected"));
    document.querySelector(`.tree-entry[data-path="${CSS.escape(entry.path)}"]`)?.classList.add("is-selected");
  } catch (error) {
    if (requestGeneration === fileRequestGeneration) showError(error.message);
  } finally {
    if (requestGeneration === fileRequestGeneration) fileViewerRefresh.disabled = false;
  }
}

async function loadEntries(
  relative = ".",
  routeToken = navigationGuard.currentRoute(),
  {background = false} = {},
) {
  const workspaceId = activeWorkspace.id;
  const request = background
    ? repositoryRequests.beginRefresh()
    : repositoryRequests.beginNavigation(relative);
  if (!request) return;
  try {
    const entries = await api(
      `/api/workspaces/${workspaceId}/entries?path=${encodeURIComponent(request.path)}`,
    );
    if (
      !repositoryRequests.isCurrent(request)
      || !navigationGuard.isCurrent(routeToken)
      || activeWorkspace?.id !== workspaceId
    ) return;
    clearNode(repositoryTree);
    if (request.path !== ".") {
      const rootButton = document.createElement("button");
      rootButton.type = "button";
      rootButton.className = "tree-entry tree-back";
      rootButton.textContent = "← Repository root";
      rootButton.addEventListener("click", () => void loadEntries(".").catch((error) => showError(error.message)));
      repositoryTree.append(rootButton);
    }
    if (!entries.length) repositoryTree.append(emptyCopy("This directory is empty."));
    entries.forEach((entry) => {
      const button = document.createElement("button");
      const marker = document.createElement("span");
      const name = document.createElement("span");
      button.type = "button";
      button.className = "tree-entry";
      button.dataset.path = entry.path;
      button.setAttribute("role", "treeitem");
      marker.className = `entry-marker is-${entry.kind}`;
      marker.textContent = entry.kind === "directory" ? "D" : entry.kind === "file" ? "F" : "L";
      name.textContent = entry.name;
      button.append(marker, name);
      if (entry.kind === "directory") {
        button.addEventListener("click", () => void loadEntries(entry.path).catch((error) => showError(error.message)));
      } else {
        button.addEventListener("click", () => void openFile(entry));
      }
      repositoryTree.append(button);
    });
  } catch (error) {
    const stale = !repositoryRequests.isCurrent(request)
      || !navigationGuard.isCurrent(routeToken)
      || activeWorkspace?.id !== workspaceId;
    if (!stale) throw error;
  } finally {
    const refreshDeferred = repositoryRequests.finish(request);
    if (refreshDeferred) {
      queueMicrotask(() => {
        if (!activeWorkspace) return;
        void refreshCurrentRepository().catch((error) => showError(error.message));
      });
    }
  }
}

async function refreshCurrentRepository() {
  if (!activeWorkspace) return;
  const relative = repositoryRequests.currentPath();
  try {
    await loadEntries(relative, navigationGuard.currentRoute(), {background: true});
  } catch (error) {
    if (
      relative === "."
      || repositoryRequests.currentPath() !== relative
      || repositoryRequests.hasNavigationPending()
    ) throw error;
    await loadEntries(".");
  }
}

function renderExperimentProjects(experiments = [], notice = "") {
  clearNode(experimentProjectList);
  experimentProjectCount.textContent = String(experiments.length);
  experimentProjects.hidden = experiments.length === 0 && !notice;
  document.querySelector("#experiment-projects-title").textContent = "SAVED RESULTS";
  if (notice) experimentProjectList.append(emptyCopy(notice));
  experiments.forEach((experiment) => {
    const name = experiment.name;
    const article = document.createElement("article");
    const summary = document.createElement("div");
    const primary = document.createElement("button");
    const identity = document.createElement("span");
    const title = document.createElement("strong");
    const status = document.createElement("span");
    const disclosure = document.createElement("button");
    const actions = document.createElement("div");
    article.className = `experiment-project is-${experiment.validation_state === "passed" ? "success" : "warning"}`;
    summary.className = "experiment-project-summary";
    primary.type = "button";
    primary.className = "experiment-project-primary";
    primary.title = name;
    primary.setAttribute("aria-label", `Reopen results: ${name}`);
    identity.className = "experiment-project-identity";
    title.textContent = name;
    status.className = "experiment-project-status";
    status.textContent = experiment.reason || (experiment.validation_state === "passed" ? "Checks passed" : "Checks need review");
    identity.append(title, status);
    primary.append(identity);
    primary.addEventListener("click", async () => {
      try { await openSavedResult(experiment.bundle_run_id); }
      catch (error) { showError(error.message); return; }
      if (experiment.validation_state !== "passed") {
        fileViewerBody.querySelector('[data-result-section="validation"]')?.scrollIntoView({block:"start"});
      }
    });
    disclosure.type = "button";
    disclosure.className = "experiment-project-disclosure";
    disclosure.textContent = "›";
    disclosure.title = "Result actions";
    disclosure.setAttribute("aria-label", `Result actions for ${name}`);
    disclosure.setAttribute("aria-expanded", "false");
    actions.className = "experiment-project-actions";
    actions.hidden = true;
    const secondaryActions = experiment.project_path
      ? [{label: "Plan", path: `${experiment.project_path}/PLAN.md`}, {label: "Report", path: `${experiment.project_path}/REPORT.md`}] : [];
    secondaryActions.forEach(({label, path}) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", () => void openFile({path}));
      actions.append(button);
    });
    const recalculate = document.createElement("button");
    recalculate.type = "button";
    recalculate.textContent = "Recalculate";
    recalculate.title = "Prepare a new plan with the same scientific inputs. Does not run until approved.";
    recalculate.addEventListener("click", () => void reviewSavedCalculation(experiment.bundle_run_id).catch(error => showError(error.message)));
    actions.append(recalculate);
    disclosure.addEventListener("click", () => {
      actions.hidden = !actions.hidden;
      disclosure.textContent = actions.hidden ? "›" : "⌄";
      disclosure.setAttribute("aria-expanded", String(!actions.hidden));
    });
    summary.append(primary, disclosure);
    article.append(summary, actions);
    experimentProjectList.append(article);
  });
}

async function loadExperimentProjects(workspaceId = activeWorkspace?.id) {
  if (!workspaceId) {
    renderExperimentProjects([]);
    return;
  }
  const listing = await api(`/api/workspaces/${workspaceId}/saved-results`);
  const notice = [listing.rejected_count ? `${listing.rejected_count} bundles are unavailable, incomplete, or failed integrity checks and were excluded.` : "",
    listing.truncated ? "Showing up to 500 saved bundles." : ""].filter(Boolean).join(" ");
  if (activeWorkspace?.id === workspaceId) renderExperimentProjects(listing.entries, notice);
}

function diagnosticDisclosure(text) {
  const safe = window.AgentKronigAgentView.sanitizeDiagnostic(text);
  if (!safe) return document.createDocumentFragment();
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  const pre = document.createElement("pre");
  const copy = document.createElement("button");
  details.className = "run-diagnostics";
  summary.textContent = "Technical diagnostics";
  pre.textContent = safe;
  copy.type = "button";
  copy.textContent = "Copy diagnostics";
  copy.addEventListener("click", () => void navigator.clipboard.writeText(safe).catch(error => showError(error.message)));
  details.append(summary, pre, copy);
  return details;
}

function appendMessage(message) {
  if (sessionMessages.querySelector(`[data-message-id="${message.id}"]`)) return null;
  const article = document.createElement("article");
  const header = document.createElement("header");
  const role = document.createElement("span");
  const time = document.createElement("time");
  const content = document.createElement("div");
  article.className = `message is-${message.role}`;
  article.dataset.messageId = message.id;
  article.dataset.role = message.role;
  role.textContent = message.role.toUpperCase();
  if (message.created_at) {
    time.dateTime = message.created_at;
    time.textContent = new Date(message.created_at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
  }
  content.className = "message-body";
  window.AgentKronigMarkdown.render(content, message.content);
  header.append(role, time);
  article.append(header, content);
  sessionMessages.append(article);
  return article;
}

function scrollSessionToBottom() {
  requestAnimationFrame(() => {
    sessionMessages.scrollTop = sessionMessages.scrollHeight;
  });
}

function isSessionNearBottom() {
  const remaining = sessionMessages.scrollHeight
    - sessionMessages.clientHeight
    - sessionMessages.scrollTop;
  return remaining <= 48;
}

function renderChatProgress(snapshot, {allowFollow = true, wasNearBottom = null} = {}) {
  const trail = window.AgentKronigAgentView.researchTrail(snapshot);
  const signature = JSON.stringify(trail);
  const changed = signature !== researchTrailSignature;
  const nearBottom = wasNearBottom ?? isSessionNearBottom();
  sessionMessages.querySelector("#agent-research-trail")?.remove();
  researchTrailSignature = signature;
  if (!trail.visible) {
    jumpToLatest.classList.add("hidden");
    return;
  }

  const narrative = document.createElement("section");
  const heading = document.createElement("header");
  const title = document.createElement("strong");
  const meta = document.createElement("span");
  const stages = document.createElement("div");
  narrative.id = "agent-research-trail";
  narrative.className = "research-trail";
  heading.className = "research-trail-header";
  title.textContent = trail.title;
  meta.textContent = trail.meta;
  stages.className = "research-trail-stages";
  if (trail.current) {
    const current = document.createElement("div");
    const activity = document.createElement("span");
    const label = document.createElement("strong");
    const detail = document.createElement("small");
    current.className = `research-trail-current is-${trail.current.status}`;
    activity.className = "research-trail-live-indicator";
    activity.setAttribute("aria-label", "Agent activity in progress");
    activity.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
    label.textContent = trail.current.label;
    detail.textContent = trail.current.detail || "";
    if (trail.current.animated) current.append(activity);
    current.append(label, detail);
    narrative.append(current);
  }
  trail.stages.forEach((stage) => {
    const row = document.createElement("div");
    const phase = document.createElement("span");
    const description = document.createElement("div");
    const label = document.createElement("strong");
    const detail = document.createElement("small");
    row.className = "research-trail-stage";
    phase.textContent = stage.phase;
    label.textContent = stage.label;
    detail.textContent = stage.detail;
    description.append(label, detail);
    row.append(phase, description);
    stages.append(row);
  });
  heading.append(title, meta);
  narrative.prepend(heading);
  narrative.append(stages);
  if (trail.recent?.length) {
    const recent = document.createElement("div");
    recent.className = "research-trail-recent";
    trail.recent.forEach((update) => {
      const row = document.createElement("div");
      const phase = document.createElement("span");
      const label = document.createElement("strong");
      row.className = `is-${update.status}`;
      phase.textContent = update.phase;
      label.textContent = update.label;
      row.append(phase, label);
      if (update.detail) {
        const detail = document.createElement("small");
        detail.textContent = update.detail;
        label.append(detail);
      }
      recent.append(row);
    });
    narrative.append(recent);
  }
  if (trail.recovery) {
    const recovery = document.createElement("p");
    recovery.className = "research-trail-recovery";
    recovery.textContent = trail.recovery;
    narrative.append(recovery);
  }
  if (trail.diagnostics) narrative.append(diagnosticDisclosure(trail.diagnostics));
  const activityLink = document.createElement("button");
  activityLink.type = "button";
  activityLink.className = "research-trail-activity";
  activityLink.textContent = "Open technical activity";
  activityLink.addEventListener("click", () => activateAgentView("activity", {focus: true}));
  narrative.append(activityLink);
  const latestUser = Array.from(sessionMessages.querySelectorAll('.message[data-role="user"]')).at(-1);
  if (latestUser) latestUser.after(narrative);
  else sessionMessages.append(narrative);

  if (!changed || !allowFollow) return;
  if (window.AgentKronigIDEState.shouldAutoFollowProgress(changed, nearBottom)) {
    scrollSessionToBottom();
    jumpToLatest.classList.add("hidden");
  } else {
    jumpToLatest.classList.remove("hidden");
  }
}

function renderMessages(messages, {forceScroll = false} = {}) {
  const previousLastId = sessionMessages.querySelector(".message:last-of-type")?.dataset.messageId;
  const previousScrollTop = sessionMessages.scrollTop;
  const wasNearBottom = isSessionNearBottom();
  const nextLastId = messages.at(-1)?.id;
  const shouldFollow = window.AgentKronigIDEState.shouldAutoFollowChat(
    previousLastId,
    nextLastId,
    wasNearBottom,
    forceScroll,
  );
  clearNode(sessionMessages);
  if (!messages.length) {
    sessionMessages.append(emptyCopy("Describe the task for this repository."));
    return;
  }
  messages.forEach((message) => {
    appendMessage(message);
  });
  renderChatProgress(runPresentation.snapshot(selectedRunId), {
    allowFollow: false,
    wasNearBottom,
  });
  if (shouldFollow) scrollSessionToBottom();
  else requestAnimationFrame(() => { sessionMessages.scrollTop = previousScrollTop; });
}

function renderClarification(preparation) {
  activePreparation = preparation;
  const view = window.AgentKronigClarification.view(preparation);
  const interaction = window.AgentKronigClarification.interaction(preparation);
  const nextSignature = window.AgentKronigClarification.signature(preparation);
  agentChat.classList.toggle("has-clarification", interaction.clarificationActive);
  messageForm.hidden = !interaction.showComposer;
  clarificationCard.classList.toggle("hidden", !view.visible);
  if (!view.visible) {
    clarificationRenderSignature = "";
    activeClarificationIndex = 0;
    clearNode(clarificationQuestions);
    clearNode(clarificationSteps);
    return;
  }
  if (nextSignature === clarificationRenderSignature) return;

  const drafts = {};
  clarificationQuestions.querySelectorAll("textarea[data-question-id]").forEach((input) => {
    drafts[input.dataset.questionId] = input.value;
  });
  const focusedInput = document.activeElement?.closest?.(
    "#clarification-questions textarea[data-question-id]",
  );
  const focusedQuestionId = focusedInput?.dataset.questionId || null;
  const focusedSelection = focusedInput
    ? {end: focusedInput.selectionEnd, start: focusedInput.selectionStart}
    : null;
  const wasVisible = Boolean(clarificationRenderSignature);
  const previousActiveIndex = activeClarificationIndex;

  clearNode(clarificationQuestions);
  clearNode(clarificationSteps);
  activeClarificationIndex = window.AgentKronigClarification.restoredIndex(
    preparation,
    focusedQuestionId,
    wasVisible ? previousActiveIndex : 0,
  );
  clarificationSummary.textContent = view.summary;
  view.questions.forEach((question, index) => {
    const field = document.createElement("div");
    const label = document.createElement("label");
    const rationale = document.createElement("details");
    const rationaleLabel = document.createElement("summary");
    const reason = document.createElement("p");
    const answer = document.createElement("textarea");
    const stepButton = document.createElement("button");
    const inputId = `clarification-${question.id}`;
    field.className = "clarification-question";
    field.dataset.questionIndex = String(index);
    label.htmlFor = inputId;
    label.textContent = question.prompt;
    rationale.className = "clarification-rationale";
    rationaleLabel.textContent = "Why this matters";
    reason.textContent = question.reason;
    answer.id = inputId;
    answer.dataset.questionId = question.id;
    answer.required = question.required;
    answer.rows = 2;
    answer.autocomplete = "off";
    answer.placeholder = question.required ? "Your answer" : "Optional";
    answer.value = drafts[question.id] || "";
    answer.addEventListener("input", () => renderClarificationStep());
    rationale.append(rationaleLabel, reason);
    field.append(label, rationale, answer);
    clarificationQuestions.append(field);

    stepButton.type = "button";
    stepButton.dataset.questionIndex = String(index);
    stepButton.setAttribute("aria-label", `Question ${index + 1} of ${view.questions.length}`);
    stepButton.textContent = String(index + 1);
    stepButton.addEventListener("click", () => {
      activeClarificationIndex = index;
      renderClarificationStep({focus: true});
    });
    clarificationSteps.append(stepButton);
  });
  clarificationRenderSignature = nextSignature;
  renderClarificationStep();
  requestAnimationFrame(() => {
    const focusTarget = focusedQuestionId
      ? Array.from(
        clarificationQuestions.querySelectorAll("textarea[data-question-id]"),
      ).find((input) => input.dataset.questionId === focusedQuestionId)
      : null;
    if (focusTarget) {
      focusTarget.focus({preventScroll: true});
      if (focusedSelection) {
        focusTarget.setSelectionRange(focusedSelection.start, focusedSelection.end);
      }
    } else if (!wasVisible) {
      clarificationQuestions.querySelector("textarea")?.focus({preventScroll: true});
      scrollSessionToBottom();
    }
  });
}

function clarificationValues() {
  const values = {};
  clarificationQuestions.querySelectorAll("textarea[data-question-id]").forEach((input) => {
    values[input.dataset.questionId] = input.value;
  });
  return values;
}

function renderClarificationStep({focus = false} = {}) {
  if (!activePreparation) return;
  const values = clarificationValues();
  const model = window.AgentKronigClarification.view(activePreparation);
  const step = window.AgentKronigClarification.step(
    activePreparation,
    activeClarificationIndex,
    values,
  );
  activeClarificationIndex = step.index;
  clarificationProgress.textContent = `Question ${step.position} of ${step.total}`;
  clarificationQuestions.querySelectorAll(".clarification-question").forEach((field, index) => {
    field.hidden = index !== step.index;
  });
  clarificationSteps.querySelectorAll("button[data-question-index]").forEach((button, index) => {
    const questionId = model.questions[index]?.id;
    button.classList.toggle("is-active", index === step.index);
    button.classList.toggle("is-answered", Boolean(String(values[questionId] || "").trim()));
    if (index === step.index) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
  });
  clarificationBack.disabled = step.isFirst;
  clarificationNext.hidden = step.isLast;
  submitClarification.hidden = !step.isLast;
  if (focus) {
    const input = clarificationQuestions.querySelector(
      `.clarification-question[data-question-index="${step.index}"] textarea`,
    );
    requestAnimationFrame(() => input?.focus({preventScroll: true}));
  }
}

function advanceClarification() {
  const activeField = clarificationQuestions.querySelector(
    `.clarification-question[data-question-index="${activeClarificationIndex}"]`,
  );
  const input = activeField?.querySelector("textarea[data-question-id]");
  if (input?.required && !input.value.trim()) {
    input.reportValidity();
    return;
  }
  activeClarificationIndex += 1;
  renderClarificationStep({focus: true});
}

function renderPlan(plan) {
  activePlan = plan;
  const view = window.AgentKronigAgentView.planReview(plan);
  const oldLedger = planReviewCard.querySelector("[data-plan-input-ledger]");
  const ledgerOpen = Boolean(oldLedger?.open);
  oldLedger?.remove();
  planReviewCard.classList.toggle("hidden", !view.visible);
  agentChat.classList.toggle("has-plan-review", view.visible);
  if (!view.visible) {
    clearNode(planReviewFacts);
    planRevisionForm.classList.add("hidden");
    planRevisionInstruction.value = "";
    return;
  }
  planReviewTitle.textContent = view.title;
  planReviewSummary.textContent = (
    `${view.backend.toUpperCase()} · ${view.study} · `
    + `${view.regionCount} region${view.regionCount === 1 ? "" : "s"} · `
    + `${view.observableCount} requested output${view.observableCount === 1 ? "" : "s"}`
  );
  clearNode(planReviewFacts);
  [
    ["Scientific inputs", view.unresolvedCount ? `${view.unresolvedCount} unresolved` : "Complete"],
    ["Contacts", String(view.contactCount)],
    ["Warnings", String(view.warningCount)],
  ].forEach(([label, value]) => {
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value;
    planReviewFacts.append(term, description);
  });
  planReviewPath.textContent = view.planPath;
  planReviewPath.title = view.planPath;
  const ledger = document.createElement("details");
  ledger.dataset.planInputLedger = "true";
  ledger.open = ledgerOpen;
  const heading = document.createElement("summary");
  heading.textContent = "Scientific inputs and authority";
  ledger.append(heading);
  const ledgerNote = document.createElement("p");
  ledgerNote.textContent = "Authority describes who reviews the contract, not who supplied each value. Original input attribution is unavailable unless explicitly recorded.";
  ledger.append(ledgerNote);
  (view.inputLedger || []).forEach(group => {
    const section = document.createElement("section");
    const title = document.createElement("strong");
    const list = document.createElement("dl");
    title.textContent = group.label;
    group.records.forEach(record => {
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = record.quantity || record.path;
      dd.textContent = [typeof record.value === "object" ? JSON.stringify(record.value) : record.value,
        record.source, record.derivation, record.rationale].filter(value => value != null && value !== "").join(" · ");
      list.append(dt, dd);
    });
    section.append(title, list);
    ledger.append(section);
  });
  planReviewFacts.after(ledger);
}

async function approvePreparedPlan(mode) {
  if (!activeRun?.id || !activePlan) return;
  const view = window.AgentKronigAgentView.planReview(activePlan);
  [approvePlan, approvePlanUnattended, revisePlan].forEach((button) => {
    button.disabled = true;
  });
  showError();
  try {
    const run = await api(`/api/runs/${activeRun.id}/plan/approve`, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: view.revision,
        plan_digest: view.planDigest,
        mode,
      }),
    });
    renderPlan(null);
    setRun(run);
  } catch (error) {
    showError(error.message);
    await loadPlan(activeRun);
  } finally {
    [approvePlan, approvePlanUnattended, revisePlan].forEach((button) => {
      button.disabled = false;
    });
  }
}

async function loadPlan(run = activeRun) {
  if (!run?.id || run.state !== "waiting_for_plan_approval") {
    renderPlan(null);
    return;
  }
  try {
    const plan = await api(`/api/runs/${run.id}/plan`);
    if (activeRun?.id === run.id) renderPlan(plan);
  } catch (error) {
    renderPlan(null);
    showError(error.message);
  }
}

async function loadPreparation(run = activeRun) {
  if (!run?.id) {
    renderClarification(null);
    return;
  }
  try {
    const preparation = await api(`/api/runs/${run.id}/preparation`);
    if (activeRun?.id === run.id) renderClarification(preparation);
  } catch (_error) {
    renderClarification(null);
  }
}

async function refreshMessages(sessionKey = activeSession?.id, options = {}) {
  const workspaceId = activeWorkspace?.id;
  if (!sessionKey || !workspaceId) return;
  const pending = navigationGuard.captureSession(
    navigationGuard.currentRoute(), sessionKey,
  );
  const messages = await api(sessionEndpoint(workspaceId, "/messages"));
  if (
    activeWorkspace?.id !== workspaceId
    || !navigationGuard.canApplySession(pending, activeSession?.id)
  ) return;
  renderMessages(messages, options);
}

async function synchronizeSession(sessionKey) {
  const workspaceId = activeWorkspace?.id;
  if (!sessionKey || !workspaceId || activeSession?.id !== sessionKey) return;
  const pending = navigationGuard.captureSession(
    navigationGuard.currentRoute(), sessionKey,
  );
  const [messages, run, approvals] = await Promise.all([
    api(sessionEndpoint(workspaceId, "/messages")),
    api(sessionEndpoint(workspaceId, "/runs/active")),
    api(sessionEndpoint(workspaceId, "/approvals")),
  ]);
  if (
    activeWorkspace?.id !== workspaceId
    || !navigationGuard.canApplySession(pending, activeSession?.id)
  ) return;
  renderMessages(messages);
  setRun(run);
  await loadPreparation(run);
  await loadPlan(run);
  renderApprovals(approvals);
}

const refreshCoordinator = window.AgentKronigIDEState.createRefreshCoordinator(
  synchronizeSession,
);

async function requestSessionRefresh(sessionKey = activeSession?.id) {
  if (!sessionKey) return;
  refreshSession.disabled = true;
  refreshSession.textContent = "Refreshing…";
  try {
    await refreshCoordinator.request(sessionKey);
  } catch (error) {
    if (activeSession?.id === sessionKey) showError(error.message);
  } finally {
    if (activeSession?.id === sessionKey) {
      refreshSession.disabled = false;
      refreshSession.textContent = "Refresh";
    }
  }
}

function setRun(run) {
  activeRun = run;
  if (run?.id) selectRun(run.id, {refresh: true});
  const state = run?.state || "idle";
  const controls = window.AgentKronigIDEState.controlsForState(state);
  runState.textContent = state.replaceAll("_", " ").toUpperCase();
  pauseRun.hidden = !controls.pause;
  resumeRun.hidden = !controls.resume;
  stopRun.hidden = !controls.stop;
  runControls.hidden = !controls.pause && !controls.resume && !controls.stop;
  messageInput.disabled = !activeSession || !controls.send || sendingPrompt;
  sendMessage.disabled = messageInput.disabled;
  sendMessage.textContent = sendingPrompt ? "Starting…" : "Send";
  refreshSession.disabled = !activeSession;
  if (state !== "waiting_for_user" && activePreparation?.run_id !== run?.id) {
    renderClarification(null);
  }
  if (state !== "waiting_for_plan_approval") renderPlan(null);
}

function activateAgentView(name, {focus = false} = {}) {
  agentTabs.forEach((button) => {
    const active = button.dataset.agentView === name;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    if (active && focus) button.focus();
  });
  agentViews.forEach((view) => {
    const active = view.dataset.agentPanel === name;
    view.hidden = !active;
    view.classList.toggle("is-active", active);
  });
}

function renderRunSummary(snapshot) {
  const summary = window.AgentKronigAgentView.outcomeSummary(snapshot, activeChangeSet);
  clearNode(agentRunSummary);
  agentRunSummary.hidden = !summary.visible;
  if (!summary.visible) return;
  const title = document.createElement("strong");
  const detail = document.createElement("span");
  agentRunSummary.className = `agent-run-summary is-${summary.tone}`;
  title.textContent = summary.title;
  detail.textContent = summary.executionState
    ? `${summary.failedCheckCount} failed checks · ${summary.unmetDeliverables.length} unmet outputs`
    : summary.failedStep
    ? summary.failureSummary
    : `${summary.completedSteps} actions completed · ${summary.changedFiles} files changed`;
  agentRunSummary.append(title, detail);
  if (summary.diagnostics) agentRunSummary.append(diagnosticDisclosure(summary.diagnostics));
  const evidence = [
    ["Phases", summary.phases?.join(" → ")],
    ["Changed files", summary.changedPaths?.join("\n")],
    ["Commands", summary.commands?.join("\n")],
    ["Validation", summary.validationEvidence?.map((item) => `${item.label}${item.output ? `: ${item.output}` : ""}`).join("\n")],
    ["Executed checks, not final evidence", summary.unlinkedValidationChecks?.map((item) => `${item.label}${item.output ? `: ${item.output}` : ""}`).join("\n")],
    ["Artifacts", summary.artifacts?.join("\n")],
    ["Provenance", summary.provenance?.join("\n")],
    ["Warnings", summary.warnings?.join("\n")],
    ["Next", summary.nextActions?.join("\n")],
    ["Execution", summary.executionState],
    ["Validation", summary.validationState],
    ["Deliverables", summary.deliverableState],
    ["Report", summary.reportState],
    ["Unmet requested outputs", summary.unmetDeliverables?.join("\n")],
  ].filter(([, value]) => value);
  if (evidence.length) {
    const details = document.createElement("details");
    const label = document.createElement("summary");
    const list = document.createElement("dl");
    label.textContent = "Run evidence";
    evidence.forEach(([term, value]) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = term;
      dd.textContent = value;
      row.append(dt, dd);
      list.append(row);
    });
    details.append(label, list);
    agentRunSummary.append(details);
  }
}

function renderReasoning(snapshot) {
  clearNode(agentReasoning);
  const updates = window.AgentKronigAgentView.operationalUpdates(snapshot);
  agentReasoning.hidden = !updates.length;
  if (!updates.length) return;
  const heading = document.createElement("div");
  const title = document.createElement("strong");
  const note = document.createElement("span");
  const list = document.createElement("ol");
  heading.className = "progress-log-heading";
  title.textContent = "Agent progress";
  note.textContent = "Operational summary";
  list.className = "progress-log";
  updates.forEach((update) => {
    const item = document.createElement("li");
    const phase = document.createElement("span");
    const label = document.createElement("strong");
    item.className = `progress-log-entry is-${update.status}`;
    phase.textContent = update.phase;
    label.textContent = update.label;
    item.append(phase, label);
    if (update.detail) {
      const detail = document.createElement("small");
      detail.textContent = update.detail;
      item.append(detail);
    }
    list.append(item);
  });
  heading.append(title, note);
  agentReasoning.append(heading, list);
}

function renderActivity(snapshot) {
  clearNode(agentActivity);
  const rows = window.AgentKronigAgentView.activityRows(snapshot);
  if (!rows.length && !snapshot.approvalHistory?.length && !snapshot.technicalEvents?.length) {
    agentActivity.append(emptyCopy("Tool activity will appear here when a run starts."));
  }
  rows.forEach((row) => {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const status = document.createElement("span");
    const label = document.createElement("strong");
    const metadata = document.createElement("span");
    const technical = document.createElement("div");
    details.className = `execution-step is-${row.status}`;
    details.setAttribute("data-action-id", row.id);
    status.className = "execution-status";
    status.textContent = row.status === "running" ? "●" : row.status === "failed" ? "×" : "✓";
    label.textContent = row.label;
    metadata.textContent = [row.phase, row.owner, row.duration].filter(Boolean).join(" · ");
    summary.append(status, label, metadata);
    technical.className = "execution-technical";
    if (row.command) {
      const command = document.createElement("code");
      command.textContent = row.command;
      technical.append(command);
    }
    if (row.output) {
      const output = document.createElement("pre");
      output.textContent = String(row.output);
      technical.append(output);
    }
    const affectedPaths = window.AgentKronigAgentView.affectedFilePaths(row, activeWorkspace?.root);
    affectedPaths.forEach((affectedPath) => {
      const open = document.createElement("button");
      open.type = "button";
      open.textContent = `Affected file: ${affectedPath}`;
      open.addEventListener("click", () => {
        const changed = window.AgentKronigChanges.toRows(activeChangeSet)
          .find((candidate) => candidate.label === affectedPath);
        if (changed?.diff || (changed && !changed.canOpenFile)) showDiff(changed);
        else void openFile({path: affectedPath});
      });
      technical.append(open);
    });
    if (!technical.childNodes.length) technical.append(emptyCopy("No additional technical output."));
    details.append(summary, technical);
    agentActivity.append(details);
  });
  (snapshot.approvalHistory || []).forEach((approval) => {
    const row = document.createElement("div");
    const label = document.createElement("strong");
    const state = document.createElement("span");
    row.className = "approval-marker";
    label.textContent = approval.summary;
    state.textContent = approval.decision ? `Decision: ${approval.decision}` : "Waiting for approval";
    row.append(label, state);
    agentActivity.append(row);
  });
  if (snapshot.technicalEvents?.length) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const events = document.createElement("pre");
    details.className = "technical-events";
    summary.textContent = `Technical events (${snapshot.technicalEvents.length})`;
    events.textContent = snapshot.technicalEvents
      .map((event) => `${event.kind}: ${JSON.stringify(event.payload || {})}`)
      .join("\n");
    details.append(summary, events);
    agentActivity.append(details);
  }
}

function renderAgentPresentation() {
  const snapshot = runPresentation.snapshot(selectedRunId);
  renderChatProgress(snapshot);
  renderRunSummary(snapshot);
  renderReasoning(snapshot);
  renderActivity(snapshot);
}

function renderChanges(changeSet) {
  const runId = changeSet?.run_id || selectedRunId;
  runChanges.put(runId, changeSet);
  activeChangeSet = runChanges.current();
  const rows = window.AgentKronigChanges.toRows(changeSet);
  const incomplete = window.AgentKronigChanges.isIncomplete(changeSet);
  clearNode(agentChanges);
  changesCount.textContent = String(rows.length);
  changesState.textContent = incomplete ? "PARTIAL SCAN" : rows.length ? `${rows.length} CHANGED` : "NO CHANGES";
  if (incomplete) {
    const warning = document.createElement("p");
    warning.className = "change-scan-warning";
    warning.textContent = changeSet.manifest_warning || "The workspace scan reached its safety limit. Modified files shown here are exact, but create, delete, and rename attribution may be incomplete.";
    agentChanges.append(warning);
  }
  if (!rows.length) {
    agentChanges.append(emptyCopy("No workspace changes are attributed to this run."));
    renderRunSummary(runPresentation.snapshot(selectedRunId));
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("article");
    const button = document.createElement("button");
    const top = document.createElement("span");
    const operation = document.createElement("b");
    const path = document.createElement("strong");
    const delta = document.createElement("code");
    const detail = document.createElement("small");
    button.type = "button";
    item.className = "change-item";
    button.className = `change-row is-${row.operation}`;
    operation.textContent = row.operationLabel;
    path.textContent = row.label;
    delta.textContent = row.delta;
    top.append(operation, path, delta);
    const attribution = row.attributedActionIds.length
      ? `Action ${row.attributedActionIds.join(", ")}${row.attributedSubagents.length ? ` · ${row.attributedSubagents.join(", ")}` : ""}`
      : null;
    detail.textContent = row.detail || attribution || (row.uncertain ? "Exact line changes are unavailable" : "Attribution unavailable · Open run diff");
    button.append(top, detail);
    button.addEventListener("click", () => {
      if (row.diff || !row.canOpenFile) showDiff(row);
      else void openFile({path: row.label});
    });
    item.append(button);
    if (row.validationActionIds.length) {
      const validations = document.createElement("div");
      validations.className = "change-validation-links";
      row.validationActionIds.forEach((actionId, index) => {
        const validation = document.createElement("button");
        validation.type = "button";
        validation.className = "change-validation-link";
        validation.textContent = row.validationActionIds.length === 1
          ? "View validation evidence"
          : `Validation check ${index + 1}`;
        validation.addEventListener("click", () => {
          activateAgentView("activity");
          const target = Array.from(agentActivity.querySelectorAll("[data-action-id]"))
            .find((candidate) => candidate.dataset.actionId === actionId);
          if (!target) return;
          target.open = true;
          target.scrollIntoView({block: "center"});
          target.querySelector("summary")?.focus();
        });
        validations.append(validation);
      });
      item.append(validations);
    }
    agentChanges.append(item);
  });
  renderRunSummary(runPresentation.snapshot(selectedRunId));
}

async function refreshChanges(runId = selectedRunId) {
  if (!runId) {
    activeChangeSet = null;
    runChanges.select(null);
    changesCount.textContent = "0";
    changesState.textContent = "NO RUN";
    clearNode(agentChanges);
    agentChanges.append(emptyCopy("Run changes will appear after the agent starts working."));
    return null;
  }
  changesState.textContent = "CHECKING";
  try {
    const changeSet = await api(`/api/runs/${runId}/changes`);
    if (selectedRunId !== runId) return;
    renderChanges(changeSet);
    return changeSet;
  } catch (_error) {
    if (selectedRunId !== runId) return;
    activeChangeSet = null;
    changesCount.textContent = "0";
    changesState.textContent = "UNAVAILABLE";
    clearNode(agentChanges);
    agentChanges.append(emptyCopy("Changes are unavailable for this historical run."));
    return null;
  }
}

function selectRun(runId, {refresh = false} = {}) {
  const normalized = runId ? String(runId) : null;
  if (selectedRunId === normalized) return false;
  selectedRunId = normalized;
  activeChangeSet = runChanges.select(normalized);
  if (activeChangeSet) {
    renderChanges(activeChangeSet);
  } else {
    changesCount.textContent = "0";
    changesState.textContent = normalized ? "CHECKING" : "NO RUN";
    clearNode(agentChanges);
    agentChanges.append(emptyCopy(
      normalized
        ? "Changes for this run are being checked."
        : "Run changes will appear after the agent starts working.",
    ));
    renderRunSummary(runPresentation.snapshot(normalized));
  }
  if (refresh && normalized) void refreshChanges(normalized);
  return true;
}

async function decideApproval(approval, decision) {
  showError();
  Array.from(approvalActions.querySelectorAll("button")).forEach((button) => {
    button.disabled = true;
  });
  try {
    let endpoint = `/api/approvals/${approval.id}/deny`;
    if (decision === "approve") endpoint = `/api/approvals/${approval.id}/approve`;
    if (decision === "approve-category") endpoint = `/api/approvals/${approval.id}/approve-category`;
    const body = {expected_revision: approval.revision};
    if (decision === "deny") body.reason = "Denied by the user";
    const run = await api(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setRun(run);
    await loadApprovals();
  } catch (error) {
    showError(error.message);
    await loadApprovals();
  } finally {
    Array.from(approvalActions.querySelectorAll("button")).forEach((button) => {
      button.disabled = false;
    });
  }
}

function permissionCategoryLabel(value) {
  return String(value || "unrecognized action").replaceAll("_", " ");
}

function approvalSignature(approvals) {
  return JSON.stringify(approvals.map((approval) => ({
    id: approval.id,
    revision: approval.revision,
    summary: approval.summary,
    permission_category: approval.permission_category,
    payload: approval.payload,
  })));
}

function restoreApprovalFocus() {
  const target = approvalPreviousFocus;
  approvalPreviousFocus = null;
  requestAnimationFrame(() => {
    if (target?.isConnected && !target.disabled && !target.inert) {
      target.focus();
    } else if (!messageInput.disabled) {
      messageInput.focus();
    }
  });
}

function setApprovalDrawerOpen(open, {focus = true, restoreFocus = false} = {}) {
  const hasApprovals = pendingApprovalQueue.length > 0;
  const shouldOpen = Boolean(open && hasApprovals);
  if (shouldOpen && !approvalSection.contains(document.activeElement)) {
    approvalPreviousFocus = document.activeElement;
  }
  approvalDrawerMinimized = hasApprovals && !shouldOpen;
  approvalSection.classList.toggle("hidden", !shouldOpen);
  approvalLauncher.classList.toggle("hidden", !hasApprovals || shouldOpen);
  approvalLauncher.setAttribute("aria-expanded", String(shouldOpen));
  agentChat.classList.toggle("has-approval-open", shouldOpen);
  sessionMessages.inert = shouldOpen;
  messageForm.inert = shouldOpen;
  if (shouldOpen && focus) requestAnimationFrame(() => approvalSection.focus());
  if (!shouldOpen && restoreFocus) restoreApprovalFocus();
}

function renderActiveApproval({focus = false, technicalOpen = false} = {}) {
  const deck = window.AgentKronigAgentView.approvalDeck(
    pendingApprovalQueue,
    selectedApprovalId,
  );
  clearNode(pendingApprovals);
  clearNode(approvalActions);
  if (!deck.active) return;

  const approval = deck.active;
  const view = window.AgentKronigAgentView.permissionView(approval);
  selectedApprovalId = approval.id;
  approvalDrawerTitle.textContent = view.explanation;
  approvalPosition.textContent = `${deck.position} of ${deck.total}`;
  approvalLauncherSummary.textContent = view.explanation;
  approvalLauncherCount.textContent = String(deck.total);
  previousApproval.disabled = !deck.canPrevious;
  nextApproval.disabled = !deck.canNext;

  const card = document.createElement("article");
  const plainHeading = document.createElement("h3");
  const plainExplanation = document.createElement("p");
  const targetHeading = document.createElement("span");
  const target = document.createElement("code");
  const reversibility = document.createElement("p");
  const technical = document.createElement("details");
  const technicalLabel = document.createElement("summary");
  const technicalBody = document.createElement("div");
  const toolDetail = document.createElement("span");
  const categoryDetail = document.createElement("span");
  const riskDetail = document.createElement("span");
  const argumentsDetail = document.createElement("code");
  const deny = document.createElement("button");
  const approve = document.createElement("button");
  const approveCategory = document.createElement("button");

  card.className = "approval-card";
  plainHeading.textContent = "What Agent Kronig is asking to do";
  plainExplanation.className = "approval-explanation";
  plainExplanation.textContent = view.explanation;
  targetHeading.className = "approval-target-label";
  targetHeading.textContent = "Target";
  target.className = "approval-target";
  target.textContent = view.target;
  reversibility.className = "approval-reversibility";
  reversibility.textContent = `Reversibility: ${view.reversibility}`;
  technical.className = "approval-technical";
  technical.open = technicalOpen;
  technicalLabel.textContent = "Technical details";
  toolDetail.textContent = `Tool: ${view.toolName}`;
  categoryDetail.textContent = `Permission type: ${permissionCategoryLabel(view.permissionCategory)}`;
  riskDetail.textContent = `Risk level: ${view.risk}`;
  argumentsDetail.textContent = view.technicalArguments;
  technicalBody.append(toolDetail, categoryDetail, riskDetail, argumentsDetail);
  technical.append(technicalLabel, technicalBody);
  card.append(plainHeading, plainExplanation, targetHeading, target, reversibility, technical);
  pendingApprovals.append(card);

  deny.type = "button";
  deny.className = "is-deny";
  deny.textContent = "Deny";
  approve.type = "button";
  approve.className = "is-approve";
  approve.textContent = "Approve once";
  approveCategory.type = "button";
  approveCategory.className = "is-approve-category";
  approveCategory.textContent = "Approve all like this";
  approveCategory.title = "Allow this permission type for the rest of this run only";
  deny.addEventListener("click", () => void decideApproval(approval, "deny"));
  approve.addEventListener("click", () => void decideApproval(approval, "approve"));
  approvalActions.append(deny, approve);
  if (view.canApproveCategory) {
    approveCategory.addEventListener("click", () => void decideApproval(approval, "approve-category"));
    approvalActions.append(approveCategory);
  }
  if (focus) requestAnimationFrame(() => approvalSection.focus());
}

function renderApprovals(approvals) {
  const nextQueue = Array.isArray(approvals) ? approvals : [];
  const previousIds = new Set(pendingApprovalQueue.map((approval) => String(approval.id)));
  const hadApprovals = pendingApprovalQueue.length > 0;
  const nextSignature = approvalSignature(nextQueue);
  const signatureChanged = approvalQueueSignature !== nextSignature;
  const technicalOpen = !signatureChanged && Boolean(
    pendingApprovals.querySelector(".approval-technical")?.open,
  );
  pendingApprovalQueue = nextQueue;
  approvalQueueSignature = nextSignature;

  if (!pendingApprovalQueue.length) {
    selectedApprovalId = null;
    clearNode(pendingApprovals);
    clearNode(approvalActions);
    setApprovalDrawerOpen(false, {restoreFocus: hadApprovals});
    approvalLauncher.classList.add("hidden");
    return;
  }

  const containsNewApproval = pendingApprovalQueue.some(
    (approval) => !previousIds.has(String(approval.id)),
  );
  const deck = window.AgentKronigAgentView.approvalDeck(
    pendingApprovalQueue,
    selectedApprovalId,
  );
  selectedApprovalId = deck.active.id;
  if (signatureChanged) renderActiveApproval({technicalOpen});
  if (!hadApprovals || containsNewApproval || !approvalDrawerMinimized) {
    setApprovalDrawerOpen(true, {focus: !hadApprovals || containsNewApproval});
  } else {
    setApprovalDrawerOpen(false);
  }
}

async function loadApprovals(sessionKey = activeSession?.id) {
  const workspaceId = activeWorkspace?.id;
  if (!sessionKey || !workspaceId) return;
  const pending = navigationGuard.captureSession(
    navigationGuard.currentRoute(), sessionKey,
  );
  const approvals = await api(sessionEndpoint(workspaceId, "/approvals"));
  if (
    activeWorkspace?.id === workspaceId
    && navigationGuard.canApplySession(pending, activeSession?.id)
  ) renderApprovals(approvals);
}

function updateRunFromEvent(event) {
  const terminalStates = {
    run_completed: "completed",
    run_failed: "failed",
    run_blocked: "blocked",
    run_cancelled: "cancelled",
    run_paused: "paused",
    run_recovered_paused: "paused",
  };
  if (event.kind === "run_state_changed" && event.payload?.state) {
    setRun({...activeRun, id: event.payload.run_id, state: event.payload.state});
  } else if (event.kind === "approval_requested") {
    setRun({...activeRun, id: event.payload?.run_id, state: "waiting_for_approval"});
  } else if (event.kind === "plan_ready") {
    setRun({...activeRun, id: event.payload?.run_id, state: "waiting_for_plan_approval"});
  } else if (event.kind === "plan_approved" || event.kind === "plan_revision_requested") {
    setRun({...activeRun, id: event.payload?.run_id, state: "running"});
  } else if (terminalStates[event.kind]) {
    setRun({...activeRun, id: event.payload?.run_id, state: terminalStates[event.kind]});
  }
}

function connectEvents(sessionKey) {
  if (eventSource) eventSource.close();
  runPresentation.reset();
  runChanges.clear();
  selectedRunId = null;
  activeChangeSet = null;
  selectRun(activeRun?.id || null);
  renderAgentPresentation();
  void refreshChanges(selectedRunId);
  streamState.textContent = "CONNECTING";
  const workspaceId = activeWorkspace.id;
  const pending = navigationGuard.captureSession(
    navigationGuard.currentRoute(), sessionKey,
  );
  eventSource = new EventSource(sessionEndpoint(workspaceId, "/events"));
  const receive = (rawEvent) => {
    if (
      activeWorkspace?.id !== workspaceId
      || !navigationGuard.canApplySession(pending, activeSession?.id)
    ) return;
    streamState.textContent = "LIVE";
    const event = JSON.parse(rawEvent.data);
    if (!runPresentation.accept(event)) return;
    const eventRunId = event.payload?.run_id ? String(event.payload.run_id) : null;
    if (eventRunId && ["run_created", "run_started"].includes(event.kind)) {
      selectRun(eventRunId, {refresh: true});
    }
    renderAgentPresentation();
    updateRunFromEvent(event);
    if (event.kind === "message_created") void refreshMessages(sessionKey);
    if (event.kind === "clarification_required") void loadPreparation(activeRun);
    if (event.kind === "plan_ready") void loadPlan(activeRun);
    if (["plan_approved", "plan_revision_requested"].includes(event.kind)) renderPlan(null);
    if (event.kind === "result_ready") {
      void openManagedResult(eventRunId).catch((error) => showError(error.message));
      void loadExperimentProjects(workspaceId).catch((error) => showError(error.message));
    }
    if (event.kind === "saved_result_ready") {
      void openSavedResult(event.payload.bundle_run_id).catch(error => showError(error.message));
      void loadExperimentProjects(workspaceId).catch(error => showError(error.message));
    }
    if (["clarification_answered", "prompt_compiled"].includes(event.kind)) {
      renderClarification(null);
    }
    if (event.kind === "approval_requested" || event.kind === "approval_resolved") {
      void loadApprovals(sessionKey);
    }
    if (event.kind === "tool_call_completed") void refreshChanges(selectedRunId);
    if (window.AgentKronigIDEState.shouldRefreshRepository(event.kind)) {
      void refreshCurrentRepository().catch((error) => showError(error.message));
    }
    if (event.kind === "run_completed") {
      const completedRunId = eventRunId || selectedRunId;
      void refreshChanges(completedRunId).then((changeSet) => {
        if (selectedRunId !== completedRunId || editingFile) return;
        const resultPath = window.AgentKronigResults.findCanonicalResultPath(changeSet);
        if (resultPath) void openFile({path: resultPath});
      });
      void refreshCoordinator.request(sessionKey).catch((error) => showError(error.message));
    } else if (["run_failed", "run_blocked", "run_cancelled"].includes(event.kind)) {
      void refreshChanges(selectedRunId);
      void refreshCoordinator.request(sessionKey).catch((error) => showError(error.message));
    }
  };
  [
    "conversation_created", "message_created", "run_created", "run_state_changed",
    "run_started", "tool_call_started", "tool_call_completed", "approval_requested",
    "approval_resolved", "permission_grant_created", "permission_grant_used",
    "run_completed", "run_failed", "run_blocked", "run_paused",
    "run_cancelled", "run_recovered_paused", "agent_error", "runtime_state_changed",
    "thinking_started", "thinking_delta", "thinking_aborted", "change_baseline_warning",
    "agent_progress_started", "agent_progress_interrupted",
    "prompt_preparation_started", "prompt_preparation_progress",
    "clarification_required", "clarification_answered", "prompt_compiled",
    "plan_ready", "plan_approved", "plan_revision_requested", "result_ready", "saved_result_ready",
  ].forEach((kind) => eventSource.addEventListener(kind, receive));
  eventSource.onopen = () => {
    streamState.textContent = "LIVE";
    void refreshCoordinator.request(sessionKey).catch((error) => showError(error.message));
  };
  eventSource.onerror = () => { streamState.textContent = "RECONNECTING"; };
}

async function bindSession(session, workspaceId, routeToken) {
  activeSession = session;
  sessionState.textContent = "Current repository";
  await refreshMessages(session.id, {forceScroll: true});
  if (!navigationGuard.isCurrent(routeToken) || activeSession?.id !== session.id) return;
  const run = await api(sessionEndpoint(workspaceId, "/runs/active"));
  if (!navigationGuard.isCurrent(routeToken) || activeSession?.id !== session.id) return;
  setRun(run);
  await loadPreparation(run);
  await loadPlan(run);
  await loadApprovals(session.id);
  if (!navigationGuard.isCurrent(routeToken) || activeSession?.id !== session.id) return;
  connectEvents(session.id);
}

function clearSession() {
  activeSession = null;
  activeRun = null;
  selectedRunId = null;
  activeChangeSet = null;
  activePreparation = null;
  activePlan = null;
  renderClarification(null);
  renderPlan(null);
  renderExperimentProjects([]);
  submissions.reset();
  runPresentation.reset();
  setRun(null);
  clearNode(sessionMessages);
  sessionMessages.append(emptyCopy("Describe the task for this repository."));
  clearNode(agentActivity);
  clearNode(agentReasoning);
  clearNode(agentRunSummary);
  void refreshChanges(null);
  renderApprovals([]);
  streamState.textContent = "OFFLINE";
  sessionState.textContent = "Open a repository";
  refreshSession.disabled = true;
  if (eventSource) eventSource.close();
  eventSource = null;
}

function applyAgentPanelAction(action) {
  const next = AgentKronigLayout.resolvePanelAction({
    mode: ideShell.dataset.layoutMode || "desktop",
    collapsed: ideShell.classList.contains("is-agent-collapsed"),
    open: agentPanel.classList.contains("is-open"),
  }, action);
  ideShell.classList.toggle("is-agent-collapsed", next.collapsed);
  ideShell.classList.toggle("is-agent-open", next.open);
  agentPanel.classList.toggle("is-open", next.open);
  toggleAgentPanel.setAttribute(
    "aria-expanded",
    String(next.open || !next.collapsed),
  );
}

function setAgentPanelOpen(open) {
  applyAgentPanelAction(open ? "open" : "close");
}

async function restoreRoute() {
  const routeToken = navigationGuard.beginRoute();
  const previousWorkspaceId = activeWorkspace?.id || null;
  showError();
  const route = parseRoute();
  if (!route.workspaceId) {
    clearSession();
    return;
  }
  try {
    const workspace = await api(`/api/workspaces/${route.workspaceId}`);
    if (!navigationGuard.isCurrent(routeToken)) return;
    const session = await api(sessionEndpoint(route.workspaceId), {method: "POST"});
    if (!navigationGuard.isCurrent(routeToken)) return;
    clearSession();
    renderWorkspace(workspace);
    await loadEntries(".", routeToken);
    await loadExperimentProjects(workspace.id);
    if (!navigationGuard.isCurrent(routeToken)) return;
    await bindSession(session, route.workspaceId, routeToken);
    const requestedBundle = new URLSearchParams(window.location.search).get("saved_bundle_id");
    if (/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(requestedBundle || "")) await openSavedResult(requestedBundle);
    const requestedResult = new URLSearchParams(window.location.search).get("result_run_id");
    if (/^[0-9a-f-]{36}$/i.test(requestedResult || "")) {
      await openManagedResult(requestedResult);
    }
  } catch (error) {
    if (!navigationGuard.isCurrent(routeToken)) return;
    if (error.code === "workspace_session_busy" && previousWorkspaceId && activeSession) {
      window.history.replaceState({}, "", `/workspaces/${previousWorkspaceId}`);
      navigationGuard.beginRoute();
      connectEvents(activeSession.id);
      void requestSessionRefresh(activeSession.id);
    }
    showError(error.message);
  }
}

async function openWorkspace(path) {
  const workspace = await api("/api/workspaces", {
    method: "POST",
    body: JSON.stringify({path}),
  });
  navigate(`/workspaces/${workspace.id}`);
}

workspaceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError();
  try {
    await openWorkspace(workspacePath.value);
  } catch (error) {
    showError(error.message);
  }
});

browseWorkspace.addEventListener("click", async () => {
  showError();
  browseWorkspace.disabled = true;
  browseWorkspace.textContent = "Choosing folder…";
  try {
    const selectedPath = await window.AgentKronigDesktopBridge.selectDirectory(
      window.fetch.bind(window),
      window.agentKronigDesktop,
    );
    if (!selectedPath) return;
    workspacePath.value = selectedPath;
    await openWorkspace(selectedPath);
  } catch (error) {
    showError(error.message);
  } finally {
    browseWorkspace.disabled = false;
    browseWorkspace.textContent = "Open folder";
  }
});

clarificationBack.addEventListener("click", () => {
  activeClarificationIndex -= 1;
  renderClarificationStep({focus: true});
});
clarificationNext.addEventListener("click", advanceClarification);

clarificationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeRun?.id || !activePreparation) return;
  showError();
  const values = clarificationValues();
  const incompleteIndex = window.AgentKronigClarification.firstIncomplete(
    activePreparation,
    values,
  );
  if (incompleteIndex >= 0) {
    activeClarificationIndex = incompleteIndex;
    renderClarificationStep({focus: true});
    requestAnimationFrame(() => {
      clarificationQuestions.querySelector(
        `.clarification-question[data-question-index="${incompleteIndex}"] textarea`,
      )?.reportValidity();
    });
    return;
  }
  submitClarification.disabled = true;
  submitClarification.textContent = "Preparing…";
  try {
    const payload = window.AgentKronigClarification.submission(activePreparation, values);
    const run = await api(`/api/runs/${activeRun.id}/clarifications`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderClarification(null);
    setRun(run);
    await refreshMessages(activeSession?.id, {forceScroll: true});
  } catch (error) {
    showError(error.message);
    if (error.code === "stale_revision") await loadPreparation(activeRun);
  } finally {
    submitClarification.disabled = false;
    submitClarification.textContent = "Continue";
  }
});

openPlan.addEventListener("click", () => {
  if (!activePlan) return;
  const view = window.AgentKronigAgentView.planReview(activePlan);
  void openFile({path: view.planPath});
});
approvePlan.addEventListener("click", () => {
  void approvePreparedPlan("review_each_risk");
});
approvePlanUnattended.addEventListener("click", () => {
  void approvePreparedPlan("unattended_local");
});
revisePlan.addEventListener("click", () => {
  planRevisionForm.classList.remove("hidden");
  planRevisionInstruction.focus();
});
cancelPlanRevision.addEventListener("click", () => {
  planRevisionForm.classList.add("hidden");
  planRevisionInstruction.value = "";
});
planRevisionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const instruction = planRevisionInstruction.value.trim();
  if (!instruction || !activeRun?.id || !activePlan) return;
  const view = window.AgentKronigAgentView.planReview(activePlan);
  const submit = planRevisionForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  showError();
  try {
    const run = await api(`/api/runs/${activeRun.id}/plan/revise`, {
      method: "POST",
      body: JSON.stringify({expected_revision: view.revision, instruction}),
    });
    renderPlan(null);
    setRun(run);
  } catch (error) {
    showError(error.message);
    await loadPlan(activeRun);
  } finally {
    submit.disabled = false;
  }
});

messageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const draft = messageInput.value.trim();
  if (!draft || !activeSession || sendingPrompt) return;
  if (!window.AgentKronigIDEState.controlsForState(activeRun?.state).send) return;
  const sessionKey = activeSession.id;
  const workspaceId = activeWorkspace.id;
  const pendingResponse = navigationGuard.captureMessage(
    navigationGuard.currentRoute(), sessionKey, draft,
  );
  sendingPrompt = true;
  setRun(activeRun);
  showError();
  try {
    const submission = submissions.begin(sessionKey, draft);
    let messageId = submission.messageId;
    if (!messageId) {
      const message = await api(sessionEndpoint(workspaceId, "/messages"), {
        method: "POST",
        body: JSON.stringify({content: draft}),
      });
      if (
        activeWorkspace?.id !== workspaceId
        || !navigationGuard.canApplyMessage(pendingResponse, activeSession?.id)
      ) return;
      submissions.recordMessage(submission, message.id);
      messageId = message.id;
      if (sessionMessages.querySelector(".empty-copy")) clearNode(sessionMessages);
      appendMessage(message);
      scrollSessionToBottom();
    }
    const run = await api(sessionEndpoint(workspaceId, "/runs"), {
      method: "POST",
      body: JSON.stringify({message_id: messageId}),
    });
    submissions.recordRun(submission, run.id);
    if (
      activeWorkspace?.id !== workspaceId
      || !navigationGuard.canApplyMessage(pendingResponse, activeSession?.id)
    ) return;
    messageInput.value = "";
    setRun(run);
  } catch (error) {
    if (error.code === "agent_run_conflict") {
      await requestSessionRefresh(sessionKey).catch(() => {});
    }
    if (
      activeWorkspace?.id === workspaceId
      && navigationGuard.canApplyMessage(pendingResponse, activeSession?.id)
    ) showError(error.message);
  } finally {
    sendingPrompt = false;
    if (activeWorkspace?.id === workspaceId && activeSession?.id === sessionKey) {
      setRun(activeRun);
    }
  }
});

messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    messageForm.requestSubmit();
  }
});

async function controlRun(action) {
  if (!activeRun) return;
  showError();
  try {
    const run = await api(`/api/runs/${activeRun.id}/${action}`, {method: "POST"});
    setRun(run);
  } catch (error) {
    showError(error.message);
  }
}

pauseRun.addEventListener("click", () => void controlRun("pause"));
resumeRun.addEventListener("click", () => void controlRun("resume"));
stopRun.addEventListener("click", () => void controlRun("stop"));
jumpToLatest.addEventListener("click", () => {
  scrollSessionToBottom();
  jumpToLatest.classList.add("hidden");
});
sessionMessages.addEventListener("scroll", () => {
  if (isSessionNearBottom()) jumpToLatest.classList.add("hidden");
}, {passive: true});
approvalLauncher.addEventListener("click", () => setApprovalDrawerOpen(true));
minimizeApproval.addEventListener("click", () => setApprovalDrawerOpen(false, {restoreFocus: true}));
previousApproval.addEventListener("click", () => {
  const deck = window.AgentKronigAgentView.approvalDeck(
    pendingApprovalQueue,
    selectedApprovalId,
  );
  const index = window.AgentKronigAgentView.moveApproval(deck.index, deck.total, -1);
  selectedApprovalId = pendingApprovalQueue[index]?.id || selectedApprovalId;
  renderActiveApproval({focus: true});
});
nextApproval.addEventListener("click", () => {
  const deck = window.AgentKronigAgentView.approvalDeck(
    pendingApprovalQueue,
    selectedApprovalId,
  );
  const index = window.AgentKronigAgentView.moveApproval(deck.index, deck.total, 1);
  selectedApprovalId = pendingApprovalQueue[index]?.id || selectedApprovalId;
  renderActiveApproval({focus: true});
});
approvalSection.addEventListener("keydown", (event) => {
  const focusable = Array.from(approvalSection.querySelectorAll(
    "button:not([disabled]), summary, [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
  )).filter((element) => !element.hidden && element.offsetParent !== null);
  const action = window.AgentKronigAgentView.approvalKeyAction({
    key: event.key,
    shiftKey: event.shiftKey,
    atContainer: approvalSection === document.activeElement,
    atFirst: focusable[0] === document.activeElement,
    atLast: focusable.at(-1) === document.activeElement,
  });
  if (action === "minimize") {
    event.preventDefault();
    setApprovalDrawerOpen(false, {restoreFocus: true});
  } else if (action === "focus-first" && focusable.length) {
    event.preventDefault();
    focusable[0].focus();
  } else if (action === "focus-last" && focusable.length) {
    event.preventDefault();
    focusable.at(-1).focus();
  }
});
refreshSession.addEventListener("click", () => void requestSessionRefresh());
agentTabs.forEach((button) => {
  button.addEventListener("click", () => activateAgentView(button.dataset.agentView));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const index = agentTabs.indexOf(button);
    let next = index;
    if (event.key === "ArrowLeft") next = (index - 1 + agentTabs.length) % agentTabs.length;
    if (event.key === "ArrowRight") next = (index + 1) % agentTabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = agentTabs.length - 1;
    activateAgentView(agentTabs[next].dataset.agentView, {focus: true});
    event.preventDefault();
  });
});
toggleAgentPanel.addEventListener("click", () => {
  applyAgentPanelAction("toggle");
});
closeAgentPanel.addEventListener("click", () => applyAgentPanelAction("close"));
fileViewerPreview.addEventListener("click", () => renderFileContent("preview"));
fileViewerSource.addEventListener("click", () => renderFileContent("source"));
fileViewerEdit.addEventListener("click", () => void beginFileEdit());
fileViewerSave.addEventListener("click", () => void saveFileEdit());
fileViewerCancel.addEventListener("click", cancelFileEdit);
fileViewerRefresh.addEventListener("click", () => {
  if (activeResult?.saved_bundle_id) void openSavedResult(activeResult.saved_bundle_id).catch(error => showError(error.message));
  else if (activeFile) void openFile({path: activeFile.path});
});
window.addEventListener("kronig:review-recovery", event => {
  const detail = event.detail;
  if (!detail || detail.workspaceId !== activeWorkspace?.id) return;
  void reviewSavedCalculation(detail.bundleRunId, detail.action).catch(error => showError(error.message));
});
fileViewerClose.addEventListener("click", closeFileViewer);
if (window.agentKronigDesktop) desktopSettings.hidden = false;
desktopSettings.addEventListener("click", () => void openDesktopSettings());
desktopSettingsCancel.addEventListener("click", () => desktopSettingsDialog.close());
desktopSettingsForm.addEventListener("submit", (event) => void saveDesktopSettings(event));
desktopCheckUpdates.addEventListener("click", async () => {
  desktopSettingsError.textContent = "";
  try {
    renderUpdateState(await window.agentKronigDesktop.checkForUpdates());
    void refreshUpdateState();
  } catch (error) {
    desktopSettingsError.textContent = error.message;
  }
});
desktopApplyUpdate.addEventListener("click", async () => {
  desktopSettingsError.textContent = "";
  try {
    renderUpdateState(await window.agentKronigDesktop.applyUpdateWhenSafe());
  } catch (error) {
    desktopSettingsError.textContent = error.message;
    await refreshUpdateState();
  }
});
window.addEventListener("popstate", () => void restoreRoute());
window.addEventListener("beforeunload", () => eventSource?.close());
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void requestSessionRefresh();
});
setInterval(() => {
  if (!activeSession) return;
  const shouldRefresh = window.AgentKronigIDEState.isActiveState(activeRun?.state)
    || streamState.textContent === "RECONNECTING";
  if (shouldRefresh) void refreshCoordinator.request(activeSession.id).catch((error) => showError(error.message));
}, 5000);
void restoreRoute();
