// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import React from "react";
import ts from "typescript";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
let slots = [], cursor = 0, effects = [], tree, outputs = [], calls = [];
const hooks = {
  useState(initial) { const i = cursor++; slots[i] ??= { value: initial }; return [slots[i].value, next => { slots[i].value = typeof next === "function" ? next(slots[i].value) : next; }]; },
  useRef(initial) { const i = cursor++; slots[i] ??= { current: initial }; return slots[i]; },
  useEffect(fn, deps) { const i = cursor++; if (!slots[i] || deps.some((v,j) => v !== slots[i].deps[j])) { const old = slots[i]; slots[i] = { deps }; effects.push(() => { old?.cleanup?.(); slots[i].cleanup = fn(); }); } },
};
let backend = async () => ({ ok: true, result: { data: { job: { solids: [{ id: "pad" }] }, design_binding: { digest_sha256: "a".repeat(64) } } } });
const code = ts.transpileModule(readFileSync(new URL("../src/GmshPcbMeshSetup.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", code)(name => name === "react" ? hooks : name === "./workerBridge" ? { runLocalWorker: operation => { calls.push(operation); return backend(operation); } } : name.endsWith(".css") ? {} : require(name), module, module.exports);
const props = { design: { contract: "spike/v1", design_id: "board" }, onParameters: value => outputs.push(value) };
function render() { cursor = 0; tree = module.exports.default(props); const queued = effects; effects = []; queued.forEach(fn => fn()); }
function nodes(value) { return !value || typeof value !== "object" ? [] : [value, ...React.Children.toArray(value.props?.children).flatMap(nodes)]; }
const node = type => nodes(tree).find(n => n.type === type);
const settle = async () => { for (let i=0;i<4;i++) { await new Promise(resolve => setImmediate(resolve)); render(); } };
render();
node("textarea").props.onChange({ target: { value: '{"contract":"spike/pcb-volume-mesh-request/v1"}' } }); render();
await node("button").props.onClick(); await settle();
assert.equal(calls[0].params.contribution_id, "gmsh-prepare-pcb");
assert.deepEqual(calls[0].params.context.design, props.design);
assert.equal(outputs.at(-1).expected_design_sha256, "a".repeat(64), "binding comes from worker canonicalization");
node("textarea").props.onChange({ target: { value: "malformed" } }); render();
assert.equal(outputs.at(-1), null, "edits immediately retire generation parameters");
await node("button").props.onClick(); await settle();
assert.equal(calls.length, 1, "invalid JSON does not launch an extension");
let resolve;
backend = () => new Promise(done => { resolve = done; });
node("textarea").props.onChange({ target: { value: '{"contract":"spike/pcb-volume-mesh-request/v1"}' } }); render();
node("button").props.onClick(); render();
props.design = { ...props.design, design_id: "other-board" }; render();
resolve({ ok: true, result: { data: { job: { solids: [] }, design_binding: { digest_sha256: "b".repeat(64) } } } });
await settle();
assert.equal(outputs.at(-1), null, "late preparation from the previous board cannot become executable");
console.log("Gmsh PCB preparation, worker-owned binding, edit invalidation and late-response guards passed");
