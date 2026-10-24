// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";
const require = createRequire(import.meta.url);
const compile = path => ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
const model = { exports: {} };
new Function("module", "exports", compile("../src/multiportFixtureModel.ts"))(model, model.exports);
const network = (id, port_names) => ({ id, port_names, reference_impedance_ohm: 50, frequencies_hz: [1, 2], s_parameters: [1, 2].map(() => port_names.map(() => port_names.map(() => ({ real: 0, imag: 0 })))) });
const request = { contract: "spike/multiport-deembedding-request/v1", measured: network("measured", ["outside"]), fixture: network("fixture", ["inside", "outside"]), external_ports: ["outside"], dut_ports: ["inside"] };
const result = source => ({ contract: "spike/multiport-deembedding-result/v1", model_status: "experimental", production_qualified: false, source_request: structuredClone(source), input_digest: "a".repeat(64), derived_network: network("derived", ["inside"]), diagnostics: [1, 2].map(frequency_hz => ({ frequency_hz, transmission_condition_product: 1, outward_condition: 1, inward_condition: 1, recovery_condition: 1, feedback_condition: 1, max_solve_backward_residual: 0, reconstruction_residual: 0, sampled_smax: 0 })), limitations: ["Experimental supplied fixture only"] });
assert.deepEqual(model.exports.parseFixtureRequest(JSON.stringify(request)), request);
assert.throws(() => model.exports.parseFixtureRequest("{}"));
assert.throws(() => model.exports.parseFixtureRequest(" ".repeat(8 * 1024 * 1024 + 1)));
for (const mutate of [r => r.production_qualified = true, r => r.model_status = "validated", r => r.source_request.measured.id = "other", r => r.derived_network.port_names = ["wrong"], r => r.derived_network.frequencies_hz = [2, 3], r => r.diagnostics.pop(), r => r.diagnostics[0].sampled_smax = Infinity, r => r.derived_network.s_parameters[0][0][0].real = NaN]) {
  const r = result(request); mutate(r); assert.throws(() => model.exports.admitFixtureResult(r, request));
}
const nodes = n => !n || typeof n !== "object" ? [] : Array.isArray(n) ? n.flatMap(nodes) : [n, ...nodes(n.props?.children)];
const text = n => Array.isArray(n) ? n.map(text).join("") : n && typeof n === "object" ? text(n.props?.children) : String(n ?? "");
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return { promise, resolve }; };
function mount({ desktop = true, worker = async ({ params }) => ({ ok: true, result: result(params.request) }) } = {}) {
  const slots = [], effects = [], cancelled = [], exports = [];
  let index = 0, guided;
  const module = { exports: {} };
  const doc = { createElement: () => ({ click() { exports.push(this.download); } }) };
  new Function("require", "module", "exports", compile("../src/MultiportFixturePanel.tsx"))(name => {
    if (name === "react") return { ...React, useState(initial) { const i = index++; if (!(i in slots)) slots[i] = typeof initial === "function" ? initial() : initial; return [slots[i], v => { slots[i] = typeof v === "function" ? v(slots[i]) : v; }]; }, useRef(initial) { const i = index++; return slots[i] ?? (slots[i] = { current: initial }); }, useMemo: f => f(), useEffect(f) { const i = index++; if (!(i in slots)) { slots[i] = true; effects.push(f()); } } };
    if(name === "./useGuidedRunAdapter")return {useGuidedRunAdapter:adapter=>{guided=adapter;return ()=>adapter.run(adapter.context,new AbortController().signal).catch(()=>{});}};
    if (name === "./workerBridge") return { isDesktopShell: () => desktop, runLocalWorker: worker, cancelLocalWorker: async id => { cancelled.push(id); return true; } };
    if (name === "./panelPresentation") return { usePanelPresentation: () => ({ ownerDocument: doc }) };
    if (name === "./multiportFixtureModel") return model.exports;
    if (name.endsWith(".css")) return {};
    return require(name);
  }, module, module.exports);
  const render = () => { index = 0; return module.exports.default(); };
  const find = label => nodes(render()).find(n => n.props?.["aria-label"] === label || n.type === "button" && text(n) === label);
  const edit = value => find("Multiport request JSON").props.onChange({ target: { value } });
  const click = label => { const n = find(label); assert.ok(n); assert.ok(!n.props.disabled, `${label} enabled`); return n.props.onClick(); };
  return { adapter:()=>guided,render, find, edit, click, cancelled, exports, unmount: () => effects.forEach(f => f?.()), retained: () => find("Retained fixture result"), import: file => find("Import multiport request JSON").props.onChange({ target: { files: [file], value: "x" } }) };
}
const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
const ui = mount(); ui.render();assert.ok((await ui.adapter().check()).requirements.length,"Guided run refuses a missing fixture request"); ui.edit(JSON.stringify(request));
ui.render();assert.equal((await ui.adapter().check()).requirements.length,0);
assert.equal(ui.find("Run fixture removal").props.disabled, false);
ui.click("Run fixture removal"); await flush(); assert.ok(ui.retained());
ui.click("Export source and result"); assert.equal(ui.exports.length, 1);
ui.edit("{}"); assert.equal(ui.retained(), undefined); assert.equal(ui.find("Export source and result").props.disabled, true);
const browser = mount({ desktop: false }); browser.edit(JSON.stringify(request)); assert.equal(browser.find("Run fixture removal").props.disabled, true);
for (const response of [{ ok: false, error: "failed" }, { ok: true, result: {} }]) { const bad = mount({ worker: async () => response }); bad.edit(JSON.stringify(request)); bad.click("Run fixture removal"); await flush(); assert.equal(bad.retained(), undefined); assert.equal(bad.find("Export source and result").props.disabled, true); }
const numericalFailure = mount({ worker: async () => ({ ok: false, error: "Network transformation failed.", error_detail: { context: { network_code: "MULTIPORT_DEEMBEDDING_ILL_CONDITIONED" }, detail: "Singular outward fixture transmission" } }) });
numericalFailure.edit(JSON.stringify(request)); numericalFailure.click("Run fixture removal"); await flush();
assert.match(text(numericalFailure.render()), /MULTIPORT_DEEMBEDDING_ILL_CONDITIONED/);
assert.match(text(numericalFailure.render()), /Singular outward fixture transmission/);
assert.equal(numericalFailure.retained(), undefined);
assert.equal(numericalFailure.find("Export source and result").props.disabled, true);
const pending = deferred(); let payload;
const late = mount({ worker: arg => { payload = arg; return pending.promise; } }); late.edit(JSON.stringify(request)); late.click("Run fixture removal");
assert.equal(late.find("Run fixture removal").props.disabled, true); late.click("Cancel fixture removal"); assert.deepEqual(late.cancelled, [payload.id]); pending.resolve({ ok: true, result: result(request) }); await flush(); assert.equal(late.retained(), undefined);
const unmountPending = deferred(); const gone = mount({ worker: () => unmountPending.promise }); gone.edit(JSON.stringify(request)); gone.click("Run fixture removal"); gone.unmount(); assert.equal(gone.cancelled.length, 1); unmountPending.resolve({ ok: true, result: result(request) }); await flush(); assert.equal(gone.retained(), undefined);
const read = deferred(); const importing = mount(); importing.import({ size: 10, text: () => read.promise }); importing.edit("newer draft"); read.resolve(JSON.stringify(request)); await flush(); assert.equal(importing.find("Multiport request JSON").props.value, "newer draft");
importing.import({ size: 8 * 1024 * 1024 + 1, text() { throw new Error("must not read"); } }); await flush(); assert.equal(importing.find("Multiport request JSON").props.value, "");
const sourceBefore = JSON.stringify(request); let delivered;
const immutable = mount({ worker: async ({ params }) => { delivered = result(params.request); params.request.measured.id = "mutated transport"; return { ok: true, result: delivered }; } }); immutable.edit(sourceBefore); immutable.click("Run fixture removal"); await flush(); assert.ok(immutable.retained()); delivered.limitations[0] = "changed after delivery"; assert.ok(!text(immutable.render()).includes("changed after delivery")); assert.equal(JSON.stringify(request), sourceBefore);
const workbench = readFileSync(new URL("../src/SParameterWorkbench.tsx", import.meta.url), "utf8");
assert.match(workbench, /<div hidden=\{!multiportView\}><MultiportFixturePanel/);
assert.match(workbench, /<div hidden=\{workflowView \|\| multiportView\}>/);
console.log("Multiport fixture UI admission, worker lifecycle, cancellation, imports and immutable capture passed.");
