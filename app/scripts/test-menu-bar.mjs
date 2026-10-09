// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";

const require = createRequire(import.meta.url);
const effects = [], refs = [];
let refIndex = 0, closed = 0, open = false;
const listeners = new Map();
globalThis.document = {
  activeElement: null,
  addEventListener(type, listener) { listeners.set(type, listener); },
  removeEventListener(type, listener) { if (listeners.get(type) === listener) listeners.delete(type); },
};
globalThis.requestAnimationFrame = callback => { callback(); return 1; };
globalThis.KeyboardEvent = class { constructor(type, options) { Object.assign(this, { type }, options); } };
const focusLog = [];
const item = name => ({ name, disabled: false, focus() { document.activeElement = this; focusLog.push(name); } });
const first = item("first"), second = item("second"), third = item("third");
const trigger = { focus() { document.activeElement = this; focusLog.push("trigger"); } };
const dropdown = { querySelectorAll() { return [first, second, third]; }, contains(target) { return [first, second, third].includes(target); } };
const entry = { contains(target) { return target === this || target === trigger || target === dropdown; }, closest() { return null; } };

const source = readFileSync(new URL("../src/MenuBar.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", code)(name => {
  if (name === "react") return { ...React,
    createContext: () => ({ Provider: "provider" }), useContext: () => () => { closed++; open = false; }, useId: () => "file-menu",
    useRef: initial => refs[refIndex++] ?? (refs[refIndex - 1] = { current: initial }), useEffect: callback => effects.push(callback) };
  if (name.endsWith(".css")) return {};
  return require(name);
}, module, module.exports);
const { MenuButton, MenuItem } = module.exports;
const render = () => { refIndex = 0; return MenuButton({ label: "File", open, onClick: () => { open = !open; }, children: React.createElement("button") }); };

let tree = render(), triggerNode = tree.props.children[0];
refs[0].current = entry; refs[1].current = trigger; refs[2].current = dropdown;
assert.equal(triggerNode.props["aria-haspopup"], "menu");
assert.equal(triggerNode.props["aria-expanded"], false);
let prevented = 0, stopped = 0;
triggerNode.props.onKeyDown({ key: "ArrowDown", preventDefault() { prevented++; }, stopPropagation() { stopped++; } });
assert.equal(open, true, "ArrowDown opens a closed application menu");
tree = render(); triggerNode = tree.props.children[0]; const menuNode = tree.props.children[1];
const cleanup = effects.at(-1)();
assert.equal(document.activeElement, first, "keyboard opening focuses the first menu item");
assert.equal(menuNode.props.role, "menu");
assert.equal(triggerNode.props["aria-expanded"], true);
document.activeElement = second;
menuNode.props.onKeyDown({ key: "ArrowDown", preventDefault() { prevented++; }, stopPropagation() { stopped++; } });
assert.equal(document.activeElement, third, "ArrowDown advances through menu items");
menuNode.props.onKeyDown({ key: "Home", preventDefault() {}, stopPropagation() {} });
assert.equal(document.activeElement, first, "Home focuses the first menu item");
menuNode.props.onKeyDown({ key: "End", preventDefault() {}, stopPropagation() {} });
assert.equal(document.activeElement, third, "End focuses the last menu item");
menuNode.props.onKeyDown({ key: "Escape", preventDefault() {}, stopPropagation() {} });
assert.equal(open, false); assert.equal(document.activeElement, trigger, "Escape closes and restores trigger focus");
open = true; render(); effects.at(-1)();
listeners.get("pointerdown")({ target: {} });
assert.equal(open, false, "an outside pointer closes the open menu");
cleanup?.();
open = true; tree = render(); const activationCleanup = effects.at(-1)(); document.activeElement = first; open = false; activationCleanup();
assert.equal(document.activeElement, trigger, "closing after an in-place menu action restores trigger focus");
const menuItem = MenuItem({ icon: () => null, label: "Open", shortcut: "Ctrl+O", onClick() {} });
assert.equal(menuItem.props.type, "button"); assert.equal(menuItem.props.role, "menuitem");
assert.ok(prevented && stopped);
console.log("Menu bar keyboard navigation, semantics, focus restoration and outside dismissal checks passed.");
