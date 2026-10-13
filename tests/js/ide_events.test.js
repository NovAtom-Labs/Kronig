"use strict";

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(`${message}: ${actual}`);
}

function event(id, kind, payload = {}) {
  return {id, kind, payload, created_at: `2026-09-25T10:00:${String(id).padStart(2, "0")}Z`};
}

function toolStarted(id, actionId, toolName, summary, subagent = null, runId = "run-1") {
  return event(id, "tool_call_started", {
    run_id: runId,
    action_id: actionId,
    tool_call_id: `call-${actionId}`,
    tool_name: toolName,
    summary,
    subagent,
    phase: toolName === "terminal" ? "validate" : "inspect",
    evidence_kind: toolName === "terminal" ? "validation" : null,
  });
}

function toolCompleted(id, actionId, toolName, output, subagent = null, runId = "run-1") {
  return event(id, "tool_call_completed", {
    run_id: runId,
    action_id: actionId,
    tool_call_id: `call-${actionId}`,
    tool_name: toolName,
    output,
    subagent,
    is_error: false,
  });
}

const view = globalThis.AgentKronigIDEEvents.createRunPresentation();
view.accept(event(1, "conversation_created"));
view.accept(event(2, "run_started", {run_id: "run-1"}));
view.accept(toolStarted(11, "action-1", "terminal", "Run focused tests"));
view.accept(toolCompleted(12, "action-1", "terminal", "2 passed"));
view.accept(toolCompleted(12, "action-1", "terminal", "2 passed"));

let snapshot = view.snapshot();
assertEqual(snapshot.steps.length, 1, "start and completion form one step");
assertEqual(snapshot.steps[0].status, "completed", "completion closes step");
assertEqual(snapshot.steps[0].output, "2 passed", "tool evidence is retained");
assertEqual(snapshot.steps[0].phase, "validate", "structured phase metadata is retained");
assertEqual(snapshot.steps[0].evidenceKind, "validation", "structured evidence type is retained");
assertEqual(snapshot.lastEventId, 12, "duplicate replay is ignored");
assertEqual(snapshot.technicalEvents.length, 0, "conversation lifecycle noise is excluded from run state");

const researchView = globalThis.AgentKronigIDEEvents.createRunPresentation();
researchView.accept(event(125, "tool_call_started", {
  run_id: "run-1",
  action_id: "research-1",
  tool_call_id: "call-research-1",
  tool_name: "tcad_domain",
  summary: "tcad_domain: search_web",
  phase: "inspect",
  evidence_kind: "research",
  research_scope: "web",
  arguments: {operation: "search_web"},
}));
const researchSnapshot = researchView.snapshot();
assertEqual(researchSnapshot.steps.at(-1).evidenceKind, "research", "research evidence remains distinct from validation");
assertEqual(researchSnapshot.steps.at(-1).researchScope, "web", "web research scope survives event reduction");

view.accept(toolStarted(13, "action-2", "task", "Delegate validation", "science-checker"));
snapshot = view.snapshot();
assertEqual(snapshot.steps[1].subagent, "science-checker", "subagent ownership is retained");

view.accept(event(14, "thinking_started", {run_id: "run-1", item_id: "reason-1"}));
view.accept(event(15, "thinking_delta", {run_id: "run-1", item_id: "reason-1", content: "private hidden reasoning"}));
view.accept(event(16, "thinking_aborted", {run_id: "run-1", item_id: "reason-1", reason: "redirected"}));
snapshot = view.snapshot();
assertEqual(snapshot.reasoning.length, 0, "raw provider reasoning is never presented");
assertEqual(JSON.stringify(snapshot).includes("private hidden reasoning"), false, "raw reasoning cannot leak through snapshot state");

