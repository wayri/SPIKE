// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import React from "react";
import ts from "typescript";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const assembly = { boards: [{ id: "board-a" }], parts: [], extensions: { "spike.multiboard-studies": {
  pi: { request: { domain: "pi", circuit: "retained-explicit-circuit" } },
  si: { request: { domain: "si", circuit: "retained-explicit-ac-circuit" } },
} } };
const geometry = { assembly, domain: "thermal", bodies: [{ occurrence_id: "board-a" }] };
const problem = { boundaries: [], contacts: [], heat_sources: [] };
const request = { contract: "spike/multiboard-volume-electrothermal-request/v1", geometry,
  thermal_problem: problem, circuit: assembly.extensions["spike.multiboard-studies"].pi.request, loss_bindings: [{ element_id: "r1" }] };
const thermal = { contract: "spike/calculix-thermal-result/v1", field_result: { node_temperatures_k: [310] } };
const result = { contract: "spike/multiboard-volume-electrothermal-result/v1", thermal_engine: "calculix",
  thermal_geometry: geometry, thermal, electrical: { losses: [{ element_id: "r1", average_power_w: 2, temperature_k: 310, resistance_ohm: 5 }] },
  loss_balance: { thermal_imbalance_w: null }, history: [{ iteration: 2 }], request_digest: "result-a" };
