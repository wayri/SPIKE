// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import React from "react";
import ts from "typescript";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { webcrypto } from "node:crypto";
globalThis.crypto ??= webcrypto;
const require = createRequire(import.meta.url);
const nodes = node => !node || typeof node !== "object" ? [] : [node, ...React.Children.toArray(node.props?.children).flatMap(nodes)];
const text = node => typeof node === "string" || typeof node === "number" ? String(node) : React.Children.toArray(node?.props?.children).map(text).join("");
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

function mount(name, initialProps, worker) {
  const slots = []; let cursor = 0, effects = [], tree, props = initialProps, mounted = true, lateWrites = 0;
  const hooks = {
    useState(initial) { const i = cursor++; slots[i] ??= { value: initial }; return [slots[i].value, next => { if (!mounted) lateWrites++; slots[i].value = typeof next === "function" ? next(slots[i].value) : next; }]; },
    useRef(initial) { const i = cursor++; slots[i] ??= { current: initial }; return slots[i]; },
    useEffect(fn, deps) { const i = cursor++; if (!slots[i] || deps.some((value, j) => value !== slots[i].deps[j])) {
      const previous = slots[i]; slots[i] = { deps }; effects.push(() => { previous?.cleanup?.(); slots[i].cleanup = fn(); });
    } },
  };
  const modules = new Map();
  const load = name => {
    if (modules.has(name)) return modules.get(name).exports;
    const url = ["tsx", "ts"].map(extension => new URL(`../src/${name}.${extension}`, import.meta.url)).find(existsSync);
    assert.ok(url, `Local workflow module ${name} exists`);
    const source = readFileSync(url, "utf8");
    const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
    const module = { exports: {} }; modules.set(name, module);
    new Function("require", "module", "exports", code)(id => id === "react" ? hooks : id === "./workerBridge" ? { runLocalWorker: worker, runNativeProjectWorker: worker } : id === "./ThermalComponentPromotion" ? { default: () => null } : id.endsWith(".css") ? {} : id.startsWith("./") ? load(id.slice(2)) : require(id), module, module.exports);
    return module.exports;
  };
  const component = load(name).default;
  function render(nextProps = props) { props = nextProps; cursor = 0; tree = component(props); const pending = effects; effects = []; pending.forEach(fn => fn()); }
  function control(label, type) { const owner = nodes(tree).find(n => n.type === "label" && text(n).trimStart().startsWith(label)); const result = nodes(owner).find(n => n.type === type); assert.ok(result, `Control ${label}`); return result; }
  const api = {
    render, get props() { return props; }, get tree() { return tree; }, get lateWrites() { return lateWrites; },
    control, button(label) { const result = nodes(tree).find(n => n.type === "button" && text(n) === label); assert.ok(result, `Button ${label}`); return result; },
    change(label, type, value) { control(label, type).props.onChange({ target: { value, checked: value } }); render(); },
    async settle() { for (let i = 0; i < 5; i++) { await new Promise(resolve => setImmediate(resolve)); if (mounted) render(); } },
    unmount() { mounted = false; for (const slot of slots) slot?.cleanup?.(); },
  };
  render(); render(); render(); return api;
}

