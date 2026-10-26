// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

/** Explicit result inspection shows filled solved surfaces through CAD context.
 * Applied only to the disposable result group, never to source geometry.
 */
export function applyResultInspectionDepth(group: THREE.Group, inspectThroughGeometry: boolean) {
  if (!inspectThroughGeometry) return;
  group.traverse(object => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line || object instanceof THREE.Points)) return;
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      material.depthTest = false;
      material.depthWrite = false;
    }
    object.renderOrder = Math.max(object.renderOrder, 300);
  });
}
