// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
const require = createRequire(import.meta.url);
function load(name, imports = {}) {
  const source = readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(id => id.endsWith(".css") ? {} : imports[id] ?? require(id), mod, mod.exports);
  return mod.exports;
}
const assembly = load("mcadAssembly.ts");
const model = load("mechanicalSectionModel.ts", { "./mcadAssembly": assembly });
const { sectionNormalFromAngles: normal, sectionAnglesFromNormal: angles, updateMechanicalSectionPlane: update } = model;
function close(actual, expected) { assert.equal(actual.length, expected.length); actual.forEach((value, i) => assert.ok(Math.abs(value - expected[i]) < 1e-12, `${actual} != ${expected}`)); }
close(normal(0, 0), [1, 0, 0]); close(normal(90, 0), [0, 1, 0]); close(normal(0, 90), [0, 0, 1]); close(normal(120, -90), [0, 0, -1]); close(normal(405, 0), [Math.SQRT1_2, Math.SQRT1_2, 0]);
for (const pair of [[23, -17], [-173, 53], [180, 0], [0, 89.9]]) {
  const n = normal(...pair); assert.ok(Math.abs(Math.hypot(...n) - 1) < 1e-12);
  const a = angles(n); close(normal(a.azimuth, a.elevation), n);
}
for (const pair of [[NaN, 0], [0, Infinity], [0, 91], [0, -91]]) assert.throws(() => normal(...pair), RangeError);
assert.deepEqual(angles([0, 0, 0]), { azimuth: 0, elevation: 0 });
const legacy = { ...assembly.DEFAULT_ASSEMBLY_SECTION, enabled: true, axis: "z", offsetMm: 7 };
const flipped = update(legacy, { flipped: true });
assert.equal(flipped.mode, "planes"); close(flipped.planes[0].normal, [0, 0, 1]); assert.equal(flipped.planes[0].offsetMm, 7);
const transform = { centerX: 0, centerY: 0, scale: 1 };
const before = assembly.buildAssemblySectionClippingPlanes(legacy, transform)[0];
const after = assembly.buildAssemblySectionClippingPlanes(flipped, transform)[0];
close(before.point, after.point); close(after.normal, before.normal.map(value => -value));
const retained = { id: "keep", normal: [0, 1, 0], enabled: false, flipped: false, offsetMm: 11 };
const multiple = { ...flipped, planes: [...flipped.planes, retained] };
const changed = update(multiple, { normal: normal(23, 41), offsetMm: -4 });
assert.equal(changed.planes[1], retained); assert.equal(multiple.planes[0].offsetMm, 7); assert.equal(changed.minXMm, multiple.minXMm);
const fullPlanes = Array.from({ length: 6 }, (_, i) => ({ ...retained, id: `retained-${i}` }));
const fromBox = update({ ...legacy, mode: "box", planes: fullPlanes }, { offsetMm: 22 });
assert.equal(fromBox.planes.length, 6); assert.deepEqual(fromBox.planes.slice(1), fullPlanes.slice(1));
assert.equal(fromBox.planes[0].id, fullPlanes[0].id);
for (const preset of model.MECHANICAL_SECTION_PRESETS) assert.ok(Math.abs(Math.hypot(...preset.normal) - 1) < 1e-12);
const anchor = [34, -12, 8];
const arbitrary = { ...multiple, enabled: false, planes: [{ ...multiple.planes[0], enabled: false, normal: [2, 3, 6], flipped: true }, retained] };
const through = model.mechanicalSectionThroughPoint(arbitrary, anchor);
assert.ok(through.enabled && through.planes[0].enabled);
assert.ok(Math.abs(through.planes[0].offsetMm - (2 * 34 + 3 * -12 + 6 * 8) / 7) < 1e-12);
assert.equal(through.planes[0].flipped, true); assert.equal(through.planes[1], retained);
const actualCut = assembly.buildAssemblySectionClippingPlanes(through, transform)[0];
assert.ok(Math.abs(actualCut.normal.reduce((sum, n, i) => sum + n * ([34, 12, 8][i] - actualCut.point[i]), 0)) < 1e-12, "selected origin lies on rendered clipping plane");
assert.equal(model.mechanicalSectionThroughPoint(arbitrary, [NaN, 0, 0]), null);
assert.equal(model.mechanicalSectionThroughPoint({ ...arbitrary, planes: [{ ...arbitrary.planes[0], normal: [0, 0, 0] }] }, anchor), null);
const imports = { "./mechanicalSectionModel": model };
const Component = load("MechanicalSectionControls.tsx", imports).default;
for (const section of [legacy, multiple, { ...legacy, mode: "box" }]) {
  const html = renderToStaticMarkup(React.createElement(Component, { section, onChange() {}, onManage() {} }));
  for (const text of ["Cross section", "Azimuth (deg)", "Elevation (deg)", "Offset (mm)", "Box / multiple planes", "uncapped", "BREP"]) assert.ok(html.includes(text), text);
  assert.equal((html.match(/title="Set section normal/g) ?? []).length, 6);
}
// Execute rendered event handlers with deterministic hooks; no browser harness is needed for state routing.
const hookReact = { ...React, useId: () => "test-help", useState: value => [value, () => {}], useEffect: () => {} };
const Interactive = load("MechanicalSectionControls.tsx", { ...imports, react: hookReact }).default;
const changes = []; let managed = false;
const tree = Interactive({ section: legacy, onChange: value => changes.push(value), onManage: () => { managed = true; } });
function flatten(node) { if (!node || typeof node !== "object") return []; return [node, ...React.Children.toArray(node.props?.children).flatMap(flatten)]; }
const nodes = flatten(tree);
const button = label => nodes.find(node => node.type === "button" && node.props.children === label);
button("XY").props.onClick(); close(changes.at(-1).planes[0].normal, [0, 0, 1]);
button("45 XZ").props.onClick(); close(changes.at(-1).planes[0].normal, [Math.SQRT1_2, 0, Math.SQRT1_2]);
button("Apply angles / offset").props.onClick(); close(changes.at(-1).planes[0].normal, [0, 0, 1]);
button("Box / multiple planes").props.onClick(); assert.equal(managed, true);
assert.equal(button("Through selection").props.disabled, true);
for (const point of [undefined, [NaN, 0, 0], anchor]) {
  const anchoredTree = Interactive({ section: arbitrary, anchorPoint: point, onChange: value => changes.push(value) });
  const throughButton = flatten(anchoredTree).find(node => node.type === "button" && node.props.children === "Through selection");
  assert.equal(throughButton.props.disabled, point !== anchor);
  const count = changes.length; throughButton.props.onClick();
  assert.equal(changes.length, count + (point === anchor ? 1 : 0));
  if (point === anchor) assert.deepEqual(changes.at(-1), through);
}
const checkboxes = nodes.filter(node => node.type === "input" && node.props.type === "checkbox");
checkboxes[0].props.onChange({ target: { checked: false } }); assert.equal(changes.at(-1).enabled, false);
checkboxes[1].props.onChange({ target: { checked: false } }); assert.equal(changes.at(-1).planes[0].enabled, false);
checkboxes[2].props.onChange({ target: { checked: true } }); assert.equal(changes.at(-1).planes[0].flipped, true);
for (const invalid of [["", "0", "0"], ["0", "91", "0"], ["0", "0", "Infinity"]]) {
  let index = 0; let error = "";
  const badHooks = { ...hookReact, useState: value => [invalid[index++] ?? value, message => { error = message; }] };
  const BadInput = load("MechanicalSectionControls.tsx", { ...imports, react: badHooks }).default;
  const beforeCount = changes.length;
  const badTree = BadInput({ section: legacy, onChange: value => changes.push(value) });
  flatten(badTree).find(node => node.type === "button" && node.props.children === "Apply angles / offset").props.onClick();
  assert.equal(changes.length, beforeCount); assert.ok(error);
}
console.log("Mechanical section angle, clipping contract, rendering and action tests passed.");



