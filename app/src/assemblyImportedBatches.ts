// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import { mergeTransformedGeometries } from "./mergedGeometryTransforms";

/** Reduce occurrence draw calls while keeping exact source meshes for picking.
 * Immutable cached geometry stays shared; new merged geometry and materials
 * belong to this occurrence. Transparent surfaces retain independent sorting.
 */
export function batchAssemblyImported(frame: THREE.Group) {
  frame.updateMatrixWorld(true);
  const inverse = frame.matrixWorld.clone().invert();
  const buckets = new Map<string, THREE.Mesh[]>();
  let before = 0;
  frame.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    before++;
    if (!object.visible || object instanceof THREE.SkinnedMesh || object instanceof THREE.InstancedMesh
      || Array.isArray(object.material) || object.material.transparent || object.morphTargetInfluences?.length
      || new THREE.Matrix4().multiplyMatrices(inverse, object.matrixWorld).determinant() <= 0) return;
    const attributes = Object.entries(object.geometry.attributes as Record<string, THREE.BufferAttribute | THREE.InterleavedBufferAttribute>).map(([name, value]) => `${name}:${value.itemSize}:${value.normalized}`).sort().join(",");
    const key = `${object.material.uuid}|${attributes}|${Boolean(object.geometry.index)}|${object.renderOrder}|${object.userData.componentMount ?? ""}|${object.userData.componentSide ?? ""}|${object.userData.importedBoardLayer ?? ""}|${object.userData.importedBoardSurface ?? ""}`;
    const meshes = buckets.get(key) ?? []; meshes.push(object); buckets.set(key, meshes);
  });
  const hidden = new THREE.MeshBasicMaterial({ visible: false, side: THREE.DoubleSide });
  let after = before;
  for (const meshes of buckets.values()) {
    if (meshes.length < 2) continue;
    const first = meshes[0], instances = new Map<THREE.BufferGeometry, THREE.Mesh[]>();
    for (const mesh of meshes) { const same = instances.get(mesh.geometry) ?? []; same.push(mesh); instances.set(mesh.geometry, same); }
    const batched = new Set<THREE.Mesh>();
    const display = (mesh: THREE.Mesh) => {
      mesh.material = (first.material as THREE.Material).clone();
      mesh.castShadow = first.castShadow; mesh.receiveShadow = first.receiveShadow;
      mesh.renderOrder = first.renderOrder; mesh.name = "assembly-imported-batch";
      mesh.userData = { ...first.userData, assemblyImportedBatch: true };
      frame.add(mesh); after++;
    };
    for (const [geometry, objects] of instances) {
      // Tiny model fragments are cheaper as one material batch than hundreds
      // of separate instanced draws. Detailed repeated models retain sharing.
      if (objects.length < 4 || geometry.getAttribute("position").count < 128) continue;
      for (let start = 0; start < objects.length; start += 2048) {
        const count = Math.min(2048, objects.length - start);
        const mesh = new THREE.InstancedMesh(geometry, first.material, count);
        for (let i = 0; i < count; i++) {
          const object = objects[start + i];
          mesh.setMatrixAt(i, new THREE.Matrix4().multiplyMatrices(inverse, object.matrixWorld)); batched.add(object);
        }
        mesh.instanceMatrix.needsUpdate = true; mesh.computeBoundingBox(); mesh.computeBoundingSphere(); display(mesh);
      }
    }
    const remaining = meshes.filter(mesh => !batched.has(mesh));
    if (remaining.length >= 2) {
      const geometry = mergeTransformedGeometries(remaining.map(mesh => ({
        geometry: mesh.geometry, matrix: new THREE.Matrix4().multiplyMatrices(inverse, mesh.matrixWorld),
      })));
      if (geometry) { display(new THREE.Mesh(geometry, first.material)); remaining.forEach(mesh => batched.add(mesh)); }
    }
    for (const mesh of batched) { mesh.material = hidden; mesh.layers.set(31); mesh.userData.pickingProxy = true; after--; }
  }
  if (after === before) hidden.dispose();
  frame.userData.importedDrawCalls = { before, after };
  return { before, after };
}
