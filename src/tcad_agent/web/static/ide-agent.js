"use strict";

(() => {
  function durationText(startedAt, completedAt) {
    if (!startedAt || !completedAt) return null;
    const elapsed = new Date(completedAt).getTime() - new Date(startedAt).getTime();
    if (!Number.isFinite(elapsed) || elapsed < 0) return null;
    if (elapsed < 60_000) return `${(elapsed / 1_000).toFixed(1)}s`;
    const minutes = Math.floor(elapsed / 60_000);
    const seconds = Math.round((elapsed % 60_000) / 1_000);
    return `${minutes}m ${seconds}s`;
  }

  function technicalCommand(step) {
    const argumentsValue = step.arguments || {};
    return step.command || argumentsValue.command || argumentsValue.path
      || argumentsValue.operation || null;
  }

  function phaseForStep(step) {
    const labels = {
      plan: "Plan",
      inspect: "Inspect",
      edit: "Edit",
      delegate: "Delegate",
      execute: "Execute",
      validate: "Validate",
      report: "Report",
    };
    if (Object.values(labels).includes(step.phase)) return step.phase;
    return labels[step.phase] || "Unclassified";
  }

  function activityRows(snapshot) {
    return (snapshot?.steps || []).map((step) => ({
      id: step.id,
      label: step.summary || step.toolName || "Agent action",
      status: step.status || "running",
      toolName: step.toolName || "tool",
      owner: step.subagent || "Agent Kronig",
      duration: durationText(step.startedAt, step.completedAt),
      command: technicalCommand(step),
      output: step.output || null,
      isError: Boolean(step.isError),
      path: step.arguments?.path || null,
      taskStatus: step.taskStatus || null,
      phase: phaseForStep(step),
      evidenceKind: step.evidenceKind || null,
      researchScope: step.researchScope || null,
      affectedPaths: step.affectedPaths || [],
      artifactPaths: step.artifactPaths || [],
      provenance: step.provenance || null,
    }));
  }

  function chatTimeline(snapshot) {
    const state = snapshot?.runState || "idle";
    if (state === "idle") return [];
    const steps = snapshot?.steps || [];
    const updates = [{
      id: "run-start",
      phase: "Plan",
      label: "Understanding the request and preparing an approach",
      detail: null,
      status: !steps.length && ["queued", "running"].includes(state)
        ? "running"
        : "completed",
    }];
    const labels = {
      plan: "Updating the plan",
      inspect: "Inspecting repository evidence",
      edit: "Updating workspace files",
      delegate: "Delegating a focused task",
      execute: "Running a workspace operation",
      validate: "Running validation",
      report: "Preparing the result",
    };
    steps.forEach((step) => {
      const phase = phaseForStep(step);
      const command = technicalCommand(step);
      const tasks = Array.isArray(step.arguments?.tasks) ? step.arguments.tasks : [];
      let label = labels[step.phase] || "Working on the repository";
      let detail = command || step.summary || null;
      if (step.toolName === "think") {
        label = "Reviewing evidence and choosing the next action";
        detail = null;
      } else if (step.toolName === "task_tracker" && tasks.length) {
        label = "Plan updated";
        detail = tasks.map((task) => task.title).filter(Boolean).join(" · ") || null;
      } else if (step.evidenceKind === "research") {
        if (step.researchScope === "web") {
          label = step.arguments?.operation === "fetch_source"
            ? "Reading a scientific source"
            : "Searching scientific sources";
        } else {
          label = "Searching local TCAD references";
        }
        detail = null;
      } else if (step.arguments?.operation === "prepare_experiment") {
        label = step.status === "completed"
          ? "Experiment project and plan created"
          : "Creating experiment project and approval plan";
        detail = step.status === "completed" && step.artifactPaths?.length
          ? step.artifactPaths.join(" · ")
          : null;
      } else if (["execute_experiment", "execute_approved_plan"].includes(step.arguments?.operation)) {
        label = step.status === "completed"
          ? "Simulation and scientific results completed"
          : "Running simulation and building scientific results";
        detail = step.status === "completed" && step.artifactPaths?.length
          ? step.artifactPaths.join(" · ")
          : null;
      }
      updates.push({
        id: step.id,
        phase,
        label,
        detail,
        status: step.status || "running",
      });
    });
    if (snapshot?.inference) {
      updates.push({
        id: snapshot.inference.id || "agent-inference",
        phase: "Plan",
        label: snapshot.inference.label || "Analyzing context and choosing the next action",
        detail: null,
        status: snapshot.inference.status || "running",
      });
    }
    const pendingApproval = (snapshot?.pendingApprovals || []).at(-1);
    if (pendingApproval || state === "waiting_for_approval") {
      updates.push({
        id: "approval-wait",
        phase: "Approval",
        label: "Waiting for your approval",
        detail: pendingApproval?.summary || null,
        status: "waiting",
      });
    } else if (state === "paused") {
      updates.push({
        id: "run-paused",
        phase: "Paused",
        label: "Run paused",
        detail: null,
        status: "waiting",
      });
    } else if (state === "running"
      && snapshot?.inference?.status !== "running"
      && !steps.some((step) => step.status === "running")) {
      updates.push({
        id: "between-actions",
        phase: "Plan",
        label: "Reviewing results and choosing the next action",
        detail: null,
        status: "running",
      });
    }
    return updates;
  }

  function operationalUpdates(snapshot) {
    return chatTimeline(snapshot).slice(-6);
  }

  function liveDuration(startedAt, nowMs) {
    if (!startedAt) return null;
    const elapsed = Math.floor((nowMs - new Date(startedAt).getTime()) / 1_000);
    if (!Number.isFinite(elapsed) || elapsed < 8) return null;
    if (elapsed < 60) return `Still working · ${elapsed}s`;
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    return `Still working · ${minutes}m ${seconds}s`;
  }

  function researchTrail(snapshot, nowMs = Date.now()) {
    const state = snapshot?.runState || "idle";
    const activelyWorking = ["queued", "running"].includes(state);
    if (state === "idle") return {
      visible: false, stages: [], recent: [], current: null, recovery: null,
    };
    const steps = snapshot?.steps || [];
    const phaseLabels = {
      Plan: ["Approach", "Preparing the research approach", "Research approach prepared"],
      Inspect: ["Repository", "Reviewing repository evidence", "Repository evidence reviewed"],
      Edit: ["Workspace", "Updating workspace files", "Workspace files updated"],
      Delegate: ["Coordination", "Coordinating a focused task", "Focused tasks coordinated"],
      Execute: ["Execution", "Running a workspace operation", "Workspace operations completed"],
      Validate: ["Validation", "Running validation", "Validation completed"],
      Report: ["Results", "Preparing the research result", "Research result prepared"],
      Unclassified: ["Research", "Working through the research task", "Research action completed"],
    };
    const groups = [];
    const byPhase = new Map();
    steps.forEach((step) => {
      const key = phaseForStep(step);
      if (!byPhase.has(key)) {
        const group = {key, steps: []};
        byPhase.set(key, group);
        groups.push(group);
      }
      byPhase.get(key).steps.push(step);
    });
    const failedIndexes = steps
      .map((step, index) => step.status === "failed" ? index : -1)
      .filter((index) => index >= 0);
    const recoveredFailures = failedIndexes.filter((failedIndex) => (
      steps.slice(failedIndex + 1).some((step) => step.status === "completed"
        && step.toolName === steps[failedIndex].toolName
        && step.arguments?.operation === steps[failedIndex].arguments?.operation)
      && state !== "failed"
    ));
    let stages = groups.slice(-4).map((group) => {
      const [phase, activeLabel, completedLabel] = phaseLabels[group.key] || phaseLabels.Unclassified;
      const unfinished = group.steps.some((step) => step.status === "running");
      const running = activelyWorking && unfinished;
      const stopped = !activelyWorking && unfinished;
      const terminalFailure = state === "failed" && group.steps.at(-1)?.status === "failed";
      return {
        id: `research-${group.key.toLowerCase()}`,
        phase,
        label: stopped ? `${phase} paused or stopped` : running ? activeLabel : completedLabel,
        detail: `${group.steps.length} ${group.steps.length === 1 ? "action" : "actions"} recorded`,
        actionCount: group.steps.length,
        status: running ? "running" : terminalFailure ? "failed" : stopped ? "stopped" : "completed",
      };
    });
    const preparationStages = Array.isArray(snapshot?.preparationStages)
      ? snapshot.preparationStages
      : [];
    if (!steps.length && preparationStages.length) {
      stages = [];
    }
    let current = activelyWorking
      ? stages.find((stage) => stage.status === "running") || null
      : null;
    const runningStep = [...steps].reverse().find((step) => step.status === "running");
    if (activelyWorking && runningStep) {
      const update = [...chatTimeline({...snapshot, inference: null})]
        .reverse()
        .find((entry) => entry.id === runningStep.id);
      current = {
        label: update?.label || runningStep.summary || "Working on the research task",
        detail: liveDuration(runningStep.startedAt, nowMs),
        status: "running",
        animated: true,
      };
    }
    const pendingApproval = (snapshot?.pendingApprovals || []).at(-1);
    if (pendingApproval || state === "waiting_for_approval") {
      current = {label: "Waiting for researcher approval", status: "waiting", animated: false};
    } else if (state === "waiting_for_plan_approval") {
      current = {label: "Review the prepared experiment", status: "waiting", animated: false};
    } else if (state === "waiting_for_user") {
      current = {
        label: snapshot?.currentOperation || "Waiting for your response",
        status: "waiting",
        animated: false,
      };
    } else if (["queued", "running"].includes(state) && !steps.length) {
      const activePreparation = preparationStages.find((stage) => stage.status === "running");
      current = {
        label: activePreparation?.label
          || (snapshot?.currentOperation && snapshot.currentOperation !== "Idle"
            ? snapshot.currentOperation
            : "Preparing the research approach"),
        detail: activePreparation ? liveDuration(activePreparation.startedAt, nowMs) : null,
        status: "running",
        animated: true,
      };
    } else if (state === "running" && !current) {
      current = {
        label: "Reviewing results and choosing the next action",
        status: "running",
        animated: true,
      };
    }
    if (current && current.animated === undefined) {
      current.animated = activelyWorking && current.status === "running";
    }
    if (current && !activelyWorking) current.animated = false;
    if (state === "failed" && snapshot?.terminalDetail) {
      current = {label: failurePresentation(snapshot).summary, status: "failed", animated: false};
    }
    const resultsNeedReview = state === "blocked"
      && snapshot?.resultReady?.overallState === "needs_attention";
    if (resultsNeedReview) {
      current = {label: snapshot.terminalDetail || "Review scientific checks in Results",
        status: "completed", animated: false};
    }
    const titles = {
      queued: "Preparing request",
      completed: "Research record",
      failed: "Research failed",
      blocked: "Research blocked",
      cancelled: "Research cancelled",
      waiting_for_approval: "Research awaiting approval",
      waiting_for_plan_approval: "Plan ready",
      waiting_for_user: "Input needed",
      paused: "Research paused",
    };
    const meta = steps.length
      ? `${steps.length} ${steps.length === 1 ? "action" : "actions"}`
      : state === "waiting_for_user"
        ? "Input needed"
        : state === "waiting_for_plan_approval"
          ? "Review needed"
        : ["queued", "running"].includes(state)
          ? "Live"
          : "No tool actions";
    const recent = (preparationStages.length && !steps.length ? [] : chatTimeline(snapshot).slice(-4)).map((update) => ({
      id: update.id,
      phase: update.phase,
      label: update.label,
      detail: steps.find((step) => step.id === update.id)?.toolName === "terminal"
        ? null : update.detail,
      status: update.status,
    }));
    return {
      visible: true,
      title: resultsNeedReview ? "Results need review" : titles[state] || "Research in progress",
      meta,
      stages,
      recent,
      current,
      recovery: recoveredFailures.length
        ? "Intermediate corrections were resolved automatically. No researcher action was required."
        : null,
      state,
      diagnostics: state === "failed" ? failurePresentation(snapshot).diagnostics : "",
    };
  }

  function unique(values) {
    return Array.from(new Set(values.filter(Boolean)));
  }

  function affectedFilePaths(row, workspaceRoot) {
    const evidencePaths = Array.isArray(row?.affectedPaths) && row.affectedPaths.length
      ? row.affectedPaths
      : [row?.path];
    const root = String(workspaceRoot || "").replaceAll("\\", "/").replace(/\/$/, "");
    return unique(evidencePaths.map((value) => {
      const path = String(value || "").replaceAll("\\", "/");
      return root && path.startsWith(`${root}/`) ? path.slice(root.length + 1) : path;
    }));
  }

  function outcomeSummary(snapshot, changeSet) {
    const steps = activityRows(snapshot);
    const failed = steps.find((step) => step.status === "failed");
    const successful = steps.filter((step) => step.status === "completed");
    const state = snapshot?.runState || "idle";
    const terminal = ["completed", "failed", "blocked", "cancelled"].includes(state);
    const scientificOutcome = snapshot?.resultReady || null;
    const titles = {
      completed: "Run completed",
      failed: "Run failed",
      blocked: "Run blocked",
      cancelled: "Run cancelled",
    };
    const tones = {
      completed: "success",
      failed: "danger",
      blocked: "warning",
      cancelled: "muted",
    };
    const changedPaths = (changeSet?.files || []).map((change) => change.path);
    const validationActionIds = new Set(
      (changeSet?.files || []).flatMap((change) => change.validation_action_ids || []),
    );
    const validationChecks = successful.filter((step) => step.evidenceKind === "validation");
    const validationEvidence = validationChecks
      .filter((step) => validationActionIds.has(step.id))
      .map((step) => ({label: step.label, output: step.output || null}));
    const unlinkedValidationChecks = validationChecks
      .filter((step) => !validationActionIds.has(step.id))
      .map((step) => ({label: step.label, output: step.output || null}));
    const warnings = [];
    if (changeSet?.baseline_truncated) {
      warnings.push(changeSet.manifest_warning || "The workspace scan reached its safety limit. Create, delete, and rename attribution may be incomplete.");
    }
    if (failed) warnings.push(`Failed action: ${failed.label}`);
    if (snapshot?.terminalDetail) warnings.push(state === "failed" ? failurePresentation(snapshot).summary : sanitizeDiagnostic(snapshot.terminalDetail));
    (snapshot?.technicalEvents || [])
      .filter((event) => ["agent_error", "change_baseline_warning"].includes(event.kind))
      .forEach((event) => warnings.push(event.kind === "agent_error" ? failurePresentation(snapshot).summary : sanitizeDiagnostic(event.payload?.detail || event.kind)));
    const nextActions = [];
    if (scientificOutcome?.overallState === "needs_attention") {
      nextActions.push("Review failed checks and unmet requested outputs in Results.");
    } else if (state === "completed") nextActions.push("Review changed files and validation evidence.");
    else if (failed) nextActions.push("Inspect the failed action output before retrying.");
    else if (state === "blocked") nextActions.push("Resolve the reported blocker before continuing.");
    return {
      visible: terminal,
      state,
      tone: scientificOutcome?.overallState === "completed"
        ? "success"
        : scientificOutcome?.overallState === "needs_attention"
          ? "warning"
          : scientificOutcome?.overallState === "failed"
            ? "danger"
            : tones[state] || "neutral",
      title: scientificOutcome?.overallState === "completed"
        ? "Simulation completed"
        : scientificOutcome?.overallState === "needs_attention"
          ? "Results ready, checks need attention"
          : scientificOutcome?.overallState === "failed"
            ? "Simulation failed"
            : titles[state] || snapshot?.currentOperation || "Run activity",
      changedFiles: changedPaths.length,
      changedPaths,
      completedSteps: successful.length,
      failedStep: failed?.label || null,
      failureOutput: failed?.output ? sanitizeDiagnostic(failed.output) : null,
      lastSuccessfulStep: successful.at(-1)?.label || null,
      phases: unique(steps.map((step) => step.phase)),
      commands: unique(steps.map((step) => step.command)),
      validationEvidence,
      unlinkedValidationChecks,
      artifacts: (changeSet?.files || []).filter((change) => change.artifact).map((change) => change.path),
      provenance: unique(successful.map((step) => step.provenance).filter((item) => typeof item === "string")),
      warnings,
      failureSummary: failurePresentation(snapshot).summary,
      diagnostics: failurePresentation(snapshot).diagnostics,
      nextActions,
      executionState: scientificOutcome?.executionState || null,
      validationState: scientificOutcome?.validationState || null,
      deliverableState: scientificOutcome?.deliverableState || null,
      reportState: scientificOutcome?.reportState || null,
      failedCheckCount: scientificOutcome?.failedCheckCount || 0,
      unmetDeliverables: scientificOutcome?.unmetDeliverables || [],
    };
  }

  function sanitizeArguments(value, key = "") {
    if (/(token|secret|password|credential|api[_-]?key|authorization)/i.test(key)) {
      return "[redacted]";
    }
    if (Array.isArray(value)) return value.map((item) => sanitizeArguments(item));
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value).map(([childKey, child]) => [
          childKey,
          sanitizeArguments(child, childKey),
        ]),
      );
    }
    return value;
  }

  function sanitizeDiagnostic(value) {
    return String(value || "")
      .replace(/(["'][^"']*(?:api[_-]?key|token|secret|password|credential|authorization|signature)[^"']*["']\s*:\s*)["'][^"']*["']/gi, '$1"[redacted]"')
      .replace(/(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+/gi, "$1[redacted]")
      .replace(/((?:[\w-]*(?:api[_-]?key|token|secret|password|credential|signature)[\w-]*|AWS_ACCESS_KEY_ID)\s*[=:]\s*)[^\s,;&]+/gi, "$1[redacted]")
      .replace(/((?:https?:\/\/)[^\s/@:]+:)[^\s/@]+@/gi, "$1[redacted]@")
      .replace(/(?:[A-Za-z]:[\\/]|\/)[^\s]*[\\/](?:\.claude|\.codex|sessions)[\\/][^\s]*/gi, "[internal session path]");
  }

  function failurePresentation(snapshot) {
    const failedStep = (snapshot?.steps || []).find((step) => step.status === "failed" && step.toolName !== "think");
    const diagnostics = unique([
      snapshot?.terminalDetail,
      failedStep?.output,
      ...(snapshot?.technicalEvents || []).filter((event) => event.kind === "agent_error")
        .map((event) => event.payload?.detail),
    ]).map(sanitizeDiagnostic).join("\n\n");
    const technical = /Exception|Traceback|SDK|tool_use|\/sessions\/|\.claude|\.codex/i.test(diagnostics);
    return {
      summary: technical ? "The research service could not finish this request. Review the diagnostic before retrying."
        : sanitizeDiagnostic(snapshot?.terminalDetail) || "The research task could not finish. Review the failed action before retrying.",
      diagnostics,
    };
  }

  function inputLedger(records) {
    const authorities = [
      ["researcher_owned", "Researcher-reviewed inputs"],
      ["deterministically_derived", "Derived contract values"],
      ["evidence_backed_expert_suggestion", "Reviewed expert settings"],
      ["platform_reviewed_default", "Platform-controlled settings"],
      ["simulator_implementation_detail", "Simulator implementation"],
      ["unsupported_or_unknown", "Unresolved authority"],
    ];
    const values = Array.isArray(records) ? records : [];
    const known = new Set(authorities.map(([authority]) => authority));
    return authorities.map(([authority, label]) => ({
      authority, label,
      records: values.filter((record) => (known.has(record.authority) ? record.authority : "unsupported_or_unknown") === authority)
        .map((record) => ({
          path: String(record.path || ""), quantity: String(record.quantity || record.path || "Input"),
          value: record.value === undefined || record.value === null ? "Unavailable" : JSON.stringify(record.value),
          status: String(record.status || "unknown"), source: String(record.source?.id || "Source unavailable"),
          digest: record.source?.digest || null, derivation: record.derivation || null,
          rationale: String(record.rationale || ""),
        })),
    })).filter((group) => group.records.length);
  }

  function reversibilityFor(permissionCategory, payload) {
    const command = String(payload.command || "").trim().toLowerCase();
    if (["external_file_access", "sensitive_file_access"].includes(permissionCategory)
      && /^(cat|head|tail|grep|rg|find|ls|sed\s+-n)\b/.test(command)) {
      return "Read-only. No workspace data is changed.";
    }
    if (["network_access"].includes(permissionCategory)) {
      return "May send or retrieve external data. The external effect may not be reversible.";
    }
    if (["git_mutation", "destructive_command", "system_change", "package_installation", "remote_execution"].includes(permissionCategory)) {
      return "May change local or external state. Reversal is not guaranteed.";
    }
    if (payload.path) return "May change a file. Version control may allow reversal.";
    return "Reversibility is not guaranteed. Review the exact arguments before approval.";
  }

  function permissionView(approval) {
    const payload = approval?.payload || {};
    const permissionCategory = approval?.permission_category
      || approval?.permissionCategory
      || "unrecognized_action";
    const sanitized = sanitizeArguments(payload);
    return {
      explanation: approval?.summary || approval?.explanation || "Review the requested action.",
      target: sanitized.path || sanitized.command || sanitized.operation || approval?.target
        || "Review the technical details.",
      toolName: approval?.tool_name || approval?.toolName || "tool",
      permissionCategory,
      risk: approval?.risk || "HIGH",
      canApproveCategory: !["complex_shell", "unrecognized_action"].includes(
        permissionCategory,
      ),
      technicalArguments: JSON.stringify(sanitized, null, 2),
      reversibility: reversibilityFor(permissionCategory, sanitized),
    };
  }

  function approvalDeck(approvals, selectedId) {
    const queue = Array.isArray(approvals) ? approvals : [];
    if (!queue.length) {
      return {
        active: null,
        index: 0,
        position: 0,
        total: 0,
        canPrevious: false,
        canNext: false,
      };
    }
    const selectedIndex = queue.findIndex(
      (approval) => String(approval?.id || "") === String(selectedId || ""),
    );
    const index = selectedIndex >= 0 ? selectedIndex : 0;
    return {
      active: queue[index],
      index,
      position: index + 1,
      total: queue.length,
      canPrevious: index > 0,
      canNext: index < queue.length - 1,
    };
  }

  function moveApproval(index, total, direction) {
    const maximum = Math.max(0, Number(total || 0) - 1);
    return Math.min(maximum, Math.max(0, Number(index || 0) + Number(direction || 0)));
  }

  function approvalKeyAction({
    key,
    shiftKey = false,
    atContainer = false,
    atFirst = false,
    atLast = false,
  }) {
    if (key === "Escape") return "minimize";
    if (key !== "Tab") return "none";
    if (atContainer) return shiftKey ? "focus-last" : "focus-first";
    if (shiftKey && atFirst) return "focus-last";
    if (!shiftKey && atLast) return "focus-first";
    return "none";
  }

  function planReview(record) {
    const prepared = record?.prepared || {};
    const spec = prepared.spec || {};
    const rawPath = String(record?.plan_path || "").replaceAll("\\", "/");
    const experimentIndex = rawPath.lastIndexOf("/experiments/");
    const planPath = experimentIndex >= 0
      ? rawPath.slice(experimentIndex + 1)
      : rawPath.split("/").filter(Boolean).at(-1) || "PLAN.md";
    const studyKind = String(spec.study?.kind || "study");
    const studyLabels = {dc_points: "DC points", dc_sweep: "DC sweep", ac: "AC"};
    const study = studyLabels[studyKind] || studyKind
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase())
      .replace(/^Dc\b/, "DC")
      .replace(/^Ac\b/, "AC");
    const completeness = prepared.completeness?.records || [];
    return {
      visible: record?.status === "pending",
      title: String(spec.name || "Prepared experiment"),
      backend: String(prepared.backend || "simulator"),
      study,
      regionCount: Array.isArray(spec.regions) ? spec.regions.length : 0,
      contactCount: Array.isArray(spec.contacts) ? spec.contacts.length : 0,
      observableCount: Array.isArray(spec.observables) ? spec.observables.length : 0,
      unresolvedCount: completeness.filter((item) => item.status !== "resolved").length,
      warningCount: Array.isArray(prepared.warnings) ? prepared.warnings.length : 0,
      planPath,
      planDigest: String(record?.plan_digest || ""),
      revision: Number(record?.revision || 0),
      inputLedger: inputLedger(completeness),
    };
  }

  function experimentProjectView(experiment) {
    let statusLabel = "Result available";
    let statusTone = "neutral";
    if (experiment?.execution_state === "failed") {
      statusLabel = "Simulation failed";
      statusTone = "failed";
    } else if (experiment?.validation_state === "passed") {
      statusLabel = "Validated";
      statusTone = "success";
    } else if (experiment?.validation_state === "needs_review") {
      const count = experiment.failed_check_count;
      statusLabel = Number.isInteger(count) && count > 0
        ? `${count} validation ${count === 1 ? "check" : "checks"} failed`
        : experiment.unmet_deliverables?.length
          ? `${experiment.unmet_deliverables.length} requested outputs incomplete`
          : "Review needed";
      statusTone = "warning";
    } else if (experiment?.validation_state === "failed") {
      statusLabel = "Checks failed";
      statusTone = "failed";
    }
    const labels = {
      plan: "Plan",
      report: "Report",
      validation: "Validation",
    };
    const secondaryActions = Object.entries(labels)
      .filter(([key]) => Boolean(experiment?.artifacts?.[key]))
      .map(([key, label]) => ({key, label, path: experiment.artifacts[key]}));
    return {
      name: String(experiment?.name || "Experiment result"),
      path: String(experiment?.project_path || ""),
      statusLabel,
      statusTone,
      primaryAction: "Open results",
      secondaryActions,
    };
  }

  globalThis.AgentKronigAgentView = {
    affectedFilePaths,
    activityRows,
    approvalDeck,
    approvalKeyAction,
    chatTimeline,
    durationText,
    failurePresentation,
    inputLedger,
    sanitizeDiagnostic,
    experimentProjectView,
    moveApproval,
    outcomeSummary,
    operationalUpdates,
    permissionView,
    planReview,
    phaseForStep,
    researchTrail,
    sanitizeArguments,
  };
})();
