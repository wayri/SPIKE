// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import React from "react";
import ts from "typescript";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { importTestTypescript } from "./import-test-typescript.mjs";
const require = createRequire(import.meta.url);
const model = await importTestTypescript("assemblyThermalBodyPowerModel");
const request = { assembly: { boards: [{ id: "a", name: "Board A" }], parts: [] } };
const problem = { heat_sources: [] };
const handoff = { request_digest: "a".repeat(64), source_traceability: [{ occurrence_id: "a", cell_map: { one: "global-one" }, volume_m3: 1e-9 }] };
assert.equal(model.bodyPowerParameters(request, problem, handoff, "a", "0.5", false).power_w, .5);
for (const value of ["", " ", "NaN", "Infinity", "-1"]) assert.throws(() => model.bodyPowerParameters(request, problem, handoff, "a", value, false));
assert.throws(() => model.bodyPowerParameters(request, problem, handoff, "missing", "1", false));
assert.throws(() => model.bodyPowerParameters(request, { heat_sources: [{ occurrence_id: "a" }] }, handoff, "a", "1", false), /replacement/);
let slots = [], cursor = 0, effects = [], requests = [], applied = [], busyChanges = [], response, stateWrites = 0;
const hooks = {
  useState(initial) { const i = cursor++; slots[i] ??= { value: initial }; return [slots[i].value, value => { stateWrites++; slots[i].value = value; }]; },
  useRef(initial) { const i = cursor++; slots[i] ??= { current: initial }; return slots[i]; },
  useEffect(fn, deps) { const i = cursor++; if (!slots[i] || deps.some((value, j) => value !== slots[i].deps[j])) { const previous = slots[i]; slots[i] = { deps }; effects.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); }); } },
};
const code = ts.transpileModule(readFileSync(new URL("../src/AssemblyThermalBodyPower.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", code)(name => name === "react" ? hooks : name === "./assemblyThermalBodyPowerModel" ? model
  : name === "./workerBridge" ? { runLocalWorker: async operation => { requests.push(operation); return typeof response === "function" ? response() : response; } }
    : require(name), module, module.exports);
const props = { request, problem, handoff, disabled: false, onBusyChange: value => busyChanges.push(value), onApply: value => applied.push(value) };
let tree;
function render() { cursor = 0; tree = module.exports.default(props); const pending = effects; effects = []; pending.forEach(fn => fn()); }
const nodes = value => !value || typeof value !== "object" ? [] : [value, ...React.Children.toArray(value.props?.children).flatMap(nodes)];
const input = label => nodes(tree).find(node => node.props?.["aria-label"] === label);
const button = () => nodes(tree).find(node => node.type === "button");
async function settle() { for (let i = 0; i < 3; i++) { await new Promise(resolve => setImmediate(resolve)); render(); } }
function draft() { input("Powered occurrence").props.onChange({ target: { value: "a" } }); render(); input("Body dissipated power (W)").props.onChange({ target: { value: "2" } }); render(); nodes(tree).filter(node => node.props?.type === "checkbox").at(-1).props.onChange({ target: { checked: true } }); render(); }
render(); render(); assert.equal(button().props.disabled, true); draft(); assert.equal(button().props.disabled, false);
response = { ok: false, error: "Mesh changed" }; button().props.onClick(); await settle();
assert.equal(applied.length, 0); assert.ok(nodes(tree).some(node => node.props?.role === "alert" && /Mesh changed/.test(node.props.children)));
response = { ok: true, result: { request_digest: "stale", problem: { heat_sources: [] } } }; button().props.onClick(); await settle();
assert.equal(applied.length, 0, "worker response must match the reviewed mesh digest");
response = { ok: true, result: { request_digest: handoff.request_digest, problem: { heat_sources: [{ occurrence_id: "a", cell_id: "one", heat_source_w_m3: 2e9 }] } } };
button().props.onClick(); await settle(); assert.equal(applied.length, 1); assert.equal(requests.at(-1).params.power_w, 2); assert.equal(busyChanges.at(-1), false);
draft(); let finish; response = () => new Promise(resolve => { finish = resolve; }); button().props.onClick(); await settle();
props.request = { ...request, revision: "changed" }; render(); render();
assert.equal(busyChanges.at(-1), false, "geometry invalidation releases this component's busy ownership immediately");
busyChanges.push(true); // A newer parent operation now owns the busy indicator.
let writesBeforeCompletion = stateWrites, busyEventsBeforeCompletion = busyChanges.length;
finish({ ok: true, result: { request_digest: handoff.request_digest, problem: { heat_sources: [] } } }); await settle();
assert.equal(applied.length, 1, "changed geometry retires an in-flight source edit"); assert.equal(button().props.disabled, true);
assert.equal(stateWrites, writesBeforeCompletion, "stale completion writes no component state");
assert.equal(busyChanges.length, busyEventsBeforeCompletion, "stale completion cannot clear a newer parent's busy state");
draft(); response = () => new Promise(resolve => { finish = resolve; }); button().props.onClick(); await settle();
const releasesBeforeUnmount = busyChanges.filter(value => value === false).length;
for (const slot of slots) slot.cleanup?.();
assert.equal(busyChanges.filter(value => value === false).length, releasesBeforeUnmount + 1, "unmount releases owned busy exactly once");
busyChanges.push(true);
writesBeforeCompletion = stateWrites; busyEventsBeforeCompletion = busyChanges.length;
finish({ ok: false, error: "Late worker failure" });
for (let i = 0; i < 3; i++) await new Promise(resolve => setImmediate(resolve));
assert.equal(stateWrites, writesBeforeCompletion, "unmounted completion writes no component state");
assert.equal(busyChanges.length, busyEventsBeforeCompletion, "unmounted completion does not release busy a second time");
assert.equal(applied.length, 1);
console.log("Body power input, worker failures, review, stale responses, and busy ownership lifecycle checks passed.");
