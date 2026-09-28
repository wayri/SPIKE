// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const appRoot = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(appRoot, "src", "ThermalTransientOverlay.tsx"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
} }).outputText;
const states = [];
let cursor = 0;
const module = { exports: {} };
const require = createRequire(import.meta.url);
const dependencies = {
  react: { useState(initial) { const position = cursor++; if (!(position in states)) states[position] = initial;
    return [states[position], value => { states[position] = typeof value === "function" ? value(states[position]) : value; }]; }, useEffect() {} },
  "react/jsx-runtime": require("react/jsx-runtime"),
  "./numericRange": { numericExtent: values => ({ minimum: Math.min(...values), maximum: Math.max(...values) }) },
  "./thermalResultFields": { thermalFieldColor: (value, minimum, maximum) => value === minimum ? [0, 0, 1] : value === maximum ? [1, 0, 0] : [0.5, 0.5, 0.5] },
};
new Function("require", "module", "exports", compiled)(name => dependencies[name] ?? require(name), module, module.exports);
const Overlay = module.exports.default;
const board = { bounds: { minX: 0, minY: 0, maxX: 20, maxY: 10 },
  outlineLoops: [[[0, 0], [20, 0], [20, 10], [0, 10], [0, 0]]],
  components: [{ ref: "U1", at: [5, 5] }, { ref: "U2", at: [15, 5] }] };
const nodes = [
  { id: "U1", component_ref: "U1", steady_temperature_c: 40, peak_transient_temperature_c: 32, peak_transient_time_s: 10, time_to_90pct_steady_s: null, final_to_steady_gap_c: 8 },
  { id: "U2", component_ref: "U2", steady_temperature_c: 35, peak_transient_temperature_c: 30, peak_transient_time_s: 10, time_to_90pct_steady_s: 7, final_to_steady_gap_c: 5 },
];
const frames = [{ time_s: 0, temperatures_c: { U1: 25, U2: 25 } },
  { time_s: 10, temperatures_c: { U1: 32, U2: 30 } }];
function findNode(node, predicate) {
  if (!node || typeof node !== "object") return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) {
    const found = findNode(child, predicate);
    if (found) return found;
  }
  return null;
}
function mount() { cursor = 0; return Overlay({ board, nodes, frames }); }
const initial = mount();
assert.match(renderToStaticMarkup(initial), /TRANSIENT PART OVERLAY/);
assert.match(renderToStaticMarkup(initial), /not reached/);
assert.match(renderToStaticMarkup(initial), /Board outline with transient component temperature markers/);
assert.equal(findNode(initial, node => node.type === "input" && node.props["aria-label"] === "Thermal part animation time frame").props.value, 0);
findNode(initial, node => node.type === "input" && node.props["aria-label"] === "Thermal part animation time frame").props.onChange({ target: { value: "1" } });
const later = renderToStaticMarkup(mount());
assert.match(later, /10\.00 s · hottest U1 32\.00 °C/);
assert.match(later, /U1: 32\.00 °C at 10\.00 s/);
console.log("thermal transient marker overlay, analytics, and seek passed");
