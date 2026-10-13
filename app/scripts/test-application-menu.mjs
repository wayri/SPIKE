// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const effects = [], refs = [], states = []; let stateOverride;
const React = {
  createContext: value => ({ value }), useContext: context => context.value,
  useEffect: effect => { effects.push(effect); }, useLayoutEffect: effect => { effects.push(effect); },
  useId: () => "menu-test",
  useRef: value => ({ current: refs.length ? refs.shift() : value }),
  useState: initial => { const slot = { value: stateOverride === undefined ? initial : stateOverride }; states.push(slot); return [slot.value, next => { slot.value = typeof next === "function" ? next(slot.value) : next; }]; },
};
const jsx = (type, props, key) => ({ type, key, props: props ?? {} });
const source = readFileSync(new URL("../src/ApplicationMenu.tsx", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", code)(name => {
  if (name === "react") return React;
  if (name === "react/jsx-runtime") return { jsx, jsxs: jsx, Fragment: Symbol("Fragment") };
  if (name.endsWith(".css")) return {};
  throw new Error(`Unexpected import ${name}`);
}, module, module.exports);
const { MenuBar, MenuButton, MenuItem, MenuSubmenu } = module.exports;

let clicks = 0;
const icon = () => null;
let item = MenuItem({ icon, label: "Open", shortcut: "Ctrl+O", onClick: () => clicks++ });
assert.equal(item.props.role, "menuitem"); assert.equal(item.props.tabIndex, -1); item.props.onClick(); assert.equal(clicks, 1);
item = MenuItem({ icon, label: "Blocked", onClick: () => clicks++, disabled: true }); item.props.onClick(); assert.equal(clicks, 1); assert.equal(item.props["aria-disabled"], true);
const button = MenuButton({ label: "File", mnemonic: "F", open: false, onClick: () => clicks++, children: null });
const trigger = button.props.children[0]; assert.equal(trigger.props.role, "menuitem"); assert.equal(trigger.props["aria-haspopup"], "menu"); assert.equal(trigger.props["data-mnemonic"], "f");
const submenu = MenuSubmenu({ label: "Export", children: null }); const submenuTrigger = submenu.props.children[0];
assert.equal(submenuTrigger.props["aria-haspopup"], "menu"); assert.equal(submenuTrigger.props.className, "menu-item"); assert.equal(submenuTrigger.props["aria-controls"], "menu-test-menu"); submenuTrigger.props.onClick(); assert.equal(states.at(-1).value, true, "touch click opens submenu state");
globalThis.requestAnimationFrame = callback => { callback(); return 1; };
const childItem = { tabIndex: -1, disabled: false, focused: 0, getAttribute: () => null, focus() { this.focused++; }, closest: () => childMenu };
const childMenu = { querySelectorAll: () => [childItem] };
let keyboardPrevented = 0;
submenuTrigger.props.onKeyDown({ key: "Enter", preventDefault: () => keyboardPrevented++, currentTarget: { parentElement: { querySelector: () => childMenu } } });
assert.equal(keyboardPrevented, 1); assert.equal(childItem.focused, 1, "keyboard opening focuses the first enabled child");

globalThis.window = { innerWidth: 300, innerHeight: 240, addEventListener() {}, removeEventListener() {} };
const classes = new Set(), style = {};
const flyout = { style, parentElement: { getBoundingClientRect: () => ({ top: 190, left: 250, right: 290 }) },
  getBoundingClientRect: () => ({ top: 190, bottom: 390, left: 290, right: 490, width: 200, height: 200 }),
  classList: { add: name => classes.add(name), remove: name => classes.delete(name), toggle: (name, value) => value ? classes.add(name) : classes.delete(name) } };
stateOverride = true; refs.push(flyout); effects.length = 0; MenuSubmenu({ label: "Nested", children: null }); effects.forEach(effect => effect()); stateOverride = undefined;
assert.equal(style.position, "fixed"); assert.equal(style.left, "50px"); assert.equal(style.top, "32px"); assert.equal(classes.has("application-menu--flip"), true, "nested flyout flips and fits without ancestor clipping");

const listeners = new Map();
globalThis.document = {
  querySelector: () => null,
  addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name),
};
const windowListeners = new Map();
globalThis.window = { innerWidth: 1000, innerHeight: 700, addEventListener: (name, fn) => windowListeners.set(name, fn), removeEventListener: name => windowListeners.delete(name) };
const makeTop = mnemonic => ({ dataset: { mnemonic }, tabIndex: -1, disabled: false, focused: 0, clicked: 0,
  getAttribute: name => name === "aria-disabled" ? null : name === "aria-expanded" ? "false" : null,
  focus() { this.focused++; }, click() { this.clicked++; }, closest: () => null });
const tops = [makeTop("f"), makeTop("e"), makeTop("v")];
const bar = { querySelectorAll: () => tops, contains: () => false };
refs.push(bar); effects.length = 0;
let closed = 0;
const rendered = MenuBar({ children: null, open: true, onClose: () => closed++ });
assert.equal(rendered.props.children.type, "nav"); assert.equal(rendered.props.children.props.role, "menubar");
for (const effect of effects) effect();
const key = listeners.get("keydown");
let prevented = 0;
key({ defaultPrevented: false, isComposing: false, key: "e", altKey: true, ctrlKey: false, metaKey: false, target: null, getModifierState: () => false, preventDefault: () => prevented++ });
assert.equal(tops[1].focused, 1); assert.equal(tops[1].clicked, 1); assert.equal(prevented, 1, "Alt mnemonic opens the matching top menu");
key({ defaultPrevented: false, isComposing: false, key: "F10", altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, target: null, getModifierState: () => false, preventDefault: () => prevented++ });
assert.equal(tops[0].focused, 1); assert.ok(closed >= 1, "F10 closes an open menu and focuses the bar");
const before = tops[0].focused;
key({ defaultPrevented: false, isComposing: true, key: "F10", target: null, getModifierState: () => false, preventDefault() {} });
assert.equal(tops[0].focused, before, "IME composition does not invoke menu shortcuts");
listeners.get("pointerdown")({ target: {} }); assert.ok(closed >= 2, "outside pointer closes without focusing the menu");
rendered.props.children.props.onBlur({ currentTarget: { contains: () => false }, relatedTarget: {} }); assert.ok(closed >= 3, "focus leaving closes the menu");
windowListeners.get("blur")(); assert.ok(closed >= 4, "window deactivation closes the menu");
console.log("Application menu: roles, disabled activation, touch submenu, mnemonic/F10 guards and outside-focus closing passed.");