const request = { assembly: { thermal_contacts: [{ id: "link-a", endpoint_a: "board", endpoint_b: "case", thermal_resistance_k_per_w: 4 }] }, bodies: [] };
const problem = { boundaries: [], contacts: [] }, linked = { ...problem, contacts: [{ id: "prepared" }] };
const proposals = [
  { status: "ready", contact_id: "link-a", endpoints: ["board", "case"], face_pair_count: 2, contact_area_mm2: 4, thermal_resistance_k_per_w: 4 },
  { status: "needs_resistance", contact_id: "unassigned", endpoints: ["case", "cover"], reason: "Review resistance first" },
  { status: "ready", contact_id: "link-b", endpoints: ["case", "sink"], face_pair_count: 1, contact_area_mm2: 2, thermal_resistance_k_per_w: 3 },
];
let calls = [], applied = [], answer = async operation => ({ ok: true, result: operation.method === "discover_assembly_thermal_links" ? { proposals } : { problem: linked, face_pair_count: 2, contact_area_mm2: 4 } });
const worker = async operation => { calls.push(operation); return answer(operation); };
const contacts = mount("AssemblyThermalContacts", { request, problem, disabled: false, onApply: p => applied.push(p) }, worker);
assert.equal(contacts.control("Total thermal resistance", "input").props.value, "4");
contacts.button("Discover thermal interfaces").props.onClick(); await contacts.settle();
assert.deepEqual(calls.at(-1), { method: "discover_assembly_thermal_links", params: { request, problem } });
let checkboxes = nodes(contacts.tree).filter(n => n.type === "input" && n.props.type === "checkbox");
assert.deepEqual(checkboxes.map(n => n.props.disabled), [false, true, false], "only ready proposals are selectable");
assert.equal(contacts.button("Autolink selected retained contacts").props.disabled, true);
checkboxes[0].props.onChange({ target: { checked: true } }); contacts.render();
checkboxes = nodes(contacts.tree).filter(n => n.type === "input" && n.props.type === "checkbox");
checkboxes[2].props.onChange({ target: { checked: true } }); contacts.render();
contacts.button("Autolink selected retained contacts").props.onClick(); await contacts.settle();
assert.deepEqual(calls.at(-1), { method: "autolink_assembly_thermal_contacts", params: { request, problem, contact_ids: ["link-a", "link-b"] } });
assert.strictEqual(applied.at(-1), linked);
for (const invalid of ["", "0", "-1", "NaN"]) { contacts.change("Total thermal resistance", "input", invalid); assert.equal(contacts.button("Prepare thermal link").props.disabled, true); }
contacts.change("Total thermal resistance", "input", "9");
contacts.button("Prepare thermal link").props.onClick(); await contacts.settle();
assert.deepEqual(calls.at(-1), { method: "prepare_assembly_thermal_contact_model", params: { request, problem, contact_id: "link-a", thermal_resistance_k_per_w: 9 } });
assert.match(text(contacts.tree), /2 matched faces.*4 mm².*9 K\/W/);
answer = async () => ({ ok: true, result: { problem: [] } });
const beforeInvalid = applied.length; contacts.button("Prepare thermal link").props.onClick(); await contacts.settle();
assert.equal(applied.length, beforeInvalid); assert.match(text(contacts.tree), /invalid thermal problem/);
const stale = deferred(); answer = () => stale.promise;
contacts.button("Discover thermal interfaces").props.onClick(); contacts.render({ ...contacts.props, request: { ...request } });
stale.resolve({ ok: true, result: { proposals } }); await contacts.settle();
assert.equal(nodes(contacts.tree).filter(n => n.type === "input" && n.props.type === "checkbox").length, 0, "changed request withholds stale interface proposals");
const abandoned = deferred(); answer = () => abandoned.promise;
contacts.button("Prepare thermal link").props.onClick(); const beforeAbandon = applied.length; contacts.unmount();
abandoned.resolve({ ok: true, result: { problem: linked } }); await contacts.settle();
assert.equal(applied.length, beforeAbandon); assert.equal(contacts.lateWrites, 0);

const components = [{ board_occurrence_id: "board-a", component_id: "component-u1", reference: "U1", placement: { x_mm: 10 },
  models: [{ model_id: "package-step", status: "ready" }, { model_id: "missing-step", status: "missing", reason: "STEP asset is absent" }] },
  { board_occurrence_id: "board-a", component_id: "component-r1", reference: "R1", models: [] }];
let updated = 0, busy = []; calls = []; answer = async () => ({ ok: true, result: {} });
const promotion = mount("ThermalComponentPromotion", { components, projectPath: "design.spike", manifestDigest: "digest-a", disabled: false,
  onBusyChange: value => busy.push(value), onUpdated: async () => { updated++; } }, worker);
