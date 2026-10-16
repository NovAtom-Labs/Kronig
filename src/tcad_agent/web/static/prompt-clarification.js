"use strict";

(() => {
  function view(preparation) {
    const decision = preparation?.decision;
    const questions = Array.isArray(decision?.questions) ? decision.questions : [];
    return {
      visible: decision?.status === "clarification" && questions.length > 0,
      revision: Number(preparation?.revision || 0),
      summary: String(decision?.summary || "A few details are needed before execution."),
      questions: questions.map((question) => ({
        id: String(question.id),
        fieldPath: String(question.field_path || question.id),
        reasonKind: String(question.reason_kind || "unspecified"),
        evidenceQuotes: question.evidence_quotes || [],
        prompt: String(question.prompt),
        reason: String(question.reason),
        required: question.required !== false,
      })),
    };
  }

  function submission(preparation, values) {
    const model = view(preparation);
    if (!model.visible) throw new Error("No clarification is active.");
    const answers = [];
    model.questions.forEach((question) => {
      const answer = String(values?.[question.id] || "").trim();
      if (!answer && question.required) {
        throw new Error(`Answer required: ${question.prompt}`);
      }
      if (answer) answers.push({question_id: question.id, answer});
    });
    if (!answers.length) throw new Error("Enter at least one answer.");
    return {expected_revision: model.revision, answers};
  }

  function firstIncomplete(preparation, values) {
    const model = view(preparation);
    return model.questions.findIndex((question) => (
      question.required && !String(values?.[question.id] || "").trim()
    ));
  }

  function interaction(preparation) {
    const clarificationActive = view(preparation).visible;
    return {
      clarificationActive,
      showComposer: !clarificationActive,
    };
  }

  function step(preparation, requestedIndex, values) {
    const model = view(preparation);
    if (!model.visible) throw new Error("No clarification is active.");
    const index = Math.min(
      Math.max(Number.isFinite(Number(requestedIndex)) ? Number(requestedIndex) : 0, 0),
      model.questions.length - 1,
    );
    const question = model.questions[index];
    return {
      answered: Boolean(String(values?.[question.id] || "").trim()),
      index,
      isFirst: index === 0,
      isLast: index === model.questions.length - 1,
      position: index + 1,
      question,
      total: model.questions.length,
    };
  }

  function restoredIndex(preparation, questionId, fallbackIndex = 0) {
    const model = view(preparation);
    if (!model.visible) return 0;
    const matchingIndex = model.questions.findIndex((question) => question.id === questionId);
    if (matchingIndex >= 0) return matchingIndex;
    return Math.min(Math.max(Number(fallbackIndex) || 0, 0), model.questions.length - 1);
  }

  function signature(preparation) {
    const model = view(preparation);
    if (!model.visible) return "";
    return JSON.stringify({
      revision: model.revision,
      summary: model.summary,
      questions: model.questions,
    });
  }

  globalThis.AgentKronigClarification = {
    firstIncomplete,
    interaction,
    restoredIndex,
    signature,
    step,
    submission,
    view,
  };
})();