const record = { request, result };
const handoff = { handoff_digest: "fixture-geometry", mesh: {} };
let slots = [], cursor = 0, effects = [], calls = [], dirtyStates = [], updated = 0;
const hooks = {
  useState(initial) { const i = cursor++; slots[i] ??= { value: typeof initial === "function" ? initial() : initial }; return [slots[i].value, next => { slots[i].value = typeof next === "function" ? next(slots[i].value) : next; }]; },
  useRef(initial) { const i = cursor++; slots[i] ??= { current: initial }; return slots[i]; },
  useEffect(fn, deps) { const i = cursor++; if (!slots[i] || deps.some((v, j) => v !== slots[i].deps[j])) { const previous = slots[i]; slots[i] = { deps }; effects.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); }); } },
};
let solve = async () => result;
const inventory = { resistors: [{ element_id: "r1", resistance_ohm: 5 }], occurrences: [{ occurrence_id: "board-a", cell_ids: ["cell-0", "cell-1"] }], assembly_digest: "fixture" };
let describe = async () => inventory;
let readState = "current";
const worker = async operation => {
  calls.push(operation);
  const { method, params } = operation;
  const answer = method === "read_volume_electrothermal_in_project" ? { state: readState, record, action: "Physical assembly changed." }
    : method === "prepare_assembly_field_handoff" ? handoff
      : method === "describe_volume_electrothermal_bindings" ? await describe()
      : method === "prepare_multiboard_volume_electrothermal" ? { status: "ready_to_run", handoff, resistors: [{ id: "r1" }] }
        : method === "run_multiboard_volume_electrothermal" ? await solve()
          : method === "verify_multiboard_volume_electrothermal_result" ? params.result
            : method === "save_volume_electrothermal_in_project" ? { manifest: { manifest_payload_sha256: "new" } } : null;
  return { ok: true, result: answer };
};
const source = readFileSync(new URL("../src/VolumeElectrothermalEditor.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", code)(name => name === "react" ? hooks
  : name === "./assemblyFieldStudyPresentation" ? { assertFieldAssembly: (candidate, current) => { if (JSON.stringify(candidate.assembly) !== JSON.stringify(current)) throw Error("ASSEMBLY_FIELD_STALE"); } }
    : name === "./workerBridge" ? { runLocalWorker: worker, runNativeProjectWorker: worker }
      : name === "./automaticWorkerQueue" ? { runSerializedAutomaticWorker: (work, current) => current() ? work() : Promise.resolve(undefined) }
        : name === "./AssemblyThermalVolumeViewer" ? { default: "volume-viewer" }
          : name === "./DataTable" ? { default: "data-table" } : name.endsWith(".css") ? {} : require(name), module, module.exports);
const props = { assembly, fieldRequest: geometry, fieldProblem: problem, projectPath: "current.spike", manifestDigest: "a".repeat(64), disabled: false,
  onUpdated: async () => { updated++; }, onStatus: () => {}, onDirtyChange: dirty => dirtyStates.push(dirty) };
let tree;
function render() { cursor = 0; tree = module.exports.default(props); const queued = effects; effects = []; queued.forEach(fn => fn()); }
async function settle() { for (let i = 0; i < 7; i++) { await new Promise(resolve => setImmediate(resolve)); render(); } }
function nodes(v) { return !v || typeof v !== "object" ? [] : [v, ...React.Children.toArray(v.props?.children).flatMap(nodes)]; }
const button = text => nodes(tree).find(n => n.type === "button" && n.props.children === text);
const editor = () => nodes(tree).find(n => n.type === "textarea");
const viewer = () => nodes(tree).find(n => n.type === "volume-viewer");
const solver = () => nodes(tree).find(n => n.type === "select" && n.props["aria-label"] === "Coupled thermal solver");
const idTables = () => nodes(tree).filter(n => n.type === "data-table" && String(n.props.label).startsWith("Available"));
render(); await settle();
assert.equal(calls[0].method, "read_volume_electrothermal_in_project");
assert.equal(calls[0].params.expected_manifest_payload_sha256, props.manifestDigest);
assert.deepEqual(viewer().props.result, thermal, "saved current project result loads without file selection");
assert.ok(nodes(tree).some(n => n.type === "p" && React.Children.toArray(n.props.children).includes("not reported")), "external balance is never displayed as zero");
button("Show resistor and volume IDs").props.onClick(); await settle();
assert.equal(calls.at(-1).method, "describe_volume_electrothermal_bindings");
assert.deepEqual(calls.at(-1).params, { geometry, circuit: request.circuit });
assert.equal(idTables().length, 2);
assert.ok(idTables().every(n => n.props.pageSize === 50), "ID tables have bounded pages");
solver().props.onChange({ target: { value: "calculix" } }); render();
assert.equal(JSON.parse(editor().props.value).thermal_engine, "calculix");
assert.equal(viewer(), undefined, "changing thermal solver retires saved temperatures");
assert.equal(button("Run coupled electrothermal").props.disabled, true);
assert.equal(idTables().length, 0);
button("Reset coupled draft").props.onClick(); render();
button("Copy current volumes and saved circuit").props.onClick(); render();
const seeded = JSON.parse(editor().props.value);
assert.deepEqual(seeded.loss_bindings, [], "no invented resistor mappings or temperature laws");
assert.deepEqual(seeded.circuit, assembly.extensions["spike.multiboard-studies"].pi.request);
assert.equal(viewer(), undefined, "new draft retires prior result");
assert.equal(dirtyStates.at(-1), true);
assert.equal(button("Run coupled electrothermal").props.disabled, true);
button("Show resistor and volume IDs").props.onClick(); await settle();
assert.equal(idTables().length, 2, "incomplete loss bindings can inspect IDs before successful prepare");
assert.equal(calls.filter(c => c.method === "prepare_multiboard_volume_electrothermal").length, 0);
button("Reset coupled draft").props.onClick(); render();
assert.deepEqual(viewer().props.result, thermal);
editor().props.onChange({ target: { value: "{" } }); render();
const beforeInvalid = calls.length;
button("Prepare coupled study").props.onClick(); await settle();
assert.equal(calls.length, beforeInvalid, "malformed JSON never reaches worker");
assert.ok(nodes(tree).some(n => n.props?.role === "alert"));
assert.equal(solver().props.disabled, true, "invalid JSON is not silently overwritten by solver selection");
editor().props.onChange({ target: { value: JSON.stringify(request) } }); render();
button("Prepare coupled study").props.onClick(); await settle();
assert.equal(button("Run coupled electrothermal").props.disabled, false);
solver().props.onChange({ target: { value: "calculix" } }); render();
assert.equal(button("Run coupled electrothermal").props.disabled, true, "solver change invalidates prepared case");
editor().props.onChange({ target: { value: JSON.stringify({ ...request, thermal_engine: "calculix", thermal_engine_options: { threads: 2 } }) } }); render();
solver().props.onChange({ target: { value: "internal" } }); render();
assert.equal("thermal_engine_options" in JSON.parse(editor().props.value), false, "switching internal removes external-only runner options");
solver().props.onChange({ target: { value: "calculix" } }); render();
button("Prepare coupled study").props.onClick(); await settle();
button("Run coupled electrothermal").props.onClick(); await settle();
assert.deepEqual(viewer().props.result, thermal);
assert.ok(calls.some(c => c.method === "verify_multiboard_volume_electrothermal_result"), "computed result is admitted before presentation");
button("Save coupled study").props.onClick(); await settle();
assert.equal(calls.at(-1).method, "save_volume_electrothermal_in_project");
assert.deepEqual(calls.at(-1).params.record.result, result);
assert.equal(updated, 1);
assert.equal(dirtyStates.at(-1), false);
let resolveSolve;
solve = () => new Promise(resolve => { resolveSolve = resolve; });
button("Run coupled electrothermal").props.onClick(); await settle();
assert.equal(editor().props.disabled, true);
props.manifestDigest = "b".repeat(64); render(); await settle();
resolveSolve({ ...result, request_digest: "late-result", thermal: { ...thermal, field_result: { node_temperatures_k: [999] } } });
await settle();
assert.deepEqual(viewer().props.result, thermal, "late output cannot overwrite another manifest");
readState = "stale";
button("Load saved coupled study").props.onClick(); await settle();
assert.equal(viewer(), undefined, "stale project result is withheld even if read response contains a record");
assert.ok(nodes(tree).some(n => n.props?.role === "alert" && String(n.props.children).includes("Physical assembly changed")));
let resolveIds;
describe = () => new Promise(resolve => { resolveIds = resolve; });
button("Show resistor and volume IDs").props.onClick(); await settle();
assert.deepEqual(calls.at(-1).params.circuit, assembly.extensions["spike.multiboard-studies"].pi.request, "empty draft inspects selected saved circuit");
props.manifestDigest = "c".repeat(64); render(); await settle();
resolveIds(inventory); await settle();
assert.equal(idTables().length, 0, "late ID inventory cannot overwrite a different project manifest");
props.fieldRequest = { ...geometry, assembly: { ...assembly, parts: [{ id: "package-a", extensions: {
  "spike.thermal-component": { contract: "spike/thermal-component-provenance/v1" },
} }] } };
render();
editor().props.onChange({ target: { value: JSON.stringify({ ...request, circuit: { ...request.circuit, part_models: [{ part_id: "package-a" }] } }) } }); render();
button("Rebind circuit draft to reviewed current assembly").props.onClick(); render();
assert.deepEqual(JSON.parse(editor().props.value).circuit.assembly, props.fieldRequest.assembly);
const packageCheckbox = () => nodes(tree).find(n => n.type === "input" && n.props.type === "checkbox");
packageCheckbox().props.onChange({ target: { checked: true } }); render();
assert.deepEqual(JSON.parse(editor().props.value).circuit.thermal_only_part_ids, ["package-a"]);
assert.deepEqual(JSON.parse(editor().props.value).circuit.part_models, [{ part_id: "package-a" }], "declaration never silently deletes circuit elements");
assert.equal(viewer(), undefined, "assembly/declaration edits retire solved temperatures");
assert.equal(button("Run coupled electrothermal").props.disabled, true);
packageCheckbox().props.onChange({ target: { checked: false } }); render();
assert.deepEqual(JSON.parse(editor().props.value).circuit.thermal_only_part_ids, []);
console.log("Volume electrothermal saved loading, solver choice, incomplete binding inspection, prepare/run/save and stale-response guards passed.");
