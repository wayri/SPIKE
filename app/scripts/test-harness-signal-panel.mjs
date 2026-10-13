// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";
const model = await importTestTypescript("harnessSignalModel");
const root = fileURLToPath(new URL("../../", import.meta.url));
const localPython = fileURLToPath(new URL(process.platform === "win32" ? "../../.venv/Scripts/python.exe" : "../../.venv/bin/python", import.meta.url));
const python = process.env.SPIKE_TEST_PYTHON ?? process.env.PYTHON ?? (existsSync(localPython) ? localPython : "python");
function backend(code, input) {
  const process = spawnSync(python, ["-c", code], { cwd: root, encoding: "utf8", input: input && JSON.stringify(input), env: { ...globalThis.process.env, OPENBLAS_NUM_THREADS: "1", OMP_NUM_THREADS: "1" } });
  assert.equal(process.status, 0, process.stderr); return JSON.parse(process.stdout);
}
const original = backend("import json; from tests.python.test_harness_signal import fixture; print(json.dumps(fixture()))");
const setup = { selection: original.selection, source: original.provenance.source, model_input: Object.fromEntries(Object.keys(model.HARNESS_SI_FIELDS).map(key=>[key,String(original.model[key])])) };
const value = { ...original.harness, extensions: { [model.HARNESS_SI_KEY]: setup } };
const request = model.harnessSignalRequest(value, setup);
const result = backend("import json,sys; from python.spike_core.harness_signal import run_harness_si; print(json.dumps(run_harness_si(json.load(sys.stdin))))", request);
assert(model.validHarnessSiResult(result, request));
const saved = structuredClone(value); saved.extensions[model.HARNESS_SI_KEY].latest_result = result;
assert(model.validHarnessSiResult(result, model.harnessSignalRequest(saved, saved.extensions[model.HARNESS_SI_KEY])), "saved result is nonrecursive and reopens against exact inputs");
const reopened = backend("import json,sys; print(json.dumps(json.load(sys.stdin),sort_keys=True))", saved);
assert(model.validHarnessSiResult(reopened.extensions[model.HARNESS_SI_KEY].latest_result,
  model.harnessSignalRequest(reopened, reopened.extensions[model.HARNESS_SI_KEY])), "real Python sorted project JSON preserves unchanged result admission");
const changed = structuredClone(saved); changed.wires[0].length_mm = 1200;
assert(!model.validHarnessSiResult(result, model.harnessSignalRequest(changed, setup)));
assert(!model.validHarnessSiResult({...result,s_real:[]},request));
for (const patch of [{ status:"failed" }, { model_status:"unsupported" }, {field_coupling_executed:true},
  {wire_ids:{}}, {wire_ids:[...result.wire_ids].reverse()}, {mode:"single_ended"}, {port_bindings:[]},
  {reference_impedance_ohm:[50,50]}, {request_digest:"invalid"}, {provenance:{}},
  {frequency_hz:result.frequency_hz.map((f,i)=>i===2?f+100:f)}]) {
  assert(!model.validHarnessSiResult({...result,...patch},request), JSON.stringify(patch));
}
assert.throws(()=>model.harnessSignalRequest(value,{...setup,model_input:{}}),/Enter/);
assert.throws(()=>model.harnessSignalRequest(value,{...setup,source:""}),/source/);
const require = createRequire(import.meta.url), loaded = { exports: {} };
const source = readFileSync(new URL("../src/HarnessSignalPanel.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
new Function("require","module","exports",compiled)(name=>{
  if(name==="react") return {...React,useEffect(){},useRef: initial=>({current:initial}),useState: initial=>[typeof initial==="function"?initial():initial,()=>{}]};
  if(name==="./harnessSignalModel") return model;
  if(name==="./workerBridge") return {runLocalWorker(){},cancelLocalWorker(){},cancelLocalWorkerCleanup(){}};
  if(name==="./PlotlyChart") return {__esModule:true,default:props=>React.createElement("div",{"data-series":props.data.length},"Actual admitted network plot")};
  if(name.endsWith(".css")) return {};
  return require(name);
},loaded,loaded.exports);
const Panel = loaded.exports.default;
const html = renderToStaticMarkup(React.createElement(Panel,{value:saved,onChange(){}}));
assert.match(html,/Actual admitted network plot/); assert.match(html,/Saved with the project/);
assert.match(renderToStaticMarkup(React.createElement(Panel,{value:reopened,onChange(){}})), /Actual admitted network plot/);
const malformed = structuredClone(saved); malformed.extensions[model.HARNESS_SI_KEY].latest_result.wire_ids = {};
assert.doesNotMatch(renderToStaticMarkup(React.createElement(Panel,{value:malformed,onChange(){}})), /Actual admitted network plot/);
const stale = renderToStaticMarkup(React.createElement(Panel,{value:changed,onChange(){}}));
assert.match(stale,/Saved SI result is stale/); assert.doesNotMatch(stale,/Actual admitted network plot/);
console.log("Harness SI panel reopens actual backend results, rejects stale inputs and preserves explicit model controls.");
