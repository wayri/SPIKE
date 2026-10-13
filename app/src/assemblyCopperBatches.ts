// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import { mergeTransformedGeometries } from "./mergedGeometryTransforms";

/** Batch display triangles by scoped net/layer while retaining exact object picks.
 * Original meshes stay in the hierarchy with non-rendering materials: their
 * transforms and source identities remain available to the raycaster.
 */
export function batchAssemblyCopper(group: THREE.Group) {
  const buckets = new Map<string, THREE.Mesh[]>();
  for (const object of [...group.children]) {
    if (!(object instanceof THREE.Mesh) || Array.isArray(object.material)) continue;
    const data = object.userData;
    if (!String(data.sceneKind).startsWith("copper-") && !String(data.sceneKind).startsWith("via-")) continue;
    const key = JSON.stringify([data.sceneKind, data.layer, data.canonicalNetId]);
    const meshes = buckets.get(key) ?? [];
    meshes.push(object); buckets.set(key, meshes);
  }
  let before = 0, after = 0;
  for (const meshes of buckets.values()) {
    before += meshes.length;
    if (meshes.length < 2) { after++; continue; }
    const entries = meshes.map(mesh => {
      mesh.updateMatrix();
      return { geometry: mesh.geometry, matrix: mesh.matrix };
    });
    const geometry = mergeTransformedGeometries(entries);
    if (!geometry) { after += meshes.length; continue; }
    const first = meshes[0];
    const material = (first.material as THREE.Material).clone();
    material.visible = true;
    const batch = new THREE.Mesh(geometry, material);
    batch.name = "assembly-copper-batch";
    batch.userData = { ...first.userData, sourceObjectId: `batch:${first.userData.sourceObjectId}`,
      assemblyCopperBatch: true, sourceObjectCount: meshes.length };
    group.add(batch);
    for (const mesh of meshes) {
      (mesh.material as THREE.Material).visible = false;
      mesh.layers.set(31);
      mesh.userData.pickingProxy = true;
    }
    after++;
  }
  group.userData.copperDrawCalls = { before, after };
  return { before, after };
}
