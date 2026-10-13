// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";

export type GeometryTransform = Readonly<{ geometry: THREE.BufferGeometry; matrix: THREE.Matrix4 }>;

function canTransformMergedWindows(geometry: THREE.BufferGeometry): boolean {
  const position = geometry.getAttribute("position");
  if (!(position instanceof THREE.BufferAttribute) || position.itemSize !== 3 || !(position.array instanceof Float32Array)) return false;
  if (Object.keys(geometry.morphAttributes).length > 0 || geometry.morphTargetsRelative) return false;
  for (const [name, attribute] of Object.entries(geometry.attributes) as Array<[
    string, THREE.BufferAttribute | THREE.InterleavedBufferAttribute,
  ]>) {
    if (!(attribute instanceof THREE.BufferAttribute) || attribute instanceof THREE.InstancedBufferAttribute
      || attribute.normalized || attribute.count !== position.count) return false;
    if (attribute.gpuType !== THREE.FloatType) return false;
    if (name === "normal" && (attribute.itemSize !== 3 || !(attribute.array instanceof Float32Array))) return false;
    if (name === "tangent" && (attribute.itemSize !== 4 || !(attribute.array instanceof Float32Array))) return false;
  }
  return true;
}

function cloneTransformMerge(entries: readonly GeometryTransform[]): THREE.BufferGeometry | null {
  const transformed: THREE.BufferGeometry[] = [];
  try {
    for (const entry of entries) {
      const clone = entry.geometry.clone();
      transformed.push(clone);
      clone.applyMatrix4(entry.matrix);
    }
    return mergeGeometries(transformed, false);
  } finally {
    transformed.forEach(geometry => geometry.dispose());
  }
}

/** Merge immutable sources once, then transform windows of the final buffers. */
export function mergeTransformedGeometries(entries: readonly GeometryTransform[]): THREE.BufferGeometry | null {
  if (entries.length === 0) return null;
  if (entries.some(entry => !canTransformMergedWindows(entry.geometry))) return cloneTransformMerge(entries);
  const merged = mergeGeometries(entries.map(entry => entry.geometry), false);
  if (!merged) return null;
  try {
    let vertexOffset = 0;
    for (const entry of entries) {
      const vertexCount = entry.geometry.getAttribute("position").count;
      const window = new THREE.BufferGeometry();
      for (const name of ["position", "normal", "tangent"] as const) {
        const target = merged.getAttribute(name) as THREE.BufferAttribute | undefined;
        if (!target) continue;
        const start = vertexOffset * target.itemSize;
        window.setAttribute(name, new THREE.BufferAttribute(
          (target.array as Float32Array).subarray(start, start + vertexCount * target.itemSize), target.itemSize, false,
        ));
      }
      window.applyMatrix4(entry.matrix);
      vertexOffset += vertexCount;
    }
    return merged;
  } catch (error) {
    merged.dispose();
    throw error;
  }
}
