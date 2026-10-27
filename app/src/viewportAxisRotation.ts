// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { ViewportRotationAxis } from "./ViewportAxisNavigator";

/** Orbit the camera and its up direction about a world axis; keep geometry fixed. */
export function rotateCameraAboutAxis(camera: THREE.Camera, target: THREE.Vector3,
  axis: ViewportRotationAxis, radians: number): boolean {
  if (!["x", "y", "z"].includes(axis) || !Number.isFinite(radians)
    || !camera.position.toArray().every(Number.isFinite) || !target.toArray().every(Number.isFinite)) return false;
  const direction = new THREE.Vector3(axis === "x" ? 1 : 0, axis === "y" ? 1 : 0, axis === "z" ? 1 : 0);
  const rotation = new THREE.Quaternion().setFromAxisAngle(direction, radians);
  camera.position.sub(target).applyQuaternion(rotation).add(target);
  camera.up.applyQuaternion(rotation).normalize();
  camera.lookAt(target);
  camera.updateMatrixWorld(true);
  return true;
}
