(() => {
  const assert = (condition, message) => {
    if (!condition) throw new Error(message);
  };
  const S = AgentKronigSimulators;
  const state = {
    default: "devsim",
    selected: null,
    backends: [
      {id: "devsim", label: "DEVSIM (local)", ready: true, missing_settings: []},
      {
        id: "sentaurus",
        label: "Sentaurus (remote HPC)",
        ready: false,
        missing_settings: ["TCAD_SENTAURUS_RUNNER", "TCAD_HPSC_HOST"],
      },
    ],
  };

  const idle = S.describe(state, null);
  assert(idle.selected === "devsim", "the service default is shown when nothing was chosen");
  assert(idle.note === "", "a ready simulator needs no note");
  assert(idle.welcome === "DEVSIM (local) ready", "the welcome line names the simulator");

  const unready = S.describe(state, "sentaurus");
  assert(unready.selected === "sentaurus", "a chosen simulator is shown as selected");
  assert(unready.note.includes("SSH connection") && unready.note.includes("HPC address"),
    "the note says which settings are missing in researcher terms");
  assert(unready.welcome.endsWith("needs setup"), "an unready simulator is not reported as ready");
  assert(S.describe(state, "nonsense").selected === "devsim", "an unknown choice falls back safely");

  const extra = S.parseExtra("# comment\nTCAD_BACKEND=sentaurus\n\nTCAD_X = a=b ");
  assert(extra.TCAD_BACKEND === "sentaurus" && extra.TCAD_X === "a=b", "NAME=value lines are parsed");
  assert(S.formatExtra(extra).split("\n").length === 2, "variables round trip to lines");
  let rejected = false;
  try { S.parseExtra("no equals sign"); } catch (error) { rejected = /Line 1/.test(error.message); }
  assert(rejected, "a line without = is refused with its line number");

  const failed = S.checkRows({
    ok: false,
    checks: [
      {name: "settings", ok: true, detail: "present", fix: ""},
      {
        name: "host key",
        ok: false,
        detail: "h is not in known_hosts (server fingerprint SHA256:abc+/=)",
        fix: "confirm it",
      },
    ],
  });
  assert(failed.ok === false && failed.rows.length === 2, "every check is listed");
  assert(failed.fingerprint === "SHA256:abc+/=", "the fingerprint is offered for explicit trust");
  assert(failed.rows[0].fix === "", "a passing check has no fix text");
  assert(S.checkRows({ok: true, checks: []}).fingerprint === null, "no fingerprint unless the host key failed");

  const memory = {};
  const storage = {getItem: (key) => memory[key] ?? null, setItem: (key, value) => { memory[key] = value; }};
  storage.setItem("agentKronigSimulator", "sentaurus");
  assert(S.readChoice(storage) === "sentaurus", "a remembered choice is read back");
  storage.setItem("agentKronigSimulator", "<script>");
  assert(S.readChoice(storage) === null, "a corrupted remembered choice is ignored");
  assert(S.readChoice({getItem: () => { throw new Error("blocked"); }}) === null, "blocked storage is tolerated");
})();
