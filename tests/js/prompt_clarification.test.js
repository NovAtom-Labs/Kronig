(() => {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const preparation = {
    revision: 3,
    decision: {
      status: "clarification",
      summary: "Two researcher choices are needed.",
      questions: [
        {id: "temperature", prompt: "What temperature?", reason: "Controls statistics.", required: true},
        {id: "label", prompt: "Optional label?", reason: "Controls display only.", required: false},
      ],
    },
  };

  const view = AgentKronigClarification.view(preparation);
  assert(view.visible === true, "clarification should be visible");
  assert(view.questions.length === 2, "all questions should be retained");
  assert(view.questions[0].reason === "Controls statistics.", "rationale should be visible");

  const firstSignature = AgentKronigClarification.signature(preparation);
  const refreshedPreparation = JSON.parse(JSON.stringify(preparation));
  assert(
    AgentKronigClarification.signature(refreshedPreparation) === firstSignature,
    "an unchanged server refresh must not rebuild the clarification form",
  );
  refreshedPreparation.revision = 4;
  assert(
    AgentKronigClarification.signature(refreshedPreparation) !== firstSignature,
    "a new clarification revision must rebuild the form",
  );
  refreshedPreparation.revision = preparation.revision;
  refreshedPreparation.decision.questions[1].prompt = "What label should be used?";
  assert(
    AgentKronigClarification.signature(refreshedPreparation) !== firstSignature,
    "changed clarification content must rebuild the form",
  );

  const payload = AgentKronigClarification.submission(preparation, {
    temperature: "300 K",
    label: "",
  });
  assert(payload.expected_revision === 3, "revision should be preserved");
  assert(payload.answers.length === 1, "blank optional answer should be omitted");
  assert(payload.answers[0].answer === "300 K", "answer should be unchanged");

  let rejected = false;
  try {
    AgentKronigClarification.submission(preparation, {temperature: ""});
  } catch (_error) {
    rejected = true;
  }
  assert(rejected, "blank required answer should be rejected");
})();
