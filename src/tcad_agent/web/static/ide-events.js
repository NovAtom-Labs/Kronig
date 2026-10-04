"use strict";

(() => {
  const terminalStates = {
    run_completed: "completed",
    run_failed: "failed",
    run_blocked: "blocked",
    run_cancelled: "cancelled",
    run_paused: "paused",
    run_recovered_paused: "paused",
  };
  const ignoredKinds = new Set([
    "conversation_created",
    "message_created",
    "thinking_started",
    "thinking_delta",
    "thinking_aborted",
  ]);

  function emptyRun(runId = null) {
    return {
      runId,
      runState: "idle",
      currentOperation: "Idle",
      steps: [],
      stepsByKey: new Map(),
      pendingApprovals: new Map(),
      approvalHistory: [],
      approvalsById: new Map(),
      technicalEvents: [],
      inference: null,
      preparationStages: [],
      plan: null,
      resultReady: null,
    };
  }

  function createRunPresentation() {
    const seen = new Set();
    const runs = new Map();
    let selectedRunId = null;
    let lastEventId = 0;

    function stateFor(runId) {
      if (!runs.has(runId)) runs.set(runId, emptyRun(runId));
      return runs.get(runId);
    }

    function actionKey(payload, event) {
      return String(payload.action_id || payload.tool_call_id || `event-${event.id}`);
    }

    function startTool(state, event) {
      const payload = event.payload || {};
      const key = actionKey(payload, event);
      let step = state.stepsByKey.get(key);
      if (!step) {
        step = {
          id: key,
          actionId: payload.action_id || null,
          toolCallId: payload.tool_call_id || null,
          toolName: payload.tool_name || "tool",
          summary: payload.summary || payload.tool_name || "Tool call",
          status: "running",
          startedAt: event.created_at || null,
          completedAt: null,
          output: null,
          isError: false,
          arguments: payload.arguments || null,
          subagent: payload.subagent || null,
          taskStatus: null,
          phase: payload.phase || "unknown",
          evidenceKind: payload.evidence_kind || null,
          researchScope: payload.research_scope || null,
          affectedPaths: payload.affected_paths || [],
          artifactPaths: payload.artifact_paths || [],
          provenance: payload.provenance || null,
        };
        state.stepsByKey.set(key, step);
        state.steps.push(step);
      }
      state.currentOperation = step.summary;
    }

    function completeTool(state, event) {
      const payload = event.payload || {};
      const key = actionKey(payload, event);
      let step = state.stepsByKey.get(key);
      if (!step && payload.tool_call_id) {
        step = state.steps.find((item) => item.toolCallId === payload.tool_call_id);
      }
      if (!step) {
        step = {
          id: key,
          actionId: payload.action_id || null,
          toolCallId: payload.tool_call_id || null,
          toolName: payload.tool_name || "tool",
          summary: payload.summary || payload.tool_name || "Tool call",
          status: "running",
          startedAt: null,
          completedAt: null,
          output: null,
          isError: false,
          arguments: null,
          subagent: null,
          taskStatus: null,
          phase: payload.phase || "unknown",
          evidenceKind: payload.evidence_kind || null,
          researchScope: payload.research_scope || null,
          affectedPaths: payload.affected_paths || [],
          artifactPaths: payload.artifact_paths || [],
          provenance: payload.provenance || null,
        };
        state.stepsByKey.set(key, step);
        state.steps.push(step);
      }
      step.completedAt = event.created_at || null;
      step.output = payload.output || "";
      step.isError = Boolean(payload.is_error);
      step.status = step.isError ? "failed" : "completed";
      step.subagent = payload.subagent || step.subagent;
      step.taskStatus = payload.task_status || null;
      step.affectedPaths = payload.affected_paths || step.affectedPaths;
      step.artifactPaths = payload.artifact_paths || step.artifactPaths;
      step.provenance = payload.provenance || step.provenance;
      step.researchScope = payload.research_scope || step.researchScope;
      state.currentOperation = step.isError ? `${step.summary} failed` : step.summary;
    }

    const preparationLabels = {
      understanding_request: "Understanding the research request",
      reviewing_workspace: "Reviewing repository context",
      consulting_local_knowledge: "Consulting local TCAD knowledge",
      reasoning_about_scientific_intent: "Resolving the scientific intent",
      compiling_request: "Compiling the executable request",
      checking_local_evidence: "Checking local scientific evidence",
    };

    function setPreparationStage(state, phase, event) {
      state.preparationStages.forEach((stage) => {
        if (stage.status === "running") stage.status = "completed";
      });
      const label = preparationLabels[phase] || "Preparing the research request";
      const existing = state.preparationStages.find((stage) => stage.phase === phase);
      if (existing) {
        existing.label = label;
        existing.status = "running";
        existing.startedAt = event.created_at || existing.startedAt;
      } else {
        state.preparationStages.push({
          phase,
          label,
          status: "running",
          startedAt: event.created_at || null,
        });
      }
      state.currentOperation = label;
    }

    function completePreparation(state) {
      state.preparationStages.forEach((stage) => {
        if (stage.status === "running") stage.status = "completed";
      });
    }

    function updateRunState(state, event) {
      const payload = event.payload || {};
      if (event.kind === "run_created") {
        state.runState = String(payload.state || "queued");
      } else if (event.kind === "run_state_changed" && payload.state) {
        state.runState = String(payload.state);
      } else if (terminalStates[event.kind]) {
        state.runState = terminalStates[event.kind];
      } else if (event.kind === "run_started") {
        state.runState = "running";
      } else if (event.kind === "approval_requested") {
        state.runState = "waiting_for_approval";
      } else if (event.kind === "clarification_required") {
        state.runState = "waiting_for_user";
      } else if (event.kind === "plan_ready") {
        state.runState = "waiting_for_plan_approval";
      } else if (["plan_approved", "plan_revision_requested"].includes(event.kind)) {
        state.runState = "running";
      }
      const labels = {
        completed: "Run completed",
        failed: "Run failed",
        blocked: "Run blocked",
        cancelled: "Run cancelled",
        paused: "Run paused",
        waiting_for_approval: "Waiting for approval",
        waiting_for_plan_approval: "Experiment plan ready for review",
        waiting_for_user: "Waiting for your response",
      };
      if (labels[state.runState]) state.currentOperation = labels[state.runState];
    }

    function accept(event) {
      if (!event || event.id === undefined || seen.has(String(event.id))) return false;
      seen.add(String(event.id));
      const numericId = Number(event.id);
      if (Number.isFinite(numericId)) lastEventId = Math.max(lastEventId, numericId);
      const runId = event.payload?.run_id ? String(event.payload.run_id) : null;
      if (!runId || ignoredKinds.has(event.kind)) return true;

      const state = stateFor(runId);
      if (!selectedRunId || ["run_created", "run_started"].includes(event.kind)) {
        selectedRunId = runId;
      }
      if (state.inference?.status === "running"
        && !["agent_progress_started", "agent_progress_interrupted"].includes(event.kind)) {
        state.inference.status = "completed";
      }
      if (event.kind === "agent_progress_started") {
        state.inference = {
          id: String(event.payload?.item_id || `inference-${event.id}`),
          label: "Analyzing context and choosing the next action",
          status: "running",
          startedAt: event.created_at || null,
        };
      } else if (event.kind === "agent_progress_interrupted") {
        if (state.inference) state.inference.status = "interrupted";
      } else if (event.kind === "tool_call_started") startTool(state, event);
      else if (event.kind === "tool_call_completed") completeTool(state, event);
      else if (event.kind === "prompt_preparation_started") {
        setPreparationStage(state, "understanding_request", event);
      } else if (event.kind === "prompt_preparation_progress") {
        setPreparationStage(
          state,
          String(event.payload?.phase || "preparing_request"),
          event,
        );
      } else if (event.kind === "clarification_required") {
        completePreparation(state);
        state.currentOperation = "Waiting for research details";
      } else if (event.kind === "clarification_answered") {
        state.currentOperation = "Applying the confirmed details";
      } else if (event.kind === "prompt_compiled") {
        completePreparation(state);
        state.currentOperation = "Request prepared";
      }
      else if (event.kind === "plan_ready") {
        state.plan = {
          planDigest: String(event.payload?.plan_digest || ""),
          planPath: String(event.payload?.plan_path || ""),
          revision: Number(event.payload?.revision || 0),
          status: "pending",
        };
      } else if (event.kind === "plan_approved") {
        if (state.plan) state.plan.status = "approved";
      } else if (event.kind === "plan_revision_requested") {
        if (state.plan) state.plan.status = "revision_requested";
      } else if (event.kind === "result_ready") {
        state.resultReady = {
          bundleRunId: String(event.payload?.bundle_run_id || ""),
          executionState: String(event.payload?.execution_state || ""),
          validationState: String(event.payload?.validation_state || ""),
          deliverableState: String(event.payload?.deliverable_state || ""),
          reportState: String(event.payload?.report_state || ""),
          overallState: String(event.payload?.overall_state || ""),
          failedCheckCount: Number(event.payload?.failed_check_count || 0),
          unmetDeliverables: Array.isArray(event.payload?.unmet_deliverables)
            ? event.payload.unmet_deliverables.map(String)
            : [],
        };
      }
      else if (event.kind === "approval_requested") {
        const payload = event.payload || {};
        const approvalId = String(payload.approval_id || event.id);
        const entry = {
          id: approvalId,
          summary: payload.summary || "Permission required",
          risk: payload.risk || "HIGH",
          decision: null,
          requestedAt: event.created_at || null,
          resolvedAt: null,
        };
        state.pendingApprovals.set(approvalId, payload);
        state.approvalsById.set(approvalId, entry);
        state.approvalHistory.push(entry);
      } else if (event.kind === "approval_resolved") {
        const payload = event.payload || {};
        const approvalId = String(payload.approval_id || "");
        state.pendingApprovals.delete(approvalId);
        const entry = state.approvalsById.get(approvalId);
        if (entry) {
          entry.decision = payload.decision || "resolved";
          entry.resolvedAt = event.created_at || null;
        }
      } else if (![
        "run_created", "run_started", "run_state_changed", "run_completed", "run_failed",
        "run_blocked", "run_cancelled", "run_paused", "run_recovered_paused",
        "permission_grant_created", "permission_grant_used",
        "agent_progress_started", "agent_progress_interrupted",
        "plan_ready", "plan_approved", "plan_revision_requested", "result_ready",
      ].includes(event.kind)) {
        state.technicalEvents.push(event);
      }
      updateRunState(state, event);
      return true;
    }

    function snapshot(requestedRunId = selectedRunId) {
      const state = requestedRunId ? runs.get(String(requestedRunId)) : null;
      if (!state) {
        return {
          lastEventId,
          runId: requestedRunId || null,
          runState: "idle",
          currentOperation: "Idle",
          steps: [],
          reasoning: [],
          inference: null,
          preparationStages: [],
          plan: null,
          resultReady: null,
          pendingApprovals: [],
          approvalHistory: [],
          technicalEvents: [],
        };
      }
      return JSON.parse(JSON.stringify({
        lastEventId,
        runId: state.runId,
        runState: state.runState,
        currentOperation: state.currentOperation,
        steps: state.steps,
        reasoning: [],
        inference: state.inference,
        preparationStages: state.preparationStages,
        plan: state.plan,
        resultReady: state.resultReady,
        pendingApprovals: Array.from(state.pendingApprovals.values()),
        approvalHistory: state.approvalHistory,
        technicalEvents: state.technicalEvents,
      }));
    }

    function reset() {
      seen.clear();
      runs.clear();
      selectedRunId = null;
      lastEventId = 0;
    }

    return {accept, reset, snapshot};
  }

  globalThis.AgentKronigIDEEvents = {createRunPresentation};
})();
