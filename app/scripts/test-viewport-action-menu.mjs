// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const states = [], refs = [], effects = [], layouts = []; let index = 0, pending = [], pendingLayout = [];
const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
const hook = (collection, queue, fn, deps) => { const at = index++; if (!same(collection[at]?.deps, deps)) queue.push(() => { collection[at]?.cleanup?.(); collection[at] = { deps, fn, cleanup: fn() }; }); };
const react = {
  useId() { index++; return "test"; },
  useRef(value) { const at = index++; return refs[at] ??= { current: value }; },
  useState(initial) { const at = index++; if (!(at in states)) states[at] = initial; return [states[at], value => states[at] = typeof value === "function" ? value(states[at]) : value]; },
  useEffect(fn, deps) { hook(effects, pending, fn, deps); },
  useLayoutEffect(fn, deps) { hook(layouts, pendingLayout, fn, deps); },
};
const jsx = (type, props) => ({ type, props: props ?? {} });
const compiled = ts.transpileModule(readFileSync(new URL("../src/ViewportActionMenu.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
let presentationDocument, presentationWindow, portalTarget;
new Function("require", "module", "exports", compiled)(name => name === "react" ? react : name === "react-dom" ? {createPortal:(content,target)=>{portalTarget=target;return content;}} : name === "./panelPresentation" ? { usePanelPresentation: () => ({ ownerDocument: presentationDocument, ownerWindow: presentationWindow, detached: true }) } : name === "react/jsx-runtime" ? { jsx, jsxs: jsx } : {}, module, module.exports);
const listeners = new Map(), windowListeners = new Map();
const origin = { isConnected: true, focused: 0, focus() { this.focused++; presentationDocument.activeElement = this; } };
presentationDocument = { body:{}, activeElement: origin, addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) };
presentationWindow = { innerWidth: 480, innerHeight: 320, addEventListener: (name, fn) => windowListeners.set(name, fn), removeEventListener: name => windowListeners.delete(name) };
globalThis.document = { activeElement: null, addEventListener() { throw new Error("main document listener used"); }, removeEventListener() {} };
globalThis.window = { innerWidth: 1, innerHeight: 1, addEventListener() { throw new Error("main window listener used"); }, removeEventListener() {} };
let closed = 0, runs = 0, tree, menuItems = [], menuElements = [], searchElement;
const style = {}, panel = { style, getBoundingClientRect: () => ({ width: 352, height: 280 }), contains: target => menuElements.includes(target) || target === searchElement };
const menu = { querySelectorAll: () => menuElements };
const groups = [{ id: "view", label: "View and navigate", actions: [{ id: "fit", label: "Fit board", description: "Show the full design", run: () => runs++ }, { id: "blocked", label: "Inspect result", disabledReason: "Run the analysis first", run: () => runs++ }] }, { id: "inspect", label: "Inspect", actions: [{ id: "net", label: "Inspect net", run: () => runs++ }] }, { id: "empty", label: "Empty", actions: [] }];
const props = { x: 470, y: 310, title: "Board actions", summary: ["Workspace: PI", "Object: board"], groups, onClose: () => closed++ };
const nodes = node => !node || typeof node !== "object" ? [] : [node, ...[node.props?.children].flat(Infinity).flatMap(nodes)];
function render() {
  index = 0; pending = []; pendingLayout = []; tree = module.exports.default(props);
  const all = nodes(tree); menuItems = all.filter(node => node.props.role === "menuitem");
  menuElements = menuItems.map(node => ({ dataset: { group: node.props["data-group"] }, tabIndex: node.props.tabIndex, focus() { presentationDocument.activeElement = this; }, scrollIntoView() {} }));
  searchElement = { focus() { presentationDocument.activeElement = this; } };
  for (const node of all) if (node.props.ref) node.props.ref.current = node === tree ? panel : node.props.role === "menu" ? menu : node.type === "input" ? searchElement : null;
  pendingLayout.forEach(fn => fn()); pending.forEach(fn => fn()); return tree;
}
const key = (key, target = presentationDocument.activeElement) => { let prevented = false; tree.props.onKeyDown({ key, target, nativeEvent: { isComposing: false }, stopPropagation() {}, isDefaultPrevented: () => false, preventDefault() { prevented = true; } }); return prevented; };
render();
assert.equal(portalTarget,presentationDocument.body,"popup escapes toolbar clipping in its own window");
effects.forEach(effect=>{if(effect){effect.cleanup?.();assert.equal(origin.focused,0,"effect replay must not blur the new popup");effect.cleanup=effect.fn();}});
assert.equal(closed,0,"opening survives development effect replay");
assert.equal(menuItems.length, 2, "empty groups are omitted");
assert.equal(presentationDocument.activeElement, menuElements[0], "opening focuses the first group");
assert.equal(style.left, "120px"); assert.equal(style.top, "32px", "menu is bounded at bottom right");
assert.equal(key("End"), true); assert.equal(presentationDocument.activeElement, menuElements[1]);
key("ArrowDown"); assert.equal(presentationDocument.activeElement, menuElements[0], "down wraps at the last group");
key("ArrowRight"); render();
assert.equal(nodes(tree).find(n => n.props.role === "menu").props["aria-label"], "View and navigate");
assert.equal(menuItems.length, 2); assert.equal(presentationDocument.activeElement, menuElements[0]);
key("ArrowDown"); assert.equal(presentationDocument.activeElement, menuElements[1]);
assert.equal(menuItems[1].props["aria-disabled"], true); menuItems[1].props.onClick(); assert.equal(runs, 0); assert.equal(closed, 0, "disabled action remains available for explanation without activation");
key("ArrowLeft"); render(); assert.equal(presentationDocument.activeElement, menuElements[0], "back restores originating group");
key("ArrowUp"); assert.equal(presentationDocument.activeElement, menuElements[1]);
menuItems[1].props.onClick(); render();
key("ArrowLeft"); render(); assert.equal(presentationDocument.activeElement, menuElements[1], "second group's focus is restored");
const searchNode = () => nodes(tree).find(n => n.type === "input");
searchNode().props.onChange({ target: { value: "fit" } }); render();
assert.equal(menuItems.length, 1); assert.match(JSON.stringify(menuItems[0]), /View and navigate/, "search retains group context");
key("ArrowDown", searchElement); assert.equal(presentationDocument.activeElement, menuElements[0]);
menuItems[0].props.onClick(); assert.equal(runs, 1); assert.equal(closed, 1); assert.equal(presentationDocument.activeElement, origin);
searchNode().props.onChange({ target: { value: "unfindable" } }); render();
assert.equal(menuItems.length, 0); assert.match(JSON.stringify(tree), /No matching actions/);
searchNode().props.onChange({ target: { value: "" } }); render();
key("ArrowRight"); render();
props.groups = groups.map(group => ({ ...group, actions: group.actions.map(action => ({ ...action })) })); render();
assert.equal(nodes(tree).find(n => n.props.role === "menu").props["aria-label"], "View and navigate", "fresh action arrays preserve submenu state");
let prevented = false;
listeners.get("keydown")({ key: "Escape", isComposing: false, preventDefault() { prevented = true; }, stopPropagation() {} });
assert.equal(prevented, true); assert.equal(closed, 2); assert.equal(presentationDocument.activeElement, origin, "Escape restores original focus");
listeners.get("pointerdown")({ target: menuElements[0] }); assert.equal(closed, 2);
listeners.get("pointerdown")({ target: {} }); assert.equal(closed, 3, "outside pointer closes");
assert.equal(origin.focused, 3);
key("Tab", searchElement); assert.equal(closed, 4, "Tab dismisses while letting browser focus move"); assert.equal(origin.focused, 3, "Tab does not force focus back");
presentationWindow.innerWidth = 400; windowListeners.get("resize")(); assert.equal(style.left, "40px");
props.essentialTools = jsx("div", { "aria-label": "Viewport camera and selection" }); render();
assert.ok(nodes(tree).some(node => node === props.essentialTools), "context camera controls are rendered");
key("Tab", searchElement); assert.equal(closed, 4, "Tab reaches context camera controls without dismissal");
effects.forEach(effect => effect?.cleanup?.()); layouts.forEach(effect => effect?.cleanup?.());
assert.equal(listeners.size, 0); assert.equal(windowListeners.size, 0);
console.log("Viewport action menu: keyboard submenus, focus return, disabled actions, grouped search, stable updates and bounded positioning passed.");


