// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

let effect, refIndex = 0;
const refs = [];
const source = readFileSync(new URL("../src/modalFocusScope.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", code)(name => name === "react" ? {
  useRef(initial) { return refs[refIndex++] ??= { current: initial }; }, useEffect(callback) { effect = callback; },
} : {} , module, module.exports);

const body = {}, prior = { isConnected: true, focus() { document.activeElement = this; } };
const first = { focus() { document.activeElement = this; }, getAttribute() { return null; }, closest() { return null; }, getClientRects() { return [{}]; } };
const last = { ...first };
const hidden = { ...first, getClientRects() { return []; } };
const hiddenInput = { ...first, getAttribute(name) { return name === "type" ? "hidden" : null; } };
const hiddenParent = { ...first, closest() { return {}; } };
const disabled = { ...first, matches() { return true; } };
const listeners = new Map();
const scope = {
  tabIndex: 0, attributes: {}, setAttribute(key, value) { this.attributes[key] = value; },
  querySelector(selector) { return selector === "[data-modal-initial-focus]" ? first : null; }, querySelectorAll() { return [hiddenInput, hiddenParent, disabled, first, last, hidden]; },
  contains(item) { return item === first || item === last; }, focus() { document.activeElement = this; },
  addEventListener(type, handler) { listeners.set(type, handler); }, removeEventListener(type) { listeners.delete(type); },
};
globalThis.document = { body, activeElement: prior, querySelector: () => scope };
globalThis.requestAnimationFrame = callback => { callback(); return 1; }; globalThis.cancelAnimationFrame = () => {};
let closed = 0;
refIndex = 0; module.exports.useModalFocusScope(() => { closed++; }, false, ".fixture", "Fixture modal");
const cleanup = effect();
assert.equal(document.activeElement, first, "opening focuses the designated initial control");
assert.deepEqual(scope.attributes, { role: "dialog", "aria-modal": "true", "aria-label": "Fixture modal" });
document.activeElement = last; let prevented = 0;
listeners.get("keydown")({ key: "Tab", shiftKey: false, preventDefault() { prevented++; }, stopPropagation() {} });
assert.equal(document.activeElement, first, "Tab wraps within a selector-bound modal");
listeners.get("keydown")({ key: "Escape", shiftKey: false, preventDefault() { prevented++; }, stopPropagation() {} });
assert.equal(closed, 1, "Escape closes an allowed modal");
document.activeElement = first; cleanup();
assert.equal(document.activeElement, prior, "closing restores focus to the invoking control");

refs.length = 0; refIndex = 0; effect = undefined; closed = 0; document.activeElement = prior;
const locked = module.exports.useModalFocusScope(() => { closed++; }, true);
refs[0].current = scope; const lockedCleanup = effect();
locked.onKeyDown({ key: "Escape", shiftKey: false, preventDefault() { prevented++; }, stopPropagation() {} });
assert.equal(closed, 0, "Escape is consumed while modal closure is disabled");
const nested = { isConnected: true, focus() {} }; document.activeElement = nested;
lockedCleanup();
assert.equal(document.activeElement, nested, "cleanup does not steal focus already moved into a routed or nested modal");
assert.ok(prevented >= 3);
console.log("Modal focus scope initial focus, Tab containment, Escape gating, restoration and nested focus checks passed.");
