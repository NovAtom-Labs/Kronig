"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual}`);
}

const agent = globalThis.AgentKronigAgentView;
const rows = agent.activityRows({
  steps: [{
    id: "action-1",
    toolName: "terminal",
    summary: "Run focused tests",
    status: "completed",
    startedAt: "2026-09-25T10:00:00Z",
    completedAt: "2026-09-25T10:00:02Z",
    output: "2 passed",
    arguments: {command: "pytest tests/test_science.py -q"},
    subagent: "science-checker",
    isError: false,
    phase: "validate",
    evidenceKind: "validation",
  }],
  technicalEvents: [{kind: "conversation_created"}],
});
assertEqual(rows.length, 1, "lifecycle noise is absent from default activity");
assertEqual(rows[0].owner, "science-checker", "subagent ownership stays with the step");
assertEqual(rows[0].duration, "2.0s", "step duration is derived from event timestamps");
assertEqual(rows[0].command, "pytest tests/test_science.py -q", "technical command remains inspectable");
assertEqual(rows[0].phase, "Validate", "test execution is classified as validation evidence");
assertEqual(
  agent.affectedFilePaths(
    {path: "/repo/src/physics.py", affectedPaths: ["src/physics.py"]},
    "/repo",
  ).join(","),
  "src/physics.py",
  "completion evidence replaces duplicate absolute action paths",
);
assertEqual(
  agent.affectedFilePaths({path: "/repo/src/mesh.py", affectedPaths: []}, "/repo")[0],
  "src/mesh.py",
  "absolute action paths are normalized to the repository",
);

const progress = agent.operationalUpdates({
  runState: "running",
  steps: [
    {
      id: "plan-1",
      toolName: "task_tracker",
      summary: "task_tracker: update 2 tasks",
      status: "completed",
      phase: "plan",
      arguments: {tasks: [
        {title: "Inspect simulator inputs", status: "done"},
        {title: "Run validation", status: "in_progress"},
      ]},
    },
    {
      id: "think-1",
      toolName: "think",
      summary: "think: internal planning",
      status: "completed",
      phase: "plan",
    },
    {
      id: "validate-1",
      toolName: "terminal",
      summary: "terminal: pytest -q",
      status: "running",
      phase: "validate",
      arguments: {command: "pytest -q"},
    },
  ],
  pendingApprovals: [],
});
assertEqual(progress[0].label, "Understanding the request and preparing an approach", "run start has a useful safe update");
assertEqual(progress[1].label, "Plan updated", "task tracker becomes a plan update");
assertEqual(progress[1].detail, "Inspect simulator inputs · Run validation", "plan titles are visible without hidden notes");
assertEqual(progress[2].label, "Reviewing evidence and choosing the next action", "internal thought content is replaced by a safe summary");
assertEqual(progress[3].label, "Running validation", "active validation has a plain-language label");
assertEqual(progress[3].detail, "pytest -q", "technical evidence stays inspectable");
assertEqual(JSON.stringify(progress).includes("internal planning"), false, "private reasoning labels never leak into progress");

const webResearch = agent.operationalUpdates({
  runState: "running",
  steps: [{
    id: "research-1",
    toolName: "tcad_domain",
    summary: "tcad_domain: search_web",
    status: "running",
    phase: "inspect",
    evidenceKind: "research",
    researchScope: "web",
    arguments: {operation: "search_web"},
  }],
  pendingApprovals: [],
});
assertEqual(webResearch.at(-1).label, "Searching scientific sources", "web research has a clear scientific activity label");
assertEqual(webResearch.at(-1).detail, null, "web research does not expose technical tool syntax in chat");