const retain = () => promotion.button("Retain component for thermal meshing");
assert.equal(retain().props.disabled, true);
promotion.change("Board occurrence and component", "select", JSON.stringify(["board-a", "component-u1"]));
const options = nodes(promotion.control("Authoritative STEP model", "select")).filter(n => n.type === "option");
assert.equal(options.find(n => n.props.value === "missing-step").props.disabled, true);
promotion.change("Authoritative STEP model", "select", "missing-step");
assert.equal(retain().props.disabled, true);
promotion.change("Authoritative STEP model", "select", "package-step");
promotion.change("Thermal conductivity", "input", "42");
promotion.change("Material property source", "input", "Reviewed package datasheet");
assert.equal(retain().props.disabled, true, "material values without placement/material review cannot be saved");
const transform = [1,0,0,10,0,1,0,20,0,0,1,3,0,0,0,1];
promotion.change("Reviewed component-to-board transform", "textarea", JSON.stringify(transform));
promotion.change("I reviewed model", "input", true);
assert.equal(retain().props.disabled, false);
promotion.change("Reviewed component-to-board transform", "textarea", "[1,2]");
promotion.change("I reviewed model", "input", true);
assert.equal(retain().props.disabled, true, "malformed transform cannot be submitted even when reviewed");
promotion.change("Reviewed component-to-board transform", "textarea", JSON.stringify(transform));
assert.equal(promotion.control("I reviewed model", "input").props.checked, false, "transform edits invalidate review");
promotion.change("I reviewed model", "input", true);
retain().props.onClick(); await promotion.settle();
const operation = calls.at(-1), material = operation.params.materials[0];
assert.equal(operation.method, "promote_thermal_components_in_project");
assert.equal(operation.params.project_path, "design.spike"); assert.equal(operation.params.expected_manifest_payload_sha256, "digest-a");
assert.match(material.id, /^component-material-/);
assert.deepEqual(material, { id: material.id, thermal_conductivity_w_mk: 42, provenance: "Reviewed package datasheet" });
assert.deepEqual(operation.params.selections, [{ board_occurrence_id: "board-a", component_id: "component-u1", model_id: "package-step",
  component_to_board_transform_mm: transform, material_id: material.id, placement_reviewed: true }]);
assert.equal(updated, 1); assert.equal(busy.at(-1), false);
promotion.change("Thermal conductivity", "input", "43"); assert.equal(retain().props.disabled, true, "material edits invalidate review");
promotion.change("I reviewed model", "input", true);
const oldProject = deferred(); answer = () => oldProject.promise;
retain().props.onClick(); promotion.render({ ...promotion.props, manifestDigest: "digest-b" }); promotion.render();
const busyBeforeStale = busy.length;
oldProject.resolve({ ok: true, result: {} }); await promotion.settle();
assert.equal(updated, 1, "a prior manifest's response cannot refresh the current project");
assert.equal(busy.length, busyBeforeStale, "stale completion cannot change current lifecycle busy ownership");
promotion.change("Board occurrence and component", "select", JSON.stringify(["board-a", "component-r1"]));
assert.match(text(promotion.tree), /Retain an authoritative STEP model/); assert.equal(retain().props.disabled, true);
promotion.change("Board occurrence and component", "select", JSON.stringify(["board-a", "component-u1"]));
promotion.change("Authoritative STEP model", "select", "package-step"); promotion.change("I reviewed model", "input", true);
const unmounted = deferred(); answer = () => unmounted.promise;
retain().props.onClick(); promotion.unmount(); const busyAtUnmount = busy.length;
unmounted.resolve({ ok: true, result: {} }); await promotion.settle();
assert.equal(updated, 1); assert.equal(busy.length, busyAtUnmount, "unmounted completion cannot notify the old parent"); assert.equal(promotion.lateWrites, 0);
console.log("Thermal contact discovery/selection, explicit resistance, component STEP/material/placement review, worker requests and stale/unmount guards passed.");

