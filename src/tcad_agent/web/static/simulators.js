"use strict";

(() => {
  const STORAGE_KEY = "agentKronigSimulator";
  const SETTING_LABELS = {
    TCAD_SENTAURUS_RUNNER: "SSH connection",
    TCAD_HPSC_HOST: "HPC address",
    TCAD_HPSC_USER: "login name",
    TCAD_SENTAURUS_VERSION: "Sentaurus release",
  };

  function parseExtra(text) {
    const result = {};
    String(text || "").split(/\r?\n/).forEach((raw, index) => {
      const line = raw.trim();
      if (!line || line.startsWith("#")) return;
      const split = line.indexOf("=");
      if (split < 1) throw new Error(`Line ${index + 1}: write it as NAME=value.`);
      result[line.slice(0, split).trim()] = line.slice(split + 1).trim();
    });
    return result;
  }

  function formatExtra(map) {
    return Object.entries(map || {}).map(([name, value]) => `${name}=${value}`).join("\n");
  }

  function missingText(backend) {
    const names = (backend?.missing_settings || []).map((name) => SETTING_LABELS[name] || name);
    return names.length ? `Needs ${names.join(", ")}.` : "";
  }

  // What the switch shows: the chosen simulator, whether each is ready, and a one-line note.
  function describe(state, chosen) {
    const backends = Array.isArray(state?.backends) ? state.backends : [];
    const known = backends.map((backend) => backend.id);
    const selected = known.includes(chosen) ? chosen : (known.includes(state?.default) ? state.default : "devsim");
    const options = backends.map((backend) => ({
      id: backend.id,
      label: backend.label,
      ready: backend.ready === true,
      selected: backend.id === selected,
      note: backend.ready === true ? "" : missingText(backend),
    }));
    const current = options.find((option) => option.selected);
    let note = "";
    if (current && !current.ready) note = `${current.label} is not set up. ${current.note}`.trim();
    return {selected, options, note, welcome: current ? `${current.label}${current.ready ? " ready" : " needs setup"}` : ""};
  }

  function checkRows(result) {
    const checks = Array.isArray(result?.checks) ? result.checks : [];
    const hostKey = checks.find((check) => check.name === "host key" && !check.ok);
    return {
      ok: result?.ok === true,
      rows: checks.map((check) => ({
        name: String(check.name),
        ok: check.ok === true,
        detail: String(check.detail || ""),
        fix: check.ok ? "" : String(check.fix || ""),
      })),
      fingerprint: hostKey ? (hostKey.detail.match(/SHA256:[A-Za-z0-9+/=]+/) || [null])[0] : null,
    };
  }

  function readChoice(storage) {
    try {
      const value = storage?.getItem(STORAGE_KEY);
      return value === "devsim" || value === "sentaurus" ? value : null;
    } catch {
      return null;
    }
  }

  function writeChoice(storage, value) {
    try {
      storage?.setItem(STORAGE_KEY, value);
    } catch {
      // The choice still applies for this session without browser storage.
    }
  }

  async function request(fetchImpl, path, options) {
    const response = await fetchImpl(path, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || payload.detail || "The request failed.");
    return payload;
  }

  // Connects the composer switch and the settings test panel to the page.
  function install({document, fetch, storage, onSetupRequested}) {
    const buttons = [...document.querySelectorAll("#simulator-switch [data-simulator]")];
    const note = document.querySelector("#simulator-switch-note");
    const welcome = document.querySelector("#simulator-welcome-state");
    const settingsState = document.querySelector("#simulator-settings-state");
    const testButton = document.querySelector("#simulator-test");
    const deepButton = document.querySelector("#simulator-test-deep");
    const trustButton = document.querySelector("#simulator-trust");
    const results = document.querySelector("#simulator-test-results");
    let state = null;
    let fingerprint = null;

    function render() {
      if (!state) return;
      const view = describe(state, state.selected || state.default);
      buttons.forEach((button) => {
        const option = view.options.find((item) => item.id === button.dataset.simulator);
        button.setAttribute("aria-checked", String(option?.selected === true));
        button.classList.toggle("needs-setup", option ? !option.ready : false);
        button.title = option?.ready === false ? option.note || "Not set up" : button.title;
      });
      if (note) note.textContent = view.note;
      if (welcome && view.welcome) welcome.textContent = view.welcome;
      if (settingsState) {
        const sentaurus = view.options.find((item) => item.id === "sentaurus");
        settingsState.textContent = sentaurus?.ready
          ? "Sentaurus connection is configured."
          : `Sentaurus is not set up yet. ${sentaurus?.note || ""}`.trim();
      }
    }

    async function refresh() {
      state = await request(fetch, "/api/simulators");
      render();
    }

    async function choose(id) {
      state = await request(fetch, "/api/simulators/default", {
        method: "PUT",
        headers: {"content-type": "application/json"},
        body: JSON.stringify({backend: id}),
      });
      state = {...state, selected: id};
      writeChoice(storage, id);
      render();
    }

    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const id = button.dataset.simulator;
        const option = describe(state, id).options.find((item) => item.id === id);
        if (option && !option.ready) {
          // Show what is missing and take the researcher to the place that fixes it.
          if (note) note.textContent = `${option.label} is not set up. ${option.note}`.trim();
          if (onSetupRequested) onSetupRequested();
          return;
        }
        void choose(id).catch((error) => { if (note) note.textContent = error.message; });
      });
    });

    function showChecks(outcome) {
      const view = checkRows(outcome);
      fingerprint = view.fingerprint;
      if (trustButton) trustButton.hidden = !fingerprint;
      if (!results) return;
      results.replaceChildren(...view.rows.map((row) => {
        const item = document.createElement("li");
        item.className = row.ok ? "check-ok" : "check-failed";
        const mark = document.createElement("b");
        mark.textContent = row.ok ? "✓" : "✗";
        const name = document.createElement("strong");
        name.textContent = row.name;
        const detail = document.createElement("span");
        detail.textContent = row.detail;
        item.append(mark, name, detail);
        if (row.fix) {
          const fix = document.createElement("em");
          fix.textContent = `Fix: ${row.fix}`;
          item.append(fix);
        }
        return item;
      }));
    }

    async function runCheck({deep = false, trust = false} = {}) {
      [testButton, deepButton, trustButton].forEach((button) => { if (button) button.disabled = true; });
      if (results) results.replaceChildren(Object.assign(document.createElement("li"), {textContent: "Checking…"}));
      try {
        showChecks(await request(fetch, "/api/simulators/sentaurus/check", {
          method: "POST",
          headers: {"content-type": "application/json"},
          body: JSON.stringify({deep, trust_host: trust}),
        }));
        await refresh();
      } catch (error) {
        showChecks({ok: false, checks: [{name: "check", ok: false, detail: error.message}]});
      } finally {
        [testButton, deepButton, trustButton].forEach((button) => { if (button) button.disabled = false; });
      }
    }

    testButton?.addEventListener("click", () => void runCheck());
    deepButton?.addEventListener("click", () => void runCheck({deep: true}));
    trustButton?.addEventListener("click", () => {
      const ask = typeof window !== "undefined" ? window.confirm : () => true;
      const text = `Trust this server key?\n${fingerprint || ""}\nConfirm the fingerprint with the HPC administrator first.`;
      if (ask(text)) void runCheck({trust: true});
    });

    // The remembered choice is pushed to the service so the first request already uses it.
    async function start() {
      await refresh();
      const remembered = readChoice(storage);
      if (remembered && remembered !== state.selected) {
        const option = describe(state, remembered).options.find((item) => item.id === remembered);
        if (option?.ready) await choose(remembered);
      }
    }

    return {refresh, choose, start};
  }

  globalThis.AgentKronigSimulators = Object.freeze({
    checkRows,
    describe,
    formatExtra,
    install,
    parseExtra,
    readChoice,
  });
})();
