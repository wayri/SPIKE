// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import * as model from "../src/shortcutCatalog.ts";
const states = [], refs = [], effects = [];
let index = 0;
const react = {
  useState(initial) { const i = index++; if (!(i in states)) states[i] = initial; return [states[i], value => { states[i] = typeof value === "function" ? value(states[i]) : value; }]; },
  useRef(initial) { const i = index++; return refs[i] ??= { current: initial }; },
  useEffect(fn) { const i = index++; if (!effects[i]) effects[i] = fn; },
};
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: "fragment" };
const source = readFileSync(new URL("../src/ShortcutManager.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => name === "react" ? react : name === "react/jsx-runtime" ? jsx : name === "./shortcutCatalog" ? model : {}, module, module.exports);
let shortcuts = { ...model.defaultShortcuts }, assignments = [], presets = [], resets = 0, closes = 0;
const props = { shortcuts, onAssign(action, key) { assignments.push([action, key]); const conflict = Object.keys(shortcuts).find(other => other !== action && key && shortcuts[other] === key); if (conflict) shortcuts[conflict] = shortcuts[action]; shortcuts[action] = key; }, onPreset(name) { presets.push(name); }, onReset() { resets++; }, onClose() { closes++; } };
const render = () => { index = 0; return module.exports.default(props); };
const nodes = tree => !tree || typeof tree !== "object" ? [] : [tree, ...[tree.props?.children].flat(Infinity).flatMap(nodes)];
const named = (tree, label) => nodes(tree).find(node => node.props?.["aria-label"] === label);
const button = (tree, label) => nodes(tree).find(node => node.type === "button" && node.props.children === label);
let prevented = 0, stopped = 0;
const key = (key, flags = {}) => ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false, nativeEvent: {}, preventDefault() { prevented++; }, stopPropagation() { stopped++; }, ...flags });
let tree = render();
named(tree, "Assign Pan mode").props.onClick(); tree = render();
tree.props.onKeyDown(key("p", { ctrlKey: true, shiftKey: true })); tree = render();
assert.equal(assignments.length, 0, "conflicts require confirmation");
assert.ok(button(tree, "Swap bindings"));
button(tree, "Swap bindings").props.onClick(); tree = render();
assert.deepEqual(assignments.pop(), ["panMode", "Ctrl+Shift+P"]);
assert.equal(shortcuts.openPiSetup, "P", "confirmed assignment swaps rather than duplicates");
named(tree, "Assign Pan mode").props.onClick(); tree = render();
tree.props.onKeyDown(key("k", { ctrlKey: true })); tree = render();
assert.equal(assignments.length, 0, "reserved key cannot mutate");
assert.ok(nodes(tree).some(node => node.props?.role === "status" && String(node.props.children).includes("reserved")));
tree.props.onKeyDown(key("Shift")); assert.equal(assignments.length, 0);
tree.props.onKeyDown(key("j", { altKey: true, repeat: true })); assert.equal(assignments.length, 0);
tree.props.onKeyDown(key("j", { altKey: true })); tree = render();
assert.deepEqual(assignments.pop(), ["panMode", "Alt+J"]);
named(tree, "Clear Pan mode").props.onClick(); tree = render(); assert.deepEqual(assignments.pop(), ["panMode", ""]);
assert.equal(named(tree, "Clear Pan mode").props.disabled, true);
named(tree, "Assign Pan mode").props.onClick(); tree = render(); tree.props.onKeyDown(key("Delete")); tree = render(); assert.deepEqual(assignments.pop(), ["panMode", ""]);
named(tree, "Assign Pan mode").props.onClick(); tree = render(); tree.props.onKeyDown(key("Escape")); tree = render(); assert.equal(closes, 0);
tree.props.onKeyDown(key("Escape")); assert.equal(closes, 1);
button(tree, "KiCad preset").props.onClick(); button(tree, "SPIKE preset").props.onClick(); button(tree, "Reset defaults").props.onClick(); assert.deepEqual(presets, ["kicad", "spike"]); assert.equal(resets, 1);
nodes(tree).find(node => node.type === "input").props.onChange({ target: { value: "no such action 12345" } }); tree = render(); assert.ok(nodes(tree).some(node => node.type === "p" && node.props.children === "No matching shortcuts."));
assert.ok(prevented > 0 && stopped > 0, "capture prevents viewport keyboard dispatch");
console.log("shortcut manager capture, conflicts, reserved keys, clearing and search: passed");
