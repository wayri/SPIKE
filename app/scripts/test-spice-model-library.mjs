// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
const require = createRequire(import.meta.url);
function load(name, mocks = {}) {
  const code = readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
  const module = { exports: {} };
  const compiled = ts.transpileModule(code, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function("require", "module", "exports", compiled)(id => id.endsWith(".css") ? {} : id in mocks ? mocks[id] : require(id), module, module.exports);
  return module.exports;
}
const api = load("spiceModelLibrarySession.ts");
const { SpiceModelLibrarySession, MODEL_LIBRARY_MAX_BYTES, emptyLibraryImport } = api;
const inspection = { contract: "spike/spice-model-library-inspection/v1", valid: true, source_sha256: "a".repeat(64), candidates: ["stage", "pair"].map(name => ({ id: name, subcircuit_name: name, pins: ["in", "out"], dependency_names: [], default_parameters: { R: "1k" } })), diagnostics: [] };
const imported = name => ({ contract: "spike/spice-model-import/v1", execution_admitted: false, model: { id: name, name, kind: "subcircuit", pins: ["in", "out"], subcircuit_name: name, source: "source", import_provenance: { source_sha256: "a".repeat(64) } } });
const pending = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
{
  let reads = 0, calls = 0;
  const session = new SpiceModelLibrarySession(async () => { calls++; }, () => {}, () => assert.fail("oversize file imported"));
  await session.readFile({ size: MODEL_LIBRARY_MAX_BYTES + 1, name: "huge.lib", text: async () => { reads++; return "huge"; } });
  assert.equal(reads, 0); assert.equal(calls, 0); assert.match(session.state.error, /No file content was read/);
}
{
  const job = pending();
  const session = new SpiceModelLibrarySession(() => job.promise, () => {}, () => assert.fail("stale import"));
  session.setSource("old"); const operation = session.inspect(); session.setSource("new");
  job.resolve({ ok: true, result: inspection }); await operation;
  assert.equal(session.state.inspection, null); assert.equal(session.state.text, "new"); assert.equal(session.state.busy, false);
}
{
  const calls = [], added = [];
  const session = new SpiceModelLibrarySession(async request => { calls.push(request); return { ok: true, result: request.method.startsWith("inspect") ? inspection : imported(request.params.subcircuit_name) }; }, () => {}, model => added.push(model));
  session.setSource("library", "owned.lib"); await session.inspect(); session.select("pair");
  await session.importSelected("user fixture", "Apache-2.0");
  assert.equal(added.length, 1); assert.equal(added[0].subcircuit_name, "pair");
  assert.deepEqual(calls.map(call => call.method), ["inspect_spice_model_library", "import_spice_model"]);
  assert.equal(calls[1].params.license_note, "Apache-2.0");
  session.setSource("edited"); assert.equal(session.state.selected, ""); await session.importSelected("", ""); assert.equal(calls.length, 2);
}
for (const mode of ["mismatch", "dispose", "duplicate", "failure"]) {
  const job = pending(); let added = 0;
  const session = new SpiceModelLibrarySession(async request => request.method.startsWith("inspect") ? { ok: true, result: inspection } : job.promise, () => {}, () => { if (mode === "duplicate") throw new Error("Already in this project"); added++; });
  session.setSource("library"); await session.inspect(); const operation = session.importSelected("", "");
  if (mode === "dispose") session.dispose();
  const result = imported("stage"); if (mode === "mismatch") result.model.import_provenance.source_sha256 = "b".repeat(64);
  job.resolve(mode === "failure" ? { ok: false, error_detail: { detail: "Missing dependency child" } } : { ok: true, result }); await operation;
  assert.equal(added, 0);
  if (mode !== "dispose") assert.ok(session.state.error);
  if (mode === "failure") assert.match(session.state.error, /Missing dependency child/);
}
{
  const first = pending(); const session = new SpiceModelLibrarySession(async () => ({ ok: true, result: inspection }), () => {}, () => {});
  const read = session.readFile({ size: 1, name: "old.lib", text: () => first.promise }); session.setSource("new", "new.lib"); first.resolve("old"); await read;
  assert.equal(session.state.name, "new.lib");
}
const search = load("optionSearch.ts");
assert.equal(search.optionMatchesQuery("precision_filter in out", "prec* out"), true);
assert.equal(search.optionMatchesQuery("filter", "f?lt?r"), true);
let renderedState = null;
function render(state) {
  renderedState = state; let at = 0;
  const react = { ...React, useState: value => { const real = React.useState(value); return at++ === 0 && renderedState ? [renderedState, () => {}] : real; } };
  const view = load("SpiceModelLibraryImport.tsx", { react, "./workerBridge": { runLocalWorker: async () => assert.fail("Rendering cannot execute a worker") }, "./optionSearch": search, "./spiceModelLibrarySession": api, "./icons": { FileOutput: () => null, FolderOpen: () => null, ListChecks: () => null, X: () => null }, "./SectionHelpButton": () => React.createElement("button", { type: "button" }, "Help") }).default;
  return renderToStaticMarkup(React.createElement(view, { disabled: false, onAdd: () => {}, onClose: () => {} }));
}
assert.match(render(emptyLibraryImport()), /Choose SPICE model library/);
const ready = render({ ...emptyLibraryImport(), inspection, selected: "pair" });
assert.match(ready, /Add selected model to project/); assert.match(ready, /Pin order/); assert.match(ready, /Required|Execution route/);
const rejected = render({ ...emptyLibraryImport(), inspection: { ...inspection, valid: false, candidates: [], diagnostics: [{ code: "REJECTED", severity: "error", line: 2, message: "<script>unsafe</script>" }] } });
assert.match(rejected, /role="alert"/); assert.match(rejected, /&lt;script&gt;/); assert.doesNotMatch(rejected, /<script>unsafe/);
console.log("Model-library async admission, stale-response, byte-budget, recovery, wildcard and rendered-state checks passed");

// Project replacement remounts the owning workbench; disposal invalidates its pending Add.
assert.match(readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8"), /<SpiceWorkbench key=\{projectGeneration\.current\}/);
{
  const job = pending(); const projectB = [];
  const sessionA = new SpiceModelLibrarySession(async request => request.method.startsWith("inspect") ? { ok: true, result: inspection } : job.promise, () => {}, model => projectB.push(model));
  sessionA.setSource("project A library"); await sessionA.inspect();
  const add = sessionA.importSelected("", "");
  sessionA.dispose(); // React unmount on a new project generation.
  job.resolve({ ok: true, result: imported("stage") }); await add;
  assert.deepEqual(projectB, []);
}