view.accept(event(160, "agent_progress_started", {run_id: "run-1", item_id: "inference-1"}));
snapshot = view.snapshot();
assertEqual(snapshot.inference.status, "running", "safe inference lifecycle becomes live progress");
assertEqual(snapshot.inference.label, "Analyzing context and choosing the next action", "inference progress is content free");
view.accept(event(161, "agent_progress_interrupted", {run_id: "run-1", item_id: "inference-1"}));
assertEqual(view.snapshot().inference.status, "interrupted", "interrupted inference does not remain live");
assertEqual(JSON.stringify(view.snapshot()).includes("private hidden reasoning"), false, "safe lifecycle never recovers discarded reasoning");

view.accept(event(18, "approval_requested", {run_id: "run-1", approval_id: "approval-1", summary: "Allow network access"}));
assertEqual(view.snapshot().pendingApprovals.length, 1, "pending approval survives in presentation state");
view.accept(event(19, "approval_resolved", {run_id: "run-1", approval_id: "approval-1", decision: "deny"}));
assertEqual(view.snapshot().pendingApprovals.length, 0, "resolved approval leaves pending state");
assertEqual(view.snapshot().approvalHistory.length, 1, "approval remains visible in run activity");
assertEqual(view.snapshot().approvalHistory[0].decision, "deny", "approval outcome is retained");

view.accept(event(20, "run_state_changed", {run_id: "run-1", state: "running"}));
view.accept(event(21, "run_failed", {run_id: "run-1", detail: "validation failed"}));
snapshot = view.snapshot();
assertEqual(snapshot.runState, "failed", "terminal event determines run state");
assertEqual(snapshot.runId, "run-1", "run identity survives event restoration");
assertEqual(snapshot.currentOperation, "Run failed", "terminal state has a useful operation label");
assertEqual(snapshot.terminalDetail, "validation failed", "terminal failure detail remains available to the UI");

view.accept(event(22, "run_started", {run_id: "run-2"}));
view.accept(toolStarted(23, "action-3", "file_editor", "Inspect second run", null, "run-2"));
view.accept(toolCompleted(24, "action-3", "file_editor", "second run only", null, "run-2"));
snapshot = view.snapshot();
assertEqual(snapshot.runId, "run-2", "latest run becomes selected");
assertEqual(snapshot.steps.length, 1, "latest run does not inherit earlier tool steps");
assertEqual(snapshot.steps[0].output, "second run only", "latest run evidence is isolated");
assertEqual(view.snapshot("run-1").steps.length, 2, "an earlier run remains independently retrievable");

const restored = globalThis.AgentKronigIDEEvents.createRunPresentation();
[
  event(1, "conversation_created"),
  event(2, "run_started", {run_id: "run-1"}),
  toolStarted(11, "action-1", "terminal", "Run focused tests"),
  toolCompleted(12, "action-1", "terminal", "2 passed"),
].forEach((item) => restored.accept(item));
assertEqual(
  JSON.stringify(restored.snapshot().steps),
  JSON.stringify(view.snapshot("run-1").steps.slice(0, 1)),
  "restored and live events reduce to the same step shape",
);

view.reset();
assertEqual(view.snapshot().lastEventId, 0, "reset clears the cursor");
assertEqual(view.snapshot().steps.length, 0, "reset clears steps");

const preparationView = globalThis.AgentKronigIDEEvents.createRunPresentation();
preparationView.accept(event(201, "run_created", {run_id: "run-prep", state: "queued"}));
snapshot = preparationView.snapshot();
assertEqual(snapshot.runState, "queued", "a newly created preparation run is visible immediately");
preparationView.accept(event(202, "prompt_preparation_started", {
  run_id: "run-prep",
  phase: "understanding_request",
}));
assertEqual(
  preparationView.snapshot().currentOperation,
  "Understanding the research request",
  "request understanding is visible before tool execution",
);
preparationView.accept(event(203, "prompt_preparation_progress", {
  run_id: "run-prep",
  phase: "reviewing_workspace",
}));
assertEqual(
  preparationView.snapshot().currentOperation,
  "Reviewing repository context",
  "workspace review remains visible while preparation is running",
);
preparationView.accept(event(204, "prompt_preparation_progress", {
  run_id: "run-prep",
  phase: "consulting_local_knowledge",
}));
preparationView.accept(event(205, "prompt_preparation_progress", {
  run_id: "run-prep",
  phase: "reasoning_about_scientific_intent",
}));
snapshot = preparationView.snapshot();
assertEqual(snapshot.preparationStages.length, 4, "preparation milestones are preserved instead of overwritten");
assertEqual(snapshot.preparationStages[0].label, "Understanding the research request", "request intake is the first milestone");
assertEqual(snapshot.preparationStages[3].label, "Resolving the scientific intent", "model reasoning has a safe public label");
preparationView.accept(event(206, "clarification_required", {
  run_id: "run-prep",
  question_count: 2,
}));
snapshot = preparationView.snapshot();
assertEqual(snapshot.runState, "waiting_for_user", "clarification updates the visible run state");
assertEqual(snapshot.currentOperation, "Waiting for your response", "clarification names the next action");