const researchTrail = agent.researchTrail({
  runState: "running",
  steps: Array.from({length: 8}, (_, index) => ({
    id: `step-${index}`,
    toolName: index === 3 ? "think" : "terminal",
    summary: index === 3 ? "private chain of thought" : `terminal: check-${index}`,
    status: index === 7 ? "running" : "completed",
    phase: index > 5 ? "validate" : "inspect",
    arguments: index === 3 ? {} : {command: `check-${index}`},
  })),
  pendingApprovals: [],
});
assertEqual(researchTrail.stages.length, 2, "chat groups repeated actions into research phases");
assertEqual(researchTrail.stages[0].phase, "Repository", "inspection is presented as repository research");
assertEqual(researchTrail.stages[0].actionCount, 6, "grouped phase preserves its action count");
assertEqual(researchTrail.stages[1].phase, "Validation", "validation remains a distinct research phase");
assertEqual(researchTrail.current.label, "Running validation", "the active scientific operation is prominent");
assertEqual(researchTrail.recent.length, 4, "chat keeps a bounded recent operational record");
assertEqual(researchTrail.recent.at(-1).label, "Running validation", "the latest public action remains visible");
assertEqual(JSON.stringify(researchTrail).includes("check-7"), false, "raw commands stay out of the chat trail");
assertEqual(JSON.stringify(researchTrail).includes("private chain of thought"), false, "chat trail never exposes private reasoning");

const recoveredTrail = agent.researchTrail({
  runState: "running",
  steps: [
    {id: "invalid-1", status: "failed", phase: "validate", toolName: "terminal", summary: "invalid_spec"},
    {id: "edit-1", status: "completed", phase: "edit", toolName: "file_editor", summary: "Corrected schema"},
    {id: "validate-1", status: "running", phase: "validate", toolName: "terminal", summary: "Retry validation"},
  ],
  pendingApprovals: [],
});
assertEqual(recoveredTrail.recovery !== null, true, "resolved intermediate failures become one neutral recovery note");
assertEqual(recoveredTrail.recovery.includes("resolved automatically"), true, "recovery note explains that no researcher action was needed");
assertEqual(recoveredTrail.stages.some((stage) => stage.status === "failed"), false, "recovered attempts do not look like terminal failures in chat");

const queuedTrail = agent.researchTrail({
  runState: "queued",
  steps: [],
  pendingApprovals: [],
});
assertEqual(queuedTrail.current.label, "Preparing the research approach", "a new run starts with an honest narrative state");

const preparingTrail = agent.researchTrail({
  runState: "queued",
  currentOperation: "Checking local scientific evidence",
  steps: [],
  pendingApprovals: [],
});
assertEqual(preparingTrail.current.label, "Checking local scientific evidence", "preparation events drive the notebook narrative");
assertEqual(preparingTrail.title, "Preparing request", "preprocessing uses a task-neutral title");
assertEqual(preparingTrail.meta, "Live", "preparation does not claim that zero actions is useful progress");

const clarificationTrail = agent.researchTrail({
  runState: "waiting_for_user",
  currentOperation: "Waiting for your response",
  steps: [],
  pendingApprovals: [],
});
assertEqual(clarificationTrail.title, "Input needed", "clarification has an explicit notebook title");
assertEqual(clarificationTrail.current.label, "Waiting for your response", "clarification keeps the next action visible");
assertEqual(clarificationTrail.meta, "Input needed", "clarification never displays a misleading zero-action count");

const planReview = agent.planReview({
  status: "pending",
  revision: 2,
  plan_digest: "f".repeat(64),
  plan_path: "/repo/experiments/implant-study/PLAN.md",
  prepared: {
    backend: "devsim",
    warnings: ["Absolute current requires contact area."],
    spec: {
      name: "Compensated silicon implant",
      study: {kind: "dc_points"},
      regions: [{id: "silicon"}],
      contacts: [{id: "left"}, {id: "right"}],
      observables: ["potential", "terminal_current_density"],
    },
    completeness: {records: [{status: "resolved"}, {status: "resolved"}]},
  },
});
assertEqual(planReview.visible, true, "a pending typed plan has a dedicated review view");
assertEqual(planReview.title, "Compensated silicon implant", "plan review uses the research title");
assertEqual(planReview.study, "DC points", "study kind is presented plainly");
assertEqual(planReview.planPath, "experiments/implant-study/PLAN.md", "plan path is repository relative");
assertEqual(planReview.warningCount, 1, "plan warnings remain visible before execution");

const planTrail = agent.researchTrail({
  runState: "waiting_for_plan_approval",
  currentOperation: "Experiment plan ready for review",
  steps: [],
  pendingApprovals: [],
});
assertEqual(planTrail.title, "Plan ready", "plan approval is distinct from a tool permission");
assertEqual(planTrail.meta, "Review needed", "plan gate states the required researcher action");

