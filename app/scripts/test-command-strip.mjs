// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import ts from "typescript";
import React from "react";

const require = createRequire(import.meta.url);
const effects = [], observers = [], moves = [];
let state = { overflow: false, start: true, end: true };
class Element {
  constructor(bounds) { this.bounds = bounds; }
  getBoundingClientRect() { return this.bounds; }
}
const viewport = new Element({ left: 10, right: 210 });
Object.assign(viewport, {
  clientWidth: 200, scrollWidth: 800, scrollLeft: 0, children: [new Element({ left: 10, right: 810 })],
  scrollBy({ left }) { moves.push(left); this.scrollLeft = Math.max(0, Math.min(this.scrollWidth - this.clientWidth, this.scrollLeft + left)); },
  scrollTo({ left }) { this.scrollLeft = Math.max(0, Math.min(this.scrollWidth - this.clientWidth, left)); },
});
class Observer {
  constructor(callback) { this.callback = callback; this.targets = []; this.disconnected = false; observers.push(this); }
  observe(target) { this.targets.push(target); }
  disconnect() { this.disconnected = true; }
}
const code = ts.transpileModule(readFileSync(new URL("../src/CommandStrip.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", "ResizeObserver", "HTMLElement", code)(name => {
  if (name === "react") return { ...React, useId: () => "test-strip", useRef: () => ({ current: viewport }),
    useState: () => [state, change => { state = typeof change === "function" ? change(state) : change; }],
    useLayoutEffect: callback => effects.push(callback) };
  if (name.endsWith(".css")) return {};
  return require(name);
}, module, module.exports, Observer, Element);
const Strip = module.exports.default;
const children = React.createElement("select", { "aria-label": "Camera view" });
const render = () => Strip({ label: "Viewport", children });
let tree = render();
const cleanup = effects.shift()();
tree = render();
let [previous, commands, next] = tree.props.children;
assert.equal(previous.props.hidden, false, "overflow exposes a discoverable scroll control");
assert.equal(previous.props.disabled, true);
assert.equal(next.props.disabled, false);
assert.equal(next.props["aria-controls"], commands.props.id);
assert.ok(observers[0].targets.includes(viewport.children[0]), "changes to group widths trigger overflow measurement");
next.props.onClick();
assert.equal(viewport.scrollLeft, 140, "arrows reveal the next portion of the same toolbar");
commands.props.onScroll();
assert.equal(state.start, false);
let prevented = false, stopped = false;
const key = (target, value) => commands.props.onKeyDown({ target, currentTarget: viewport, key: value, preventDefault() { prevented = true; }, stopPropagation() { stopped = true; } });
key(viewport.children[0], "ArrowRight");
assert.equal(prevented, false, "arrow keys inside selects retain native selection behavior");
assert.equal(viewport.scrollLeft, 140);
key(viewport, "End"); commands.props.onScroll();
assert.equal(stopped, true, "toolbar scrolling must not also activate canvas navigation shortcuts");
assert.equal(viewport.scrollLeft, 600);
assert.equal(state.end, true, "end-of-strip controls disable when no further commands remain");
key(viewport, "Home"); commands.props.onScroll();
assert.equal(viewport.scrollLeft, 0);
commands.props.onFocusCapture({ currentTarget: viewport, target: new Element({ left: 260, right: 290 }) });
assert.equal(viewport.scrollLeft, 84, "keyboard focus reveals a command beyond the visible edge");
commands.props.onFocusCapture({ currentTarget: viewport, target: new Element({ left: 2, right: 28 }) });
assert.equal(viewport.scrollLeft, 72, "reverse tabbing reveals a command before the visible edge");
viewport.clientWidth = 900; viewport.scrollLeft = 0; observers[0].callback();
assert.equal(state.overflow, false, "scroll affordances recover after widening the panel");
viewport.clientWidth = 240; observers[0].callback();
assert.equal(state.overflow, true, "narrowing a dock re-enables overflow controls without remounting commands");
cleanup(); assert.equal(observers[0].disconnected, true);
console.log("Command strip overflow, keyboard, native-select, focus, resize and cleanup checks passed.");
