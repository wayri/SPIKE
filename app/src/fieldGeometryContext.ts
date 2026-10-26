// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

/** A render-pass override: never clone/dispose shared CAD materials or retain a stale baseline. */
export function beginFieldGeometryContext(roots: readonly THREE.Object3D[], opacity: number) {
  const factor = Number.isFinite(opacity) ? Math.max(0, Math.min(1, opacity)) : 1;
  if (factor === 1) return { restore() {} };
  const saved = new Map<THREE.Material, { opacity: number; transparent: boolean; depthWrite: boolean }>();
  const visit = (object: THREE.Object3D) => {
    if (object.userData.fieldVolumeOverlay || object.userData.presentationOnly) return;
    const material = (object as THREE.Mesh).material;
    for (const entry of material ? (Array.isArray(material) ? material : [material]) : []) {
      if (saved.has(entry) || factor === 1) continue;
      saved.set(entry, { opacity: entry.opacity, transparent: entry.transparent, depthWrite: entry.depthWrite });
      entry.opacity *= factor; entry.transparent = true; entry.depthWrite = false;
    }
    object.children.forEach(visit);
  };
  roots.forEach(visit);
  return { restore() { for (const [material, original] of saved) Object.assign(material, original); saved.clear(); } };
}
