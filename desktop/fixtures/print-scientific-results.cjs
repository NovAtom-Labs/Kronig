// A hidden test renderer, isolated from the user's running application.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {app, BrowserWindow} = require("electron");
const {exportResultsPdf} = require("../src/results-export");

const destination = process.argv[2];
const staticRoot = path.resolve(__dirname, "../../src/tcad_agent/web/static");
const preload = path.resolve(__dirname, "../src/preload.js");
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "kronig-pdf-test-profile-"));
app.setPath("userData", profile);
app.on("quit", () => {try {fs.rmSync(profile,{recursive:true,force:true});} catch {}});
app.whenReady().then(async () => {
  const window = new BrowserWindow({show:false, width:1280,height:900,
    webPreferences:{preload,contextIsolation:true,nodeIntegration:false,sandbox:true}});
  await window.loadURL("data:text/html," + encodeURIComponent(
    '<!doctype html><html><head><meta charset="UTF-8"></head><body>'
    + '<aside class="agent-panel">PRIVATE CHAT MUST NOT APPEAR IN PDF</aside>'
    + '<div id="results"></div></body></html>'
  ));
  await window.webContents.executeJavaScript(
    "document.head.append(Object.assign(document.createElement('style'), {textContent:"
    + JSON.stringify(fs.readFileSync(path.join(staticRoot,"theme.css"),"utf8")
      + fs.readFileSync(path.join(staticRoot,"ide.css"),"utf8")) + "}));"
  );
  await window.webContents.executeJavaScript(fs.readFileSync(path.join(staticRoot,"scientific-chart.js"),"utf8"));
  await window.webContents.executeJavaScript(fs.readFileSync(path.join(staticRoot,"results-workbench.js"),"utf8"));
  const payload = {
    execution_state:"completed",deliverable_state:"complete",
    experiment:{name:"Scientific PDF regression",study:{kind:"dc_sweep"},
      regions:[{id:"silicon-bulk",material:"silicon",x0:{magnitude_si:0},x1:{magnitude_si:1e-6}}],
      contacts:[{id:"left",location:"left"},{id:"right",location:"right"}]},
    result:{backend:"devsim",schema_version:"1.0",status:"completed",
      bias_points:[{bias_v:0.1,converged:true,terminal_currents_a_per_m2:{left:2e-6,right:-2e-6}}],
      fields:{potential:{positions_m:[0,5e-7,1e-6],values:[0,0.05,0.1],unit:"V"},
        electric_field:{positions_m:[0,5e-7,1e-6],values:[-1e5,-1e5,-1e5],unit:"V/m"}}},
    validation:{overall:"failed",checks:[{id:"current-conservation",level:"physical",status:"failed",
      message:"Terminal conservation requires review",measured_value:2.96e-6,limit:1e-6,
      unit:"A/m^2",absolute_tolerance:1e-6,relative_tolerance:1e-4,scale:2e-8}]},
    manifest:{run_id:"run-pdf-regression",backend:"devsim",simulator_version:"test-simulator-1",
      compiler_version:"test-compiler-1",input_digest:"input-sha256-fixture",runtime_digest:"runtime-sha256-fixture"},
  };
  await window.webContents.executeJavaScript(
    "AgentKronigResults.render(document.getElementById('results')," + JSON.stringify(payload) + ");"
  );
  const info = await window.webContents.executeJavaScript(
    "({charts:document.querySelectorAll('.result-chart-line').length, text:document.body.textContent})"
  );
  if (!info.charts || !info.text.includes("Terminal conservation requires review")) {
    throw new Error("The scientific renderer did not produce charts and validation");
  }
  // Exercise the real allowlisted preload bridge and main-process save handler.
  const {ipcMain} = require("electron");
  ipcMain.handle("desktop:export-results-pdf", (event,payload) => exportResultsPdf({
    dialog:{async showSaveDialog() {return {canceled:false,filePath:destination};}},
    sender:event.sender,parent:window,payload,
  }));
  const result = await window.webContents.executeJavaScript(
    "agentKronigDesktop.exportResultsPdf({suggestedName:'Scientific PDF regression.pdf'})"
  );
  if (result.cancelled || result.path !== destination || !fs.existsSync(destination)) {
    throw new Error("The PDF bridge did not return the selected saved path");
  }
  const remaining = await window.webContents.executeJavaScript("document.querySelector('.ak-print-document') !== null");
  if (remaining) throw new Error("Export left its temporary print document in the renderer");
  window.destroy();
  app.quit();
}).catch((error) => {console.error(error); app.exit(1);});
