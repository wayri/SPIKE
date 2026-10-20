// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { importTestTypescript } from "./import-test-typescript.mjs";
const model = await importTestTypescript("fieldVolumeModel");
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
new Function("require", "module", "exports", compiled)(name => name === "react" ? hooks : model, module, module.exports);
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
state = render("project-b"); state = render("project-b"); assert.equal(state.view, null, "project change removes stale field geometry");
effects.forEach(effect => effect?.cleanup?.()); const count = presented;
showFieldInMainViewport(fixture); assert.equal(presented, count, "unmount removes result route listener");
console.log("main field viewport: source admission, event route, project scope, retained hide/show and frame deduplication passed");