const coverageCalls = [];
const coverage = mount("AssemblyThermalMeshSetup", { projectPath: "thermal.spike", manifestDigest: "coverage-a", disabled: false,
  onBusyChange() {}, onPrepared() {}, onProjectUpdated() {} }, async operation => {
  coverageCalls.push(operation);
  return { ok: true, result: { boards: [], parts: [{ id: "part-u1", name: "U1", model_id: "u1-step" }], components: [
    { board_occurrence_id: "board-a", component_id: "u1", reference: "U1", promoted_part_ids: ["part-u1"], models: [{ status: "ready" }] },
    { board_occurrence_id: "board-a", component_id: "u2", reference: "U2", promoted_part_ids: [], models: [{ status: "ready" }] },
    { board_occurrence_id: "board-b", component_id: "u1", reference: "U1", promoted_part_ids: ["missing-part"], models: [{ status: "blocked" }] },
  ] } };
});
coverage.button("Read retained geometry and layers").props.onClick(); await coverage.settle();
assert.equal(coverageCalls[0].method, "read_assembly_thermal_mesh_setup");
assert.match(text(coverage.tree), /3 component occurrences: 1 retained as physical thermal parts; 2 excluded from volume meshing/);
assert.match(text(coverage.tree), /1 excluded components have a retained STEP reference/);
assert.match(text(coverage.tree), /Excluded: board-a: U2, board-b: U1/);
assert.match(text(coverage.tree), /Closed-solid eligibility is checked during meshing/);
coverage.render({ ...coverage.props, manifestDigest: "coverage-b" }); coverage.render();
assert.doesNotMatch(text(coverage.tree), /3 component occurrences/, "old project inventory must not imply current part coverage");
console.log("Thermal volume component coverage, exact retained part identity and manifest reset passed.");

// A batch keeps independent occurrences/materials and discards drafts on manifest changes.
const batchComponents = [components[0], { ...components[0], board_occurrence_id: "board-b" }];
const batchCalls = [];
const batch = mount("ThermalComponentPromotion", { components: batchComponents, projectPath: "batch.spike", manifestDigest: "batch-a", disabled: false,
  onBusyChange() {}, onUpdated: async () => {} }, async operation => { batchCalls.push(operation); return { ok: true, result: {} }; });
for (const [boardId, wattsConductivity, z] of [["board-a", "11", 2], ["board-b", "22", 4]]) {
  batch.change("Board occurrence and component", "select", JSON.stringify([boardId, "component-u1"]));
  batch.change("Authoritative STEP model", "select", "package-step");
  batch.change("Reviewed component-to-board transform", "textarea", JSON.stringify([1,0,0,0,0,1,0,0,0,0,1,z,0,0,0,1]));
  batch.change("Thermal conductivity", "input", wattsConductivity);
  batch.change("Material property source", "input", `Reviewed ${boardId}`);
  batch.change("I reviewed model", "input", true);
  batch.button("Queue reviewed component").props.onClick(); batch.render();
  assert.equal(batch.control("I reviewed model", "input").props.checked, false);
}
assert.match(text(batch.tree), /2 reviewed components queued/);
batch.button("Retain reviewed component batch").props.onClick(); await batch.settle();
assert.equal(batchCalls.length, 1);
assert.deepEqual(batchCalls[0].params.selections.map(row => row.board_occurrence_id), ["board-a", "board-b"]);
assert.deepEqual(batchCalls[0].params.selections.map(row => row.component_to_board_transform_mm[11]), [2, 4]);
assert.deepEqual(batchCalls[0].params.materials.map(row => row.thermal_conductivity_w_mk), [11, 22]);
assert.notEqual(batchCalls[0].params.selections[0].material_id, batchCalls[0].params.selections[1].material_id);
batch.render({ ...batch.props, manifestDigest: "batch-b" }); batch.render();
assert.doesNotMatch(text(batch.tree), /reviewed components queued/);
console.log("Reviewed component batches preserve occurrence transforms/materials and clear on manifest changes.");
