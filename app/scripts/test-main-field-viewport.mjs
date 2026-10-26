// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";
const model = await importTestTypescript("fieldVolumeModel");
const streams = await importTestTypescript("fieldStreamPresentation");
const composite = await importTestTypescript("fieldCompositePresentation");
const source = readFileSync(new URL("../src/mainFieldViewport.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
// Small hook scheduler: exercises retained state and event admission without a DOM renderer.
let slots = [], cursor = 0, effects = [], pending = [];
const hooks = {
  useState(initial) { const i = cursor++; if (!(i in slots)) slots[i] = initial; return [slots[i], next => { slots[i] = typeof next === "function" ? next(slots[i]) : next; }]; },
  useRef(initial) { const i = cursor++; return slots[i] ??= { current: initial }; },
  useCallback(fn, deps) { const i = cursor++; return slots[i] ??= fn; },
  useEffect(fn, deps) { const i = cursor++; const old = effects[i]; if (!old || deps.some((d,j) => d !== old.deps[j])) pending.push(() => { old?.cleanup?.(); effects[i] = { deps, cleanup: fn() }; }); },
};
globalThis.window = new EventTarget();
globalThis.CustomEvent = class extends Event { constructor(name, options) { super(name); this.detail = options.detail; } };
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => name === "react" ? hooks : name === "./fieldStreamPresentation" ? streams : name === "./fieldCompositePresentation" ? composite : model, module, module.exports);
const { useMainFieldViewport, showFieldInMainViewport } = module.exports;
let presented = 0, errors = [];
function render(scope = "project-a") { cursor = 0; const result = useMainFieldViewport(scope, () => presented++, message => errors.push(message)); pending.splice(0).forEach(f => f()); return result; }
let state = render(); state = render(); assert.equal(state.view, null);
const fixture = JSON.parse(readFileSync(new URL("../../examples/field_visualization/illustrative-volume.json", import.meta.url)));
showFieldInMainViewport(fixture); state = render();
assert.equal(presented, 1); assert.equal(state.view.visible, true);
assert.notEqual(state.view.data, fixture, "admission owns a defensive copy");
state.options({ frame: 2, opacity: .4 }); state = render(); const retained = state.view;
state.options({ frame: 2 }); state = render(); assert.equal(state.view, retained, "unchanged RAF frame does not rebuild GPU geometry");
state.visible(false); state = render(); assert.equal(state.view.options.frame, 2);
state.visible(true); state = render(); assert.deepEqual(state.view.options, retained.options, "hide/show retains controls and frame");
const before = state.view; showFieldInMainViewport({ ...fixture, frames: [] }); state = render();
assert.equal(errors.length, 1); assert.equal(state.view, before, "invalid import preserves previous layer");
state.present(); state = render(); assert.equal(state.view, before, "reopening controls retains layer");
const secondary = { ...fixture, id: "solid-samples", quantities: [{ id: "temperature_k", label: "Solid temperature", unit: "K" }],
  frames: fixture.frames.map(frame => ({ timeS: frame.timeS, scalars: { temperature_k: fixture.cells.centers.map(() => 300) } })) };
const combined = { contract: "spike/field-composite-view/v1", registration: "shared-source-coordinates", primary: fixture, secondary };
showFieldInMainViewport(combined); state = render();
assert.equal(state.view.secondary.options.quantity, "temperature_k");
assert.equal(state.view.options.contextOpacity, .15, "combined result ghosts obstructing CAD context by default");
assert.equal(state.view.secondary.options.opacity, 1, "solid samples remain opaque");
assert.equal(state.view.secondary.options.pointSize, 9, "solid samples remain readable without claiming a surface");
assert.equal(state.view.secondary.options.mode, secondary.cells.sizes ? "voxels" : "points");
state.options({ frame: 1, quantity: fixture.quantities[0].id }); state = render();
assert.equal(state.view.secondary.options.frame, 1, "shared playback advances independently sourced saved samples");
assert.equal(state.view.secondary.options.quantity, "temperature_k", "primary quantity does not replace solid temperature");
state.options({ pointSize: 12 }); state = render(); assert.equal(state.view.secondary.options.pointSize, 12);
const acceptedComposite = state.view;
showFieldInMainViewport({ ...combined, secondary: { ...secondary, frames: secondary.frames.map((f, i) => ({ ...f, timeS: f.timeS + .00001 })) } }); state = render();
assert.equal(state.view, acceptedComposite, "mismatched times preserve the admitted composite");
assert.match(errors.at(-1), /exactly matching saved timestamps/);
assert.throws(() => composite.admitFieldPresentation({ ...combined, registration: undefined }), /registration/);
assert.throws(() => composite.admitFieldPresentation({ ...combined, secondary: { ...secondary, lengthUnit: secondary.lengthUnit === "mm" ? "m" : "mm" } }), /coordinate units/);
assert.equal(composite.fieldPresentationEnvelope(state.view).secondary.id, "solid-samples", "export preserves the separate dataset");
state = render("project-b"); state = render("project-b"); assert.equal(state.view, null, "project change removes stale field geometry");
effects.forEach(effect => effect?.cleanup?.()); const count = presented;
showFieldInMainViewport(fixture); assert.equal(presented, count, "unmount removes result route listener");
console.log("main field viewport: source admission, event route, project scope, retained hide/show and frame deduplication passed");
