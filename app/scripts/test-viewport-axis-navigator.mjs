// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import React from "react";
import ts from "typescript";
import * as THREE from "three";
import { importTestTypescript } from "./import-test-typescript.mjs";

const { rotateCameraAboutAxis } = await importTestTypescript("viewportAxisRotation");
for (const axis of ["x", "y", "z"]) {
  const camera = new THREE.PerspectiveCamera();
  const target = new THREE.Vector3(3, -2, 5), originalTarget = target.clone();
  camera.position.set(13, -22, 35); camera.up.set(0, 0, 1);
  const original = camera.position.clone(), up = camera.up.clone(), distance = camera.position.distanceTo(target);
  assert.equal(rotateCameraAboutAxis(camera, target, axis, Math.PI / 2), true);
  assert.ok(Math.abs(camera.position.distanceTo(target) - distance) < 1e-10);
  assert.deepEqual(target.toArray(), originalTarget.toArray());
  rotateCameraAboutAxis(camera, target, axis, -Math.PI / 2);
  assert.ok(camera.position.distanceTo(original) < 1e-10);
  assert.ok(camera.up.distanceTo(up) < 1e-10);
  const before = camera.position.clone();
  assert.equal(rotateCameraAboutAxis(camera, target, axis, NaN), false);
  assert.deepEqual(camera.position.toArray(), before.toArray());
}
const source = readFileSync(new URL("../src/ViewportAxisNavigator.tsx", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS,
  target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText;
const require = createRequire(import.meta.url), loaded = { exports: {} }, calls = [], refs = [];
new Function("require", "module", "exports", compiled)(name => name === "react" ? {
  useRef: value => { const ref = { current: value }; refs.push(ref); return ref; },
  forwardRef: render => render, useId: () => ":ring-test:",
  useImperativeHandle: (ref, create) => { ref.current = create(); },
} : name.endsWith(".css") ? {} : require(name), loaded, loaded.exports);
const { navigatorRingPoints } = loaded.exports;
const identity = { x: 0, y: 0, z: 0, w: 1 };
const identityZ = navigatorRingPoints("z", identity);
assert.deepEqual(identityZ[0], { x: 117, y: 64 });
assert.ok(Math.abs(identityZ[24].x - 64) < 1e-12 && Math.abs(identityZ[24].y - 11) < 1e-12);
assert.ok(navigatorRingPoints("x", identity).every(point => point.x === 64), "Edge-on X ring projects to a line");
const quarterZ = { x: 0, y: 0, z: Math.SQRT1_2, w: Math.SQRT1_2 };
const rotated = navigatorRingPoints("z", quarterZ);
assert.ok(Math.abs(rotated[0].x - 64) < 1e-12 && Math.abs(rotated[0].y - 117) < 1e-12,
  "Camera rotation is inverted when projecting world rings");
const arbitrary = new THREE.Quaternion().setFromEuler(new THREE.Euler(.4, -.7, 1.2));
for (const axis of ["x", "y", "z"]) {
  const points = navigatorRingPoints(axis, arbitrary);
  assert.equal(points.length, 96);
  assert.ok(points.every(point => Math.hypot(point.x - 64, point.y - 64) <= 53 + 1e-10));
}
const ref = { current: null };
const tree = loaded.exports.default({ onRotate: (...args) => calls.push(args) }, ref);
function nodes(element) { return !element || typeof element !== "object" ? [] : [element, ...React.Children.toArray(element.props?.children).flatMap(nodes)]; }
const handles = nodes(tree).filter(node => node.props?.role === "button");
assert.equal(handles.length, 3);
assert.equal(nodes(tree).filter(node => node.type === "button").length, 0, "Ring handles replace the old button row");
const clipping = nodes(tree).find(node => node.type === "clipPath");
assert.equal(clipping.props.children.props.clipRule, "evenodd", "Ring hit regions leave the axis snap center open");
const stop = () => {}, click = { stopPropagation: stop, shiftKey: false };
for (const [index, axis] of ["x", "y", "z"].entries()) {
  const handle = handles[index];
  assert.match(handle.props["aria-label"], new RegExp(`${axis.toUpperCase()} axis`));
  assert.equal(handle.props.tabIndex, 0);
  handle.props.onClick(click);
  assert.deepEqual(calls.pop(), [axis, Math.PI / 12]);
  handle.props.onClick({ ...click, shiftKey: true });
  assert.deepEqual(calls.pop(), [axis, -Math.PI / 12]);
  for (const key of ["ArrowLeft", "ArrowDown", "-"]) {
    handle.props.onKeyDown({ ...click, key, preventDefault: stop });
    assert.deepEqual(calls.pop(), [axis, -Math.PI / 12]);
  }
  for (const key of ["ArrowRight", "ArrowUp", "+", "Enter", " "]) {
    handle.props.onKeyDown({ ...click, key, preventDefault: stop });
    assert.deepEqual(calls.pop(), [axis, Math.PI / 12]);
  }
}
let updates = 0;
refs[0].current = { getBoundingClientRect: () => ({ left: 0, top: 0, width: 128, height: 128 }),
  querySelectorAll: () => [{ setAttribute(name, value) { assert.equal(name, "d"); assert.match(value, /^M.* Z$/); updates++; } }] };
ref.current.setOrientation(arbitrary);
assert.equal(updates, 3);
ref.current.setOrientation(arbitrary);
ref.current.setOrientation({ x: NaN, y: 0, z: 0, w: 1 });
assert.equal(updates, 3, "Unchanged and invalid orientations do not rewrite paths");
ref.current.setOrientation(identity);
let captured = false, focused = false;
const target = { focus() { focused = true; }, setPointerCapture() { captured = true; },
  hasPointerCapture: () => captured, releasePointerCapture() { captured = false; } };
const handle = handles[2];
const event = { pointerId: 4, button: 0, clientX: 117, clientY: 64, currentTarget: target, stopPropagation: stop };
handle.props.onPointerDown(event);
assert.ok(captured && focused);
handle.props.onPointerMove({ ...event, clientY: 63 });
assert.equal(calls.length, 0, "Tiny movement remains a click");
handle.props.onPointerMove({ ...event, pointerId: 8, clientY: 54 });
assert.equal(calls.length, 0, "Uncaptured pointers do not rotate the camera");
handle.props.onPointerMove({ ...event, clientY: 54 });
const dragCall = calls.pop();
assert.equal(dragCall[0], "z");
assert.ok(Math.abs(dragCall[1] + 10 / 53) < .001, "Camera orbit keeps the projected ring following the drag tangent");
handle.props.onPointerUp(event);
assert.equal(captured, false);
handle.props.onClick(click);
assert.equal(calls.length, 0, "Dragging does not add a click rotation on release");
handle.props.onPointerMove({ ...event, clientY: 44 });
assert.equal(calls.length, 0, "Released handles stop rotating");
for (const end of ["onPointerCancel", "onLostPointerCapture"]) {
  handle.props.onPointerDown(event);
  handle.props[end](event);
  handle.props.onPointerMove({ ...event, clientY: 54 });
  assert.equal(calls.length, 0, `${end} stops drag rotation`);
}
console.log("Axis navigator: projected rings, orientation updates, snap pass-through, click, keyboard, pointer lifecycle and camera conservation passed");
