"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(message);
}

const cleanContext = globalThis.AgentKronigIDEState.workspaceContext({
  root: "/home/research/pn-junction",
  git: {available: true, branch: "main", dirty: false},
});
assertEqual(cleanContext.name, "pn-junction", "the title bar should show the repository folder name");
assertEqual(cleanContext.state, "main · clean", "the title bar should show clean branch state");
assertEqual(cleanContext.root, "/home/research/pn-junction", "the complete path remains available");

const modifiedWindowsContext = globalThis.AgentKronigIDEState.workspaceContext({
  root: "C:\\Users\\research\\device-study\\",
  git: {available: true, branch: null, dirty: true},
});
assertEqual(
  modifiedWindowsContext.name,
  "device-study",
  "the repository label should support Windows paths",
);
assertEqual(
  modifiedWindowsContext.state,
  "detached · modified",
  "detached modified repositories should remain explicit",
);

const guard = globalThis.AgentKronigIDEState.createNavigationGuard();
const firstRoute = guard.beginRoute();
const pendingMessage = guard.captureMessage(firstRoute, "session-a", "inspect the deck");
const firstSession = guard.captureSession(firstRoute, "session-a");

assertEqual(
  guard.canApplyMessage(pendingMessage, "session-a"),
  true,
  "the current session response should be accepted",
);

guard.beginRoute();
assertEqual(
  guard.canApplyMessage(pendingMessage, "session-a"),
  false,
  "a response from the previous route must be ignored",
);
assertEqual(
  guard.canApplySession(firstSession, "session-a"),
  false,
  "approval and event responses from a released session must be ignored",
);

const currentRoute = guard.currentRoute();
const currentMessage = guard.captureMessage(currentRoute, "session-b", "run validation");
assertEqual(
  guard.canApplyMessage(currentMessage, "session-c"),
  false,
  "a response must not render in another workspace session",
);
assertEqual(
  guard.canClearDraft(currentMessage, "session-b", "new draft"),
  false,
  "a response must not clear a draft typed while it was pending",
);

const submissions = globalThis.AgentKronigIDEState.createSubmissionTracker();
const firstAttempt = submissions.begin("session-b", "edit and test");
assertEqual(firstAttempt.messageId, null, "a new prompt should create a message");
submissions.recordMessage(firstAttempt, "message-1");
const retry = submissions.begin("session-b", "edit and test");
assertEqual(retry.messageId, "message-1", "a retry must reuse the persisted message");
submissions.recordRun(retry, "run-1");
assertEqual(submissions.current(), null, "a successful run should clear submission state");

const eventLedger = globalThis.AgentKronigIDEState.createEventLedger();
assertEqual(eventLedger.accept(17), true, "a new SSE event should render");
assertEqual(eventLedger.accept(17), false, "a replayed SSE event must not render twice");
assertEqual(eventLedger.accept(18), true, "the next SSE event should render");

const runningControls = globalThis.AgentKronigIDEState.controlsForState("running");
assertEqual(runningControls.pause, true, "running work can be paused");
assertEqual(runningControls.stop, true, "running work can be stopped");
assertEqual(runningControls.send, false, "another prompt cannot start while running");
const pausedControls = globalThis.AgentKronigIDEState.controlsForState("paused");
assertEqual(pausedControls.resume, true, "paused work can be resumed");
const finishedControls = globalThis.AgentKronigIDEState.controlsForState("completed");
assertEqual(finishedControls.send, true, "a terminal run re-enables prompting");

assertEqual(
  globalThis.AgentKronigIDEState.isActiveState("waiting_for_approval"),
  true,
  "approval waits should continue background synchronization",
);
assertEqual(
  globalThis.AgentKronigIDEState.isActiveState("waiting_for_plan_approval"),
  true,
  "plan review remains part of the active run lifecycle",
);
assertEqual(
  globalThis.AgentKronigIDEState.isActiveState("completed"),
  false,
  "terminal runs should not trigger active-run polling",
);

const runResources = globalThis.AgentKronigIDEState.createRunResourceCache();
runResources.select("run-1");
runResources.put("run-1", {files: [{path: "first.py"}]});
assertEqual(runResources.current().files[0].path, "first.py", "selected run receives its own changes");
runResources.select("run-2");
assertEqual(runResources.current(), null, "new run never inherits the previous run changes");
runResources.put("run-1", {files: [{path: "stale.py"}]});
assertEqual(runResources.current(), null, "late response for another run cannot become current");
runResources.put("run-2", {files: [{path: "second.py"}]});
assertEqual(runResources.current().files[0].path, "second.py", "current run accepts its matching response");

