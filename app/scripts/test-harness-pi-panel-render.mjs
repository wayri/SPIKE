import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("../src/HarnessPiPanel.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
} }).outputText;

function loadPanel(result = null) {
  const uiModule = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return {
      ...React,
      useEffect() {},
      useMemo: callback => callback(),
      useRef: initial => ({ current: initial }),
      useState: initial => [initial === null ? result : typeof initial === "function" ? initial() : initial, () => {}],
    };
    if (name === "./workerBridge") return { cancelLocalWorker() {}, cancelLocalWorkerCleanup() {}, runLocalWorker() {} };
    return require(name);
  }, uiModule, uiModule.exports);
  return uiModule.exports.default;
}

const malformed = { contract: "spike/harness/v1", id: "H", name: "H", connectors: [], wires: [], extensions: { "spike.harness-pi": { terminals: "broken", contacts: null } } };
const malformedHtml = renderToStaticMarkup(loadPanel()({ value: malformed, onChange() {} }));
assert.match(malformedHtml, /Saved Harness PI setup is malformed/);
assert.match(malformedHtml, /Reset malformed Harness PI setup/);

const endpointA = { connector: "J:source", pin: "1" }; const endpointB = { connector: "J:return", pin: "0" };
const harness = { contract: "spike/harness/v1", id: "H", name: "H", connectors: [
  { id: "J:source", pins: [{ id: "1" }] }, { id: "J:return", pins: [{ id: "0" }] },
], wires: [], extensions: { "spike.harness-pi": { ground: endpointB, terminals: [
  { id: "supply", type: "voltage_source", positive: endpointA, negative: endpointB, value: 12 },
  { id: "load", type: "current_load", positive: endpointA, negative: endpointB, value: 2 },
], contacts: [] } } };
const failed = { status: "failed", model_status: "experimental", native_result: { status: "failed", diagnostics: [{ message: "singular circuit" }] }, limitations: ["DC only"] };
const html = renderToStaticMarkup(loadPanel(failed)({ value: harness, onChange() {} }));
assert.match(html, /Sources and loads/);
assert.match(html, /supply positive/);
assert.match(html, /load negative/);
assert.match(html, /\/> V<\/td>/);
assert.match(html, /\/> A<\/td>/);
assert.match(html, /wire loss unavailable/);
assert.match(html, /contact loss unavailable/);
assert.match(html, /singular circuit/);
assert.ok(!html.includes("wire loss 0"), "failed runs must not invent zero wire loss");
assert.ok(!html.includes("contact loss 0"), "failed runs must not invent zero contact loss");
console.log("Harness PI panel rendered malformed setup and failed-result states honestly.");