const betweenActions = agent.operationalUpdates({
  runState: "running",
  steps: [{
    id: "inspect-1",
    toolName: "file_editor",
    summary: "file_editor view: experiment.yaml",
    status: "completed",
    phase: "inspect",
    arguments: {path: "experiment.yaml"},
  }],
  pendingApprovals: [],
});
assertEqual(betweenActions.at(-1).label, "Reviewing results and choosing the next action", "quiet model time remains visibly active");
assertEqual(betweenActions.at(-1).status, "running", "between-tool progress remains live");

const waiting = agent.operationalUpdates({
  runState: "waiting_for_approval",
  steps: [],
  pendingApprovals: [{summary: "Allow remote execution"}],
});
assertEqual(waiting.at(-1).label, "Waiting for your approval", "approval wait is explicit");
assertEqual(waiting.at(-1).detail, "Allow remote execution", "approval reason stays visible");

const inferring = agent.operationalUpdates({
  runState: "running",
  steps: [],
  pendingApprovals: [],
  inference: {
    id: "inference-1",
    label: "Analyzing context and choosing the next action",
    status: "running",
  },
});
assertEqual(inferring.at(-1).label, "Analyzing context and choosing the next action", "live model work uses the safe lifecycle label");
assertEqual(inferring.at(-1).status, "running", "model lifecycle drives the live state");

const emptyCompleted = agent.operationalUpdates({
  runState: "completed",
  steps: [],
  pendingApprovals: [],
});
assertEqual(emptyCompleted[0].status, "completed", "an empty terminal run never appears to remain active");

const completed = agent.outcomeSummary(
  {runState: "completed", steps: rows, currentOperation: "Run completed"},
  {files: [
    {path: "src/physics.py", validation_action_ids: ["action-1"]},
    {path: "report.md"},
  ]},
);
assertEqual(completed.tone, "success", "completed run uses success treatment");
assertEqual(completed.title, "Run completed", "completion title is explicit");
assertEqual(completed.changedFiles, 2, "completion includes changed file count");
assertEqual(completed.completedSteps, 1, "completion includes finished steps");
assertEqual(completed.changedPaths.join(","), "src/physics.py,report.md", "completion names changed files");
assertEqual(completed.validationEvidence.length, 1, "successful validation action becomes evidence");
assertEqual(completed.unlinkedValidationChecks.length, 0, "linked validation is not called stale");
assertEqual(completed.commands[0], "pytest tests/test_science.py -q", "completion retains executed commands");
assertEqual(completed.nextActions.length, 1, "completed runs provide a grounded next action");

const staleCheck = agent.outcomeSummary(
  {runState: "completed", steps: rows, currentOperation: "Run completed"},
  {files: [{path: "src/physics.py", validation_action_ids: []}]},
);
assertEqual(staleCheck.validationEvidence.length, 0, "stale check is not final evidence");
assertEqual(staleCheck.unlinkedValidationChecks.length, 1, "stale check remains visible as executed");

const honest = agent.activityRows({steps: [{
  id: "action-2",
  toolName: "file_editor",
  summary: "Read checks/input.txt",
  status: "completed",
  arguments: {command: "view", path: "checks/input.txt"},
  phase: "inspect",
}]});
assertEqual(honest[0].phase, "Inspect", "phase comes from structured backend metadata, not path keywords");
const noInferredArtifact = agent.outcomeSummary(
  {runState: "completed", steps: honest},
  {files: [{path: "reports/notes.txt", artifact: false}]},
);
assertEqual(noInferredArtifact.artifacts.length, 0, "artifact status is never inferred from a folder name");

const failed = agent.outcomeSummary(
  {
    runState: "failed",
    steps: [
      {status: "completed", summary: "Inspect files"},
      {status: "failed", summary: "Run validation", output: "assertion failed"},
    ],
    currentOperation: "Run failed",
  },
  {files: [{path: "src/physics.py"}]},
);
assertEqual(failed.tone, "danger", "failed run uses failure treatment");
assertEqual(failed.failedStep, "Run validation", "failure keeps the failed step");
assertEqual(failed.lastSuccessfulStep, "Inspect files", "failure keeps partial evidence");