const repositoryRequests = globalThis.AgentKronigIDEState.createRepositoryRequestCoordinator();
const firstRepositoryRequest = repositoryRequests.beginNavigation("models");
assertEqual(repositoryRequests.currentPath(), "models", "navigation records its intended path before awaiting");
assertEqual(
  repositoryRequests.beginRefresh(),
  null,
  "background refresh cannot supersede pending user navigation",
);
const secondRepositoryRequest = repositoryRequests.beginNavigation("results");
assertEqual(repositoryRequests.isCurrent(firstRepositoryRequest), false, "stale repository responses are ignored");
assertEqual(repositoryRequests.isCurrent(secondRepositoryRequest), true, "latest repository response is accepted");
assertEqual(
  repositoryRequests.finish(secondRepositoryRequest),
  false,
  "a deferred refresh waits for every foreground navigation to settle",
);
assertEqual(
  repositoryRequests.finish(firstRepositoryRequest),
  true,
  "the final foreground completion replays one coalesced repository refresh",
);
const backgroundRepositoryRequest = repositoryRequests.beginRefresh();
const thirdRepositoryRequest = repositoryRequests.beginNavigation("plots");
assertEqual(
  repositoryRequests.isCurrent(backgroundRepositoryRequest),
  false,
  "later navigation supersedes an in-flight background refresh",
);
assertEqual(repositoryRequests.isCurrent(thirdRepositoryRequest), true, "foreground navigation remains current");
repositoryRequests.finish(thirdRepositoryRequest);
assertEqual(
  globalThis.AgentKronigIDEState.shouldRefreshRepository("tool_call_completed"),
  true,
  "completed tools refresh the repository tree",
);
assertEqual(
  globalThis.AgentKronigIDEState.shouldRefreshRepository("run_completed"),
  true,
  "terminal runs perform a final repository refresh",
);
assertEqual(
  globalThis.AgentKronigIDEState.shouldRefreshRepository("tool_call_started"),
  false,
  "starting a tool does not issue a premature refresh",
);

assertEqual(
  globalThis.AgentKronigIDEState.shouldAutoFollowChat("message-1", "message-2", true, false),
  true,
  "a new message follows when the reader is already near the bottom",
);
assertEqual(
  globalThis.AgentKronigIDEState.shouldAutoFollowChat("message-1", "message-2", false, false),
  false,
  "a new message preserves the reader's position when they scrolled up",
);
assertEqual(
  globalThis.AgentKronigIDEState.shouldAutoFollowProgress(true, true),
  true,
  "live progress follows when the reader is already near the bottom",
);
assertEqual(
  globalThis.AgentKronigIDEState.shouldAutoFollowProgress(true, false),
  false,
  "live progress does not steal the reader's scroll position",
);
assertEqual(
  globalThis.AgentKronigIDEState.shouldAutoFollowChat("message-2", "message-2", true, false),
  false,
  "unchanged polling data does not force a scroll",
);
assertEqual(
  globalThis.AgentKronigIDEState.shouldAutoFollowChat("message-2", "message-2", false, true),
  true,
  "an explicit send can always request bottom alignment",
);

let refreshCalls = 0;
let releaseRefresh;
const refreshCoordinator = globalThis.AgentKronigIDEState.createRefreshCoordinator(
  () => {
    refreshCalls += 1;
    return new Promise((resolve) => { releaseRefresh = resolve; });
  },
);
const firstRefresh = refreshCoordinator.request("session-b");
const duplicateRefresh = refreshCoordinator.request("session-b");
assertEqual(firstRefresh, duplicateRefresh, "overlapping refreshes should be coalesced");
assertEqual(refreshCalls, 1, "coalesced refreshes should issue one request");
releaseRefresh();
Promise.all([firstRefresh, duplicateRefresh]).then(async () => {
  const nextRefresh = refreshCoordinator.request("session-b");
  assertEqual(refreshCalls, 2, "a completed refresh should allow the next sync");
  releaseRefresh();
  await nextRefresh;
}).catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
