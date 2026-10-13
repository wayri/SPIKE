// SPDX-License-Identifier: Apache-2.0
import assert from "node:assert/strict";
import * as THREE from "three";
import { zoomCameraAt, flipCamera, navigationPanFraction, zoomViewBoxAt } from "../src/viewportKeyboardCamera.ts";

const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);
for (const camera of [new THREE.PerspectiveCamera(45, 1.5, 0.1, 1000), new THREE.OrthographicCamera(-15, 15, 10, -10, 0.1, 1000)]) {
  const target = new THREE.Vector3(1, 2, 3);
  camera.position.set(40, -60, 70);
  camera.up.set(0, 0, 1);
  camera.lookAt(target);
  camera.updateMatrixWorld(true);
  const anchor = new THREE.Vector3(8, -5, 7);
  const before = anchor.clone().project(camera);
  const initialPosition = camera.position.clone();
  const initialTarget = target.clone();
  const initialDistance = camera.position.distanceTo(target);
  zoomCameraAt(camera, target, anchor, 0.8);
  camera.lookAt(target);
  camera.updateMatrixWorld(true);
  const after = anchor.clone().project(camera);
  close(before.x, after.x);
  close(before.y, after.y);
  zoomCameraAt(camera, target, anchor, 1.25);
  close(camera.position.distanceTo(initialPosition), 0);
  close(target.distanceTo(initialTarget), 0);
  flipCamera(camera, target);
  close(camera.position.distanceTo(target), initialDistance);
  close(camera.position.clone().sub(target).dot(initialPosition.clone().sub(target)), -(initialDistance ** 2));
  flipCamera(camera, target);
  close(camera.position.distanceTo(initialPosition), 0);
}
const bounded = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.1, 1000);
bounded.zoom = 30;
bounded.position.set(0, 0, 50);
const boundedTarget = new THREE.Vector3();
zoomCameraAt(bounded, boundedTarget, new THREE.Vector3(5, 5, 0), 0.8);
close(bounded.position.x, 0);
close(boundedTarget.x, 0);
assert.equal(navigationPanFraction("pan-left-fast:123"), 0.32);
assert.equal(navigationPanFraction("pan-down:123"), 0.08);
const view = {x: 10, y: 20, width: 100, height: 80};
const zoomed = zoomViewBoxAt(view, [35, 60], 80, 64);
close((35 - view.x) / view.width, (35 - zoomed.x) / zoomed.width);
close((60 - view.y) / view.height, (60 - zoomed.y) / zoomed.height);
assert.deepEqual(zoomViewBoxAt(zoomed, [35, 60], 100, 80), view);
console.log("viewport keyboard camera: all assertions passed");
