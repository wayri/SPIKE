// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const root = resolve(import.meta.dirname, "../..");
const source = readFileSync(resolve(root, "app/src/CapacitorPlacementPanel.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS,
  target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const nodeRequire = createRequire(import.meta.url);
const Plot = props => React.createElement("div", { "data-plot-title": props.title, "data-x-scale": props.layout.xaxis.type ?? "linear" });
function loadModule(reactDependency, worker) {
  const loaded = { exports: {} };
  new Function("require", "module", "exports", compiled)(name => {
    if (name === "react") return reactDependency;
    if (name === "react/jsx-runtime") return nodeRequire(name);
    if (name === "./workerBridge") return { runLocalWorker: worker };
    if (name === "./PlotlyChart") return { default: Plot, __esModule: true };
    if (name.endsWith(".css")) return {};
    return nodeRequire(name);
  }, loaded, loaded.exports);
  return loaded.exports;
}
const api = loadModule(React, async () => { throw new Error("Unexpected static worker dispatch"); });
const request = api.syntheticCapacitorPlacementRequest();
const input = JSON.stringify(request, null, 2);
assert.deepEqual(api.parseCapacitorPlacementRequest(input), request);
assert.match(request.provenance.conditions, /No PCB extraction/);
for (const malformed of ["", "{}", "null", "{", input.replace('"current_a_rms": 1', '"current_a_rms": 1e999')]) {
  assert.throws(() => api.parseCapacitorPlacementRequest(malformed));
}
const foreign = structuredClone(request); foreign.reference_return.occurrence_id = "another-board";
assert.throws(() => api.parseCapacitorPlacementRequest(JSON.stringify(foreign)), /same board occurrence/);
const shape = structuredClone(request); shape.z_ohm[0][0][0] = [1];
assert.throws(() => api.parseCapacitorPlacementRequest(JSON.stringify(shape)), /Z must/);
const duplicate = structuredClone(request); duplicate.ports[1].id = duplicate.ports[0].id;
assert.throws(() => api.parseCapacitorPlacementRequest(JSON.stringify(duplicate)), /unique/);

// Use the actual Python numerical result to test the boundary, not a frontend
// reimplementation or a hand-authored successful response.
const localPython = resolve(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const python = process.env.SPIKE_TEST_PYTHON ?? process.env.PYTHON ?? (existsSync(localPython) ? localPython : "python");
function evaluate(value) {
  const run = spawnSync(python, ["-c", "import json,sys; from python.spike_core.capacitor_placement import evaluate_capacitor_placement; print(json.dumps(evaluate_capacitor_placement(json.load(sys.stdin)),allow_nan=False))"],
    { cwd: root, input: JSON.stringify(value), encoding: "utf8", maxBuffer: 4 * 1024 * 1024,
      env: { ...process.env, OPENBLAS_NUM_THREADS: "1", OMP_NUM_THREADS: "1" } });
  assert.equal(run.status, 0, run.stderr || String(run.error));
  return JSON.parse(run.stdout);
}
const result = evaluate(request);
assert.equal(api.validCapacitorPlacementResult(result, request), true);
for (const change of [
  r => { r.z_ohm[0][0][0][0] += .001; },
  r => { r.loads[0].current_a_rms += 1; },
  r => { r.dc_voltage_v += 1; },
]) {
  const differentNetwork = structuredClone(request); change(differentNetwork);
  assert.equal(api.validCapacitorPlacementResult(result, differentNetwork), false,
    "same identity/frequency/provenance must not admit a result for different Z/current/DC inputs");
}
const absentSnapshot = { ...result }; delete absentSnapshot.request_snapshot;
assert.equal(api.validCapacitorPlacementResult(absentSnapshot, request), false);
const mismatchedSnapshot = structuredClone(result); mismatchedSnapshot.request_snapshot.dc_voltage_v += 1;
assert.equal(api.validCapacitorPlacementResult(mismatchedSnapshot, request), false, "a result cannot reopen against a different complete request snapshot");
const reordered = structuredClone(request);
reordered.provenance = { conditions: request.provenance.conditions, source_id: request.provenance.source_id };
assert.equal(api.sameCapacitorPlacementRequest(request, reordered), true, "object key order must not change request identity");
assert.equal(api.validCapacitorPlacementResult(result, reordered), true);
const reorderedSnapshot = { ...result, request_snapshot: reordered };
assert.equal(api.validCapacitorPlacementResult(reorderedSnapshot, request), true);
for (const broken of [
  { ...result, model_status: "validated" },
  { ...result, board_occurrence_id: "another-board" },
  { ...result, baseline: null },
  { ...result, ranked_candidate_ids: [result.best_candidate_id, result.best_candidate_id] },
  { ...result, candidates: result.candidates.slice(1) },
]) assert.equal(api.validCapacitorPlacementResult(broken, request), false);
const misbound = structuredClone(result); misbound.candidates[0].x_mm += 1;
assert.equal(api.validCapacitorPlacementResult(misbound, request), false);
const wrongSample = structuredClone(result); wrongSample.baseline.samples[0].frequency_hz += 1;
assert.equal(api.validCapacitorPlacementResult(wrongSample, request), false);
const infinite = structuredClone(result); infinite.candidates[0].worst_target_ratio = Infinity;
assert.equal(api.validCapacitorPlacementResult(infinite, request), false);
const hv = structuredClone(request); hv.dc_voltage_v = 800;
const hvResult = evaluate(hv);
assert.equal(api.validCapacitorPlacementResult(hvResult, hv), true);
assert.equal(hvResult.best_candidate_id, null);
const illegalRank = structuredClone(hvResult); illegalRank.ranked_candidate_ids = [illegalRank.candidates[0].id]; illegalRank.best_candidate_id = illegalRank.candidates[0].id;
assert.equal(api.validCapacitorPlacementResult(illegalRank, hv), false, "rating-excluded candidates must never be ranked");

const emptyMarkup = renderToStaticMarkup(React.createElement(api.default, { workerAvailable: false }));
assert.match(emptyMarkup, /Local solver worker unavailable/);
assert.match(emptyMarkup, /disabled=""[^>]*>Compare candidates/);
assert.doesNotMatch(emptyMarkup, /Selected candidate:/, "a blank panel must not manufacture results");
const reopenedMarkup = renderToStaticMarkup(React.createElement(api.default, {
  workerAvailable: true, initialRequest: request, initialResult: result,
}));
assert.match(reopenedMarkup, /synthetic-two-node-example/, "the saved request initializes the editable JSON source");
assert.match(reopenedMarkup, /Selected candidate:/, "an exact saved backend result is admitted on reopen");
assert.doesNotMatch(reopenedMarkup, /Inputs differ from the solved setup/);
const rejectedReopenMarkup = renderToStaticMarkup(React.createElement(api.default, {
  workerAvailable: true, initialRequest: request, initialResult: mismatchedSnapshot,
}));
assert.match(rejectedReopenMarkup, /synthetic-two-node-example/, "a valid saved request remains editable when its result is rejected");
assert.doesNotMatch(rejectedReopenMarkup, /Selected candidate:/, "a mismatched saved result is not displayed");
const initializationStates = [], initializationRefs = [];
let initializationStateCursor = 0, initializationRefCursor = 0, requestReads = 0;
const initializationHooks = { useEffect() {},
  useRef(initial) { const i = initializationRefCursor++; if (!(i in initializationRefs)) initializationRefs[i] = { current: initial }; return initializationRefs[i]; },
  useState(initial) { const i = initializationStateCursor++; if (!(i in initializationStates)) initializationStates[i] = typeof initial === "function" ? initial() : initial;
    return [initializationStates[i], value => { initializationStates[i] = typeof value === "function" ? value(initializationStates[i]) : value; }]; },
};
const countedRequest = new Proxy(request, { get(target, property, receiver) { requestReads += 1; return Reflect.get(target, property, receiver); } });
const initializationModule = loadModule(initializationHooks, async () => { throw new Error("Unexpected initialization worker dispatch"); });
const renderInitializedPanel = () => { initializationStateCursor = 0; initializationRefCursor = 0;
  return initializationModule.default({ workerAvailable: true, initialRequest: countedRequest, initialResult: result }); };
renderInitializedPanel();
const readsAfterMount = requestReads;
renderInitializedPanel();
assert.equal(requestReads, readsAfterMount, "large persisted requests are parsed and admitted once per panel mount, not on every render");
const markup = renderToStaticMarkup(React.createElement(api.CapacitorPlacementResults, { result, selectedId: result.best_candidate_id, onSelect() {} }));
assert.match(markup, /data-x-scale="log"/);
assert.match(markup, /Capacitor candidate XY map/);
assert.match(markup, /No unsampled resonance search/);
assert.match(markup, /Required voltage rating/);
assert.match(markup, /Source, return and model limits/);
const excludedMarkup = renderToStaticMarkup(React.createElement(api.CapacitorPlacementResults, { result: hvResult, selectedId: hvResult.candidates[0].id, onSelect() {} }));
assert.match(excludedMarkup, /capacitor_voltage_rating/);
assert.match(excludedMarkup, /No eligible candidate improves/);

const states = [], refs = [], pending = [], statuses = [], captured = [];
let stateCursor = 0, refCursor = 0;
const hooks = { useEffect() {},
  useRef(initial) { const i = refCursor++; if (!(i in refs)) refs[i] = { current: initial }; return refs[i]; },
  useState(initial) { const i = stateCursor++; if (!(i in states)) states[i] = typeof initial === "function" ? initial() : initial;
    return [states[i], value => { states[i] = typeof value === "function" ? value(states[i]) : value; }]; },
};
const live = loadModule(hooks, value => new Promise(resolvePromise => pending.push({ value, resolve: resolvePromise })));
const mount = () => { stateCursor = 0; refCursor = 0; return live.default({ workerAvailable: true,
  onStatus: m => statuses.push(m), onResult: (requestValue, resultValue) => captured.push([requestValue, resultValue]) }); };
function find(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) { const found = find(child, predicate); if (found) return found; }
  return null;
}
const button = label => find(mount(), n => n.type === "button" && n.props.children === label);
const textarea = () => find(mount(), n => n.type === "textarea");
const flush = async () => { await new Promise(done => setImmediate(done)); await new Promise(done => setImmediate(done)); };
button("Load synthetic example").props.onClick();
assert.deepEqual(api.parseCapacitorPlacementRequest(textarea().props.value), request);
button("Compare candidates").props.onClick();
assert.equal(pending[0].value.method, "evaluate_capacitor_placement");
assert.deepEqual(pending[0].value.params, { request });
assert.equal(button("Comparing candidates...").props.disabled, true);
// Editing invalidates the old dispatch immediately and permits a newer request.
textarea().props.onChange({ target: { value: JSON.stringify(hv) } });
button("Compare candidates").props.onClick();
pending[1].resolve({ ok: true, result: hvResult }); await flush();
pending[0].resolve({ ok: true, result }); await flush();
assert.equal(captured.length, 1, "only the current successful run is persisted");
assert.deepEqual(captured[0][0], hv);
assert.strictEqual(captured[0][1], hvResult);
let view = find(mount(), n => n.type === live.CapacitorPlacementResults);
assert.equal(view.props.result, hvResult, "obsolete responses must not replace a newer input/result");
textarea().props.onChange({ target: { value: input } });
assert.match(renderToStaticMarkup(mount()), /Inputs differ from the solved setup/);
button("Compare candidates").props.onClick();
pending[2].resolve({ ok: false, error: "test network rejected" }); await flush();
assert.match(renderToStaticMarkup(mount()), /test network rejected/);
assert.match(renderToStaticMarkup(mount()), /last completed result is retained/);
assert.equal(captured.length, 1, "a failed retry retains the last saved result and does not publish a callback");
button("Compare candidates").props.onClick();
pending[3].resolve({ ok: true, result }); await flush();
assert.equal(captured.length, 2);
assert.strictEqual(captured[1][1], result);
assert.doesNotMatch(renderToStaticMarkup(mount()), /Inputs differ from the solved setup/);
view = find(mount(), n => n.type === live.CapacitorPlacementResults);
const selected = request.candidates[0].id;
let resultsTree = live.CapacitorPlacementResults(view.props);
find(resultsTree, n => n.type === Plot && n.props.title === "Capacitor candidate XY map").props.onPointClick({ customdata: selected });
view = find(mount(), n => n.type === live.CapacitorPlacementResults);
assert.equal(view.props.selectedId, selected, "map click selects the candidate and its frequency curve");
resultsTree = live.CapacitorPlacementResults(view.props);
const curve = find(resultsTree, n => n.type === Plot && n.props.title === "Capacitor placement impedance sweep");
assert.equal(curve.props.layout.xaxis.type, "log");
assert.equal(curve.props.layout.yaxis.type, "log");
assert.match(curve.props.data[1].name, new RegExp(selected));
const other = request.candidates[1].id;
find(resultsTree, n => n.type === "button" && n.props.children === other).props.onClick();
assert.equal(find(mount(), n => n.type === live.CapacitorPlacementResults).props.selectedId, other);
assert.ok(statuses.some(s => s.includes("completed")));
console.log("Capacitor placement panel real-result admission, plots, selection, ratings, stale-response and recovery tests passed.");