const failedPreparationView = globalThis.AgentKronigIDEEvents.createRunPresentation();
failedPreparationView.accept(event(207, "run_created", {run_id: "run-failed-prep", state: "queued"}));
failedPreparationView.accept(event(208, "prompt_preparation_started", {
  run_id: "run-failed-prep",
  phase: "understanding_request",
}));
failedPreparationView.accept(event(209, "agent_progress_started", {
  run_id: "run-failed-prep",
  item_id: "inference-failed-prep",
}));
failedPreparationView.accept(event(210, "run_failed", {
  run_id: "run-failed-prep",
  detail: "preparation failed",
}));
snapshot = failedPreparationView.snapshot();
assertEqual(snapshot.runState, "failed", "preparation failure reaches a terminal state");
assertEqual(
  snapshot.preparationStages.some((stage) => stage.status === "running"),
  false,
  "terminal failure settles every live preparation stage",
);
assertEqual(snapshot.inference.status, "interrupted", "terminal failure stops live inference");

const planView = globalThis.AgentKronigIDEEvents.createRunPresentation();
planView.accept(event(210, "run_started", {run_id: "run-plan"}));
planView.accept(event(211, "plan_ready", {
  run_id: "run-plan",
  plan_digest: "a".repeat(64),
  plan_path: "/repo/experiments/bias-study/PLAN.md",
  revision: 0,
}));
snapshot = planView.snapshot();
assertEqual(snapshot.runState, "waiting_for_plan_approval", "a prepared plan has a dedicated state");
assertEqual(snapshot.currentOperation, "Experiment plan ready for review", "plan review names the next action");
assertEqual(snapshot.plan.planDigest, "a".repeat(64), "typed plan metadata is retained");
planView.accept(event(211.1, "run_paused", {run_id: "run-plan"}));
assertEqual(planView.snapshot().runState, "waiting_for_plan_approval", "SDK pause must not overwrite plan review");
planView.accept(event(211.2, "run_state_changed", {run_id: "run-plan", state: "paused"}));
assertEqual(planView.snapshot().runState, "waiting_for_plan_approval", "SDK paused state preserves a pending plan");
planView.accept(event(212, "plan_approved", {
  run_id: "run-plan",
  plan_digest: "a".repeat(64),
  approval_mode: "review_each_risk",
}));
assertEqual(planView.snapshot().runState, "running", "plan approval resumes the same run");

planView.accept(event(213, "result_ready", {
  run_id: "run-plan",
  bundle_run_id: "experiment-0001",
  execution_state: "completed",
  validation_state: "needs_review",
  deliverable_state: "incomplete",
  report_state: "complete",
  overall_state: "needs_attention",
  failed_check_count: 2,
  unmet_deliverables: ["electron_density"],
}));
const resultSnapshot = planView.snapshot("run-plan");
assertEqual(resultSnapshot.resultReady.overallState, "needs_attention", "structured outcome is retained");
assertEqual(resultSnapshot.resultReady.failedCheckCount, 2, "failed check count is retained");
snapshot = planView.snapshot();
assertEqual(snapshot.resultReady.bundleRunId, "experiment-0001", "managed result metadata reaches the UI");
assertEqual(snapshot.resultReady.validationState, "needs_review", "validation review remains distinct from execution");