const needsAttention = agent.outcomeSummary(
  {
    runState: "blocked",
    steps: rows,
    resultReady: {
      executionState: "completed",
      validationState: "needs_review",
      deliverableState: "incomplete",
      reportState: "complete",
      overallState: "needs_attention",
      failedCheckCount: 2,
      unmetDeliverables: ["electron_density"],
    },
  },
  {files: []},
);
assertEqual(needsAttention.tone, "warning", "scientific review state is not shown as success or generic failure");
assertEqual(needsAttention.title, "Results ready, checks need attention", "review outcome is humanized");
assertEqual(needsAttention.failedCheckCount, 2, "exact failed-check count remains visible");
assertEqual(needsAttention.unmetDeliverables[0], "electron_density", "missing requested evidence remains visible");

const permission = agent.permissionView({
  summary: "Agent Kronig wants to access a path outside this repository.",
  tool_name: "terminal",
  permission_category: "external_file_access",
  risk: "HIGH",
  payload: {command: "cat /shared/reference.dat"},
});
assertEqual(permission.explanation.includes("outside this repository"), true, "plain explanation is primary");
assertEqual(permission.target, "cat /shared/reference.dat", "exact technical target is retained");
assertEqual(permission.canApproveCategory, true, "narrow category can be approved for the run");
assertEqual(permission.technicalArguments.includes("cat /shared/reference.dat"), true, "all sanitized arguments remain inspectable");
assertEqual(permission.reversibility.includes("Read-only"), true, "read-only permission explains reversibility");
const redacted = agent.permissionView({
  payload: {command: "curl example.test", api_key: "never-show-this"},
  permission_category: "network_access",
});
assertEqual(redacted.technicalArguments.includes("never-show-this"), false, "sensitive argument values are redacted");
assertEqual(redacted.technicalArguments.includes("[redacted]"), true, "redaction is explicit");
assertEqual(
  agent.permissionView({...permission, permission_category: "complex_shell"}).canApproveCategory,
  false,
  "broad shell permission cannot be approved for the run",
);

const approvalQueue = [
  {id: "approval-1", summary: "Read a reference file"},
  {id: "approval-2", summary: "Run a combined validation command"},
  {id: "approval-3", summary: "Contact the licensed simulator"},
];
const selectedApproval = agent.approvalDeck(approvalQueue, "approval-2");
assertEqual(selectedApproval.active.id, "approval-2", "the selected approval remains visible after refresh");
assertEqual(selectedApproval.position, 2, "approval position is one based for researchers");
assertEqual(selectedApproval.total, 3, "approval count includes the full pending queue");
assertEqual(selectedApproval.canPrevious, true, "middle approvals can navigate backward");
assertEqual(selectedApproval.canNext, true, "middle approvals can navigate forward");
assertEqual(
  agent.approvalDeck(approvalQueue, "approval-missing").active.id,
  "approval-1",
  "a resolved approval falls back to the first pending decision",
);
assertEqual(agent.approvalDeck([], null).active, null, "an empty queue closes the approval drawer");
assertEqual(agent.moveApproval(1, 3, -1), 0, "previous approval navigation is bounded");
assertEqual(agent.moveApproval(1, 3, 1), 2, "next approval navigation is bounded");
assertEqual(agent.moveApproval(0, 3, -1), 0, "navigation never wraps unexpectedly");
assertEqual(
  agent.approvalKeyAction({key: "Escape"}),
  "minimize",
  "escape minimizes rather than approving or denying",
);
assertEqual(
  agent.approvalKeyAction({key: "Tab", shiftKey: true, atFirst: true}),
  "focus-last",
  "reverse tab stays inside the approval drawer",
);
assertEqual(
  agent.approvalKeyAction({key: "Tab", atLast: true}),
  "focus-first",
  "forward tab stays inside the approval drawer",
);
assertEqual(
  agent.approvalKeyAction({key: "Tab", atFirst: false, atLast: false}),
  "none",
  "ordinary tab order remains native inside the drawer",
);
assertEqual(
  agent.approvalKeyAction({key: "Tab", shiftKey: true, atContainer: true}),
  "focus-last",
  "reverse tab from the drawer container cannot escape into dimmed chat",
);
assertEqual(
  agent.approvalKeyAction({key: "Tab", atContainer: true}),
  "focus-first",
  "forward tab from the drawer container starts at its first control",
);
