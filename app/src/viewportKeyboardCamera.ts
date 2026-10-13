// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

/** Scale the view about a physical anchor, preserving its screen position. */
export function zoomCameraAt(camera: THREE.PerspectiveCamera | THREE.OrthographicCamera,
  target: THREE.Vector3, anchor: THREE.Vector3, factor: number) {
  if (!anchor.toArray().every(Number.isFinite) || !Number.isFinite(factor) || factor <= 0) return;
  if (camera instanceof THREE.OrthographicCamera) {
    const oldZoom = camera.zoom;
    camera.zoom = THREE.MathUtils.clamp(oldZoom / factor, 0.1, 30);
    factor = oldZoom / camera.zoom;
    camera.updateProjectionMatrix();
  }
  camera.position.sub(anchor).multiplyScalar(factor).add(anchor);
  target.sub(anchor).multiplyScalar(factor).add(anchor);
}

/** Reverse the viewing direction without moving source geometry or the target. */
export function flipCamera(camera: THREE.Camera, target: THREE.Vector3) {
  camera.position.sub(target).negate().add(target);
}

export function navigationPanFraction(command: string) { return command.split(":", 1)[0].endsWith("-fast") ? 0.32 : 0.08; }

export function zoomViewBoxAt(view: {x: number; y: number; width: number; height: number},
  anchor: readonly [number, number], width: number, height: number) {
  return { x: anchor[0] - (anchor[0] - view.x) / view.width * width,
    y: anchor[1] - (anchor[1] - view.y) / view.height * height, width, height };
}
