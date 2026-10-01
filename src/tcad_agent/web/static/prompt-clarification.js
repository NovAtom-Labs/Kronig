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

  function signature(preparation) {
    const model = view(preparation);
    if (!model.visible) return "";
    return JSON.stringify({
      revision: model.revision,
      summary: model.summary,
      questions: model.questions,
    });
  }

  globalThis.AgentKronigClarification = {signature, submission, view};
})();
