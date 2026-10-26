// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
import * as THREE from "three";

function source(name) {
  return ts.createSourceFile(name, readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
}
function find(root, predicate) {
  if (predicate(root)) return root;
  let found;
  ts.forEachChild(root, child => { if (!found) found = find(child, predicate); });
  return found;
}
function runCallback(node, context, ...args) {
  assert(node, "actual renderer callback exists");
  const js = ts.transpileModule(`const callback = ${node.getText()};`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
  return new Function("context", "args", `with(context) { ${js} return callback(...args); }`)(context, args);
}
function commandEffect(root) {
  return find(root, node => ts.isCallExpression(node) && node.expression.getText() === "useEffect"
    && node.arguments[0]?.getText().includes('cameraCommand.startsWith("reset-view-")'))?.arguments[0];
}
const boardSource = source("BoardViewport.tsx");
const fit = find(boardSource, node => ts.isVariableDeclaration(node) && node.name.getText() === "fit" && node.initializer?.getText().includes("refreshVisibleBounds"))?.initializer;
const perspective = new THREE.PerspectiveCamera(45, 2, .1, 10000), orthographic = new THREE.OrthographicCamera();
perspective.position.set(-98, 37, -19); perspective.up.set(0, -1, 0);
let resets = 0, frames = 0, refreshes = 0, saved3d = 0;
const controls3d = { target: new THREE.Vector3(15, -9, 1), enableDamping: true, update() {}, reset() { resets++; this.target.set(0, 0, 0); } };
const controls2d = { target: new THREE.Vector3(20, 20, 20), update() {} };
const center = new THREE.Vector3(12, -8, 6), size = new THREE.Vector3(80, 40, 20);
const fitContext = { THREE, host: { getBoundingClientRect: () => ({ width: 1000, height: 500 }), dataset: {} },
  boardSizeRef: { current: { width: 80, height: 40 } }, perspective, orthographic, controls3d, controls2d,
  refreshVisibleBounds() { refreshes++; }, visibleBoundsRef: { current: { center, size } }, record3dCamera() { saved3d++; }, record2dCamera() {} };
const helperCenter = new THREE.Vector3();
runCallback(commandEffect(boardSource), {
  THREE, cameraCommand: "reset-view-123", viewModeRef: { current: "3D" }, perspectiveRef: { current: perspective }, orthographicRef: { current: orthographic },
  controls3dRef: { current: controls3d }, controls2dRef: { current: controls2d }, setNavigationStatus() {},
  fitRef: { current: mode => runCallback(fit, fitContext, mode) }, viewHelperRef: { current: { center: helperCenter } }, requestInteractiveFrameRef: { current() { frames++; } },
});
assert.equal(resets, 1); assert.equal(controls3d.enableDamping, true);
assert.equal(refreshes, 1); assert.equal(saved3d, 1); assert.equal(frames, 1);
assert.deepEqual(controls3d.target.toArray(), center.toArray());
assert.deepEqual(helperCenter.toArray(), center.toArray());
assert.deepEqual(perspective.up.toArray(), [0, 0, 1]);
const direction = perspective.position.clone().sub(center).normalize();
assert(direction.distanceTo(new THREE.Vector3(.72, -.86, .72).normalize()) < 1e-12, "reset replaces an arbitrary orbit with the default fitted oblique pose");
assert(perspective.position.distanceTo(center) > size.length() / 2, "the full visible geometry is framed");

const initialView = { x: 0, y: 0, width: 80, height: 40 };
let layoutView = { x: 100, y: -200, width: 3, height: 2 };
runCallback(commandEffect(source("LayoutViewport.tsx")), { cameraCommand: "reset-view-123", initialView,
  setNavigationStatus() {}, navigationPointerRef: { current: null }, svgRef: { current: null }, setView(next) { layoutView = next; } });
assert.deepEqual(layoutView, initialView, "single-board 2D reset returns to its default top view and full source frame");
let assemblyView;
const fitBounds = { x: -70, y: 15, width: 150, height: 90 };
runCallback(commandEffect(source("AssemblyLayoutViewport.tsx")), { cameraCommand: "reset-view-123", handledCameraCommand: { current: "" },
  fit: fitBounds, frame(bounds, margin) { assert.equal(margin, .03); return { ...bounds }; }, setView(next) { assemblyView = next; } });
assert.deepEqual(assemblyView, fitBounds, "assembly 2D reset fits the complete displayed assembly");
console.log("viewport reset commands: default 3D orientation/visible fit, damping reset, single and assembly 2D fits passed");
