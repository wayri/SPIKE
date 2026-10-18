// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const require = createRequire(import.meta.url);
const root = resolve(import.meta.dirname, "../src");
const cache = new Map();
function load(name) {
  if (name.endsWith(".css")) return {};
  if (!name.startsWith("./")) return require(name);
  if (cache.has(name)) return cache.get(name);
  const path = resolve(root, name.slice(2) + (name.includes("Panel") ? ".tsx" : ".ts"));
  const compiled = ts.transpileModule(readFileSync(path, "utf8"), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const module = { exports: {} };
  new Function("require", "module", "exports", compiled)(load, module, module.exports);
  cache.set(name, module.exports);
  return module.exports;
}
const { allocatePiPinLoads: allocate, eligibleComponentSupplyPads: eligible } = load("./piPinLoads");
const pad = (id, net, extra = {}) => ({ id, ref: "U1", name: id, net, layers: ["F.Cu"], layer: "F.Cu", ...extra });
const board = { components: [{ id: "u1", ref: "U1", value: "IC" }, { id: "u2", ref: "U2", value: "Other" }], nets: { "1": "VCC", "2": "GND", "3": "VDDIO" },
  pads: [pad("a", "VCC"), pad("b", "1"), pad("c", "GND"), pad("d", "VDDIO"), pad("e", "VCC", { type: "np_thru_hole" }), pad("f", "VCC", { layers: ["F.Mask"], layer: "F.Mask" }), pad("g", "VCC", { ref: "U2" })] };
assert.deepEqual(eligible(board, "U1", "VCC").map(p => p.id), ["a", "b"]);
assert.deepEqual(eligible(board, "U1", "1").map(p => p.id), ["a", "b"]);
assert.deepEqual(eligible(board, "U1", "VC"), []);
assert.deepEqual(eligible(board, "unknown", "VCC"), []);
assert.deepEqual(eligible(board, "U1", ""), []);
const copied=eligible(board,"U1","VCC");copied.pop();assert.equal(eligible(board,"U1","VCC").length,2,"Caller cannot mutate cached pad membership");
const changing={...board};eligible(changing,"U1","VCC");changing.pads=[...board.pads,pad("new","VCC")];assert.equal(eligible(changing,"U1","VCC").length,3,"Replacement pad snapshots invalidate the index");

assert.deepEqual(eligible({ ...board, nets: { "1": "VCC", "2": "1" } }, "U1", "1").map(p => p.id), ["b"]);
assert.deepEqual(allocate(0.9, [{ padId: "a" }, { padId: "b" }, { padId: "c" }]).map(p => p.currentA), [0.3, 0.3, 0.30000000000000004]);
assert.deepEqual(allocate(2, [{ padId: "a", weight: 1 }, { padId: "b", weight: 3 }, { padId: "c", weight: 0 }], "weights"), [{ padId: "a", currentA: 0.5 }, { padId: "b", currentA: 1.5 }, { padId: "c", currentA: 0 }]);
for (const total of [0, 1e-200, 0.1, 1234, 1e300]) {
  const pins = Array.from({ length: 91 }, (_, i) => ({ padId: String(i), weight: i % 7 }));
  const result = allocate(total, pins, "weights");
  assert.equal(result.reduce((sum, pin) => sum + pin.currentA, 0), total);
  assert.ok(result.every(pin => Number.isFinite(pin.currentA) && pin.currentA >= 0));
}
for (const total of [-1, Infinity, NaN]) assert.throws(() => allocate(total, [{ padId: "a" }]));
for (const weight of [-1, Infinity, NaN, undefined]) assert.throws(() => allocate(1, [{ padId: "a", weight }], "weights"));
assert.throws(() => allocate(1, []));
assert.throws(() => allocate(1, [{ padId: "a" }, { padId: "a" }]));
assert.throws(() => allocate(1, [{ padId: "" }]));
assert.throws(() => allocate(1, [{ padId: "a", weight: 0 }], "weights"));
assert.throws(() => allocate(1, [{ padId: "a", weight: Number.MAX_VALUE }, { padId: "b", weight: Number.MAX_VALUE }], "weights"));
const { PiComponentLoadPanel: Panel } = load("./PiComponentLoadPanel");
const render = props => renderToStaticMarkup(React.createElement(Panel, { board, net: "VCC", onApply() {}, ...props }));
assert.match(render({ board: null }), /Load a board/);
assert.match(render({ net: "" }), /Select a PI rail/);
assert.match(render({ net: "missing" }), /No component copper pads/);
const markup = render({});
assert.match(markup, /Equal sharing is an editable input assumption/);
assert.match(markup, /Total component current is required/);
assert.match(markup, /disabled=""[^>]*>Apply component pin loads/);
assert.match(render({ initialRef: "U1", initialTotalCurrentA: .6, fixedRef: true }), /0.300000/);
assert.match(render({ initialRef: "U3", fixedRef: true }), /selected component has no copper pads/);
assert.match(render({ busy: true }), /fieldset disabled=""/);
console.log("PI pin loads: rail candidates, conservation, invalid inputs, and panel states passed.");
