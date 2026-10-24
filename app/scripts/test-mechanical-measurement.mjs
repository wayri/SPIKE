// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createRequire} from "node:module";
import ts from "typescript";
import {renderToStaticMarkup} from "react-dom/server";
import {importTestTypescript} from "./import-test-typescript.mjs";
const geometry = await importTestTypescript("mechanicalMeasurement");
const {measureMechanicalPoints: measure, parseMeasurementPoint: parse, mechanicalMeasurementCsv: csv} = geometry;
assert.equal(measure([0,0,0], [3,4,12]).distance, 13, "independent integer 3D Pythagorean fixture");
assert.deepEqual(measure([5,-2,7], [-1,2,4]).delta, [-6,4,-3], "signed delta follows B minus A");
assert.equal(measure([2,3,4], [2,3,4]).distance, 0);
assert.equal(measure([1,2,3], [4,6,15]).distance, measure([4,6,15], [1,2,3]).distance);
assert.equal(measure([0,0,0], [1e200,0,0]).distance, 1e200, "hypot avoids intermediate square overflow");
assert.throws(() => measure([NaN,0,0],[0,0,0]), /finite/);
assert.throws(() => measure([Infinity,0,0],[0,0,0]), /finite/);
assert.throws(() => measure([-1e308,0,0],[1e308,0,0]), /range/);
assert.equal(parse(["", "0", "0"]), null, "empty coordinate cannot silently become zero");
assert.equal(parse(["0", "Infinity", "0"]), null);
assert.deepEqual(parse(["-2.5", "1e2", "0"]), [-2.5,100,0]);
assert.equal(csv(measure([0,0,0],[3,4,12])).split("\r\n")[1], "assembly,mm,0,0,0,3,4,12,3,4,12,13");
const require = createRequire(import.meta.url);
const cells = []; let cursor = 0; let effects = [];
const hooks = {
  useState(initial) {const index = cursor++; if (!(index in cells)) cells[index] = typeof initial === "function" ? initial() : initial; return [cells[index], value => {cells[index] = value;}];},
  useMemo(fn) {return fn();},
  useRef(initial) {const index = cursor++; if (!(index in cells)) cells[index] = {current: initial}; return cells[index];},
  useEffect(fn) {effects.push(fn);},
};
const source = readFileSync(new URL("../src/MechanicalMeasurementControls.tsx", import.meta.url), "utf8");
const output = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const module = {exports: {}};
new Function("require", "module", "exports", output)(name => name === "react" ? hooks : name === "./mechanicalMeasurement" ? geometry : name.endsWith(".css") ? {} : require(name), module, module.exports);
const {MechanicalMeasurementControls: Panel} = module.exports;
const received = []; const props = {onMeasure: value => received.push(value)};
function render(extra = {}) {cursor = 0; effects = []; const element = Panel({...props, ...extra}); for (const effect of effects) effect(); return element;}
function all(element) {if (!element || typeof element !== "object") return []; return [element, ...[element.props?.children].flat(Infinity).flatMap(all)];}
function button(tree, label) {return all(tree).find(element => element.type === "button" && element.props.children === label);}
let tree = render();
assert.equal(button(tree, "JSON").props.disabled, true);
assert.equal(all(tree).filter(element => element.type === "button" && element.props.disabled).length, 4);
const html = renderToStaticMarkup(tree);
assert.match(html, /Anchors are not surface snaps/);
assert.match(html, /Point A X \(mm\)/);
tree = render({selectedPoint: [1,2,3], selectedLabel: "Board anchor"});
const captureA = all(tree).find(element => element.type === "button" && element.props.title === "Use anchor of Board anchor");
captureA.props.onClick();
tree = render({selectedPoint: [4,6,15]});
const captureButtons = all(tree).filter(element => element.type === "button" && String(element.props.children).includes("from selection"));
captureButtons[1].props.onClick();
tree = render();
assert.deepEqual(received.at(-1), {pointA: [1,2,3], pointB: [4,6,15]}, "selection capture emits assembly coordinates");
assert.equal(button(tree, "JSON").props.disabled, false);
const input = all(tree).find(element => element.props?.["aria-label"] === "Point B Z (mm)");
input.props.onChange({target: {value: ""}}); tree = render();
assert.equal(received.at(-1), null, "invalid manual edit clears measurement markers");
assert.equal(button(tree, "CSV").props.disabled, true);
button(tree, "Clear").props.onClick(); tree = render();
assert.ok(all(tree).filter(element => element.type === "input").every(element => element.props.value === ""));
console.log("Mechanical measurement: 3D distance, signed axes, finite/range guards, exports, accessible render and capture/edit/clear callbacks passed.");

