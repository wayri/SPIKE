// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import * as model from "../src/piQuickTune.ts";
const states = [], refs = [], effects = [];
let index = 0, pending = [], handler, changed = 0, runs = [], notices = [], timers = new Map(), timerId = 0;
const same = (a, b) => a && b && a.length === b.length && a.every((value, i) => Object.is(value, b[i]));
const react = {
  useState(initial) { const i = index++; if (!(i in states)) states[i] = initial; return [states[i], value => { states[i] = typeof value === "function" ? value(states[i]) : value; }]; },
  useRef(initial) { const i = index++; return refs[i] ??= { current: initial }; },
  useEffect(fn, deps) { const i = index++; if (!same(effects[i]?.deps, deps)) pending.push(() => { effects[i]?.cleanup?.(); effects[i] = { deps, cleanup: fn() }; }); },
};
const jsx = { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }), Fragment: "fragment" };
const compiled = ts.transpileModule(readFileSync(new URL("../src/PiQuickTuneBar.tsx", import.meta.url), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const module = { exports: {} };
new Function("require", "module", "exports", compiled)(name => name === "react" ? react : name === "react/jsx-runtime" ? jsx : name === "./piQuickTune" ? model : new Proxy({}, { get: () => () => null }), module, module.exports);
let setup = { net: "+5V", loads: [{ id: "sink", net: "+5V", anchorType: "coordinate", anchorId: "", x: "0", y: "1", value: "1" }] };
let scope = "project:A", busy = false;
const bind = value => { handler = value; };
const props = () => ({ setup, scope, occurrenceId: "board-A", available: true, busy,
  onHandler: bind, onChange: next => { setup = next; changed++; }, onRun: async (value, key) => { runs.push({ value, key }); }, onStatus: value => notices.push(value) });
const render = () => { index = 0; pending = []; const tree = module.exports.default(props()); pending.forEach(fn => fn()); return tree; };
const nodes = tree => !tree || typeof tree !== "object" ? [] : [tree, ...[tree.props?.children].flat(Infinity).flatMap(nodes)];
const button = (tree, text) => nodes(tree).find(node => node.type === "button" && [node.props.children].flat(Infinity).filter(v => typeof v === "string").join("").trim() === text);
const realSet = globalThis.setTimeout, realClear = globalThis.clearTimeout;
globalThis.setTimeout = callback => { const id = ++timerId; timers.set(id, callback); return id; };
globalThis.clearTimeout = id => timers.delete(id);
const settle = async () => { const batch = [...timers.values()]; timers.clear(); batch.forEach(fn => fn()); await Promise.resolve(); await Promise.resolve(); };
try {
  let tree = render(); assert.equal(handler, undefined);
  button(tree, "Tune PI").props.onClick(); tree = render(); assert.equal(typeof handler, "function");
  const wheel = { net: "+5V", occurrenceId: "board-A", deltaY: -100, altKey: false };
  handler(wheel); handler(wheel); tree = render();
  assert.equal(setup.loads[0].value, "1.2", "two wheel events before a render use the latest edited current");
  assert.equal(timers.size, 1); await settle(); assert.equal(runs.length, 1); assert.equal(runs[0].value.loads[0].value, "1.2");
  handler({ ...wheel, occurrenceId: "board-B" }); assert.equal(changed, 2); assert.match(notices.at(-1), /occurrence/);
  busy = true; tree = render(); handler(wheel); assert.equal(changed, 2); assert.match(notices.at(-1), /Wait/);
  busy = false; tree = render(); handler({ ...wheel, altKey: true }); tree = render(); assert.equal(setup.loads[0].value, "1.21");
  button(tree, "Undo").props.onClick(); tree = render(); assert.equal(setup.loads[0].value, "1"); await settle(); assert.equal(runs.length, 1);
  handler(wheel); tree = render(); scope = "project:B"; tree = render(); await settle(); assert.equal(runs.length, 1, "switching context cancels the paused gesture");
  handler(wheel); tree = render(); setup = { ...setup, loads: setup.loads.map(load => ({ ...load, value: "4" })) }; tree = render(); await settle(); assert.equal(runs.length, 1, "an external edit invalidates a pending rerun");
  button(tree, "Auto run").props.onClick(); tree = render(); handler(wheel); tree = render(); await settle(); assert.equal(runs.length, 1); button(tree, "Run").props.onClick(); await Promise.resolve(); assert.equal(runs.length, 2);
  effects.forEach(effect => effect?.cleanup?.()); assert.equal(handler, undefined); assert.equal(timers.size, 0);
} finally { globalThis.setTimeout = realSet; globalThis.clearTimeout = realClear; }
console.log("Viewport PI controls: latest gesture, one rerun, occurrence isolation, busy guard, undo and stale cancellation passed.");
