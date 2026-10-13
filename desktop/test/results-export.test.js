const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {exportResultsPdf} = require("../src/results-export");

test("cancelled native save never prints or writes a PDF", async () => {
  const result = await exportResultsPdf({
    dialog:{async showSaveDialog() {return {canceled:true};}},
    sender:{async printToPDF() {throw new Error("cancelled save printed");}},
    payload:{suggestedName:"../results.pdf"},
  });
  assert.deepEqual(result, {cancelled:true,path:null});
});

test("native save returns the chosen path only after the PDF exists", async (context) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "agent-kronig-export-"));
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  const target = path.join(directory, "chosen-results.pdf");
  const result = await exportResultsPdf({
    dialog:{async showSaveDialog(_parent, options) {
      assert.equal(options.defaultPath,"scientific-results.pdf");
      return {canceled:false,filePath:target};
    }},
    sender:{async executeJavaScript() {}, async printToPDF(options) {
      assert.equal(options.printBackground,true);
      return Buffer.from("%PDF-1.7\nfixture scientific document\n%%EOF");
    }},
    payload:{suggestedName:"scientific results.pdf"},
  });
  assert.deepEqual(result, {cancelled:false,path:target});
  assert.match(fs.readFileSync(target,"utf8"), /^%PDF/);
  if (process.platform !== "win32") assert.equal(fs.statSync(target).mode & 0o777,0o600);
});

test("failed printing does not overwrite an existing destination", async (context) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "agent-kronig-export-"));
  context.after(() => fs.rmSync(directory, {recursive:true,force:true}));
  const target = path.join(directory,"previous.pdf");
  fs.writeFileSync(target,"previous report");
  await assert.rejects(exportResultsPdf({
    dialog:{async showSaveDialog() {return {canceled:false,filePath:target};}},
    sender:{async executeJavaScript() {}, async printToPDF() {throw new Error("printing failed");}},
  }), /printing failed/);
  assert.equal(fs.readFileSync(target,"utf8"), "previous report");
});
