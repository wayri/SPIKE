// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

export type ResultVectorGlyph = { origin: THREE.Vector3; direction: THREE.Vector3; length: number; color: THREE.Color };

/** Two draw batches for the entire returned vector field; no inferred vectors. */
export function resultVectorGlyphs(values: readonly ResultVectorGlyph[]): THREE.Group {
  const valid = values.filter(value => value.length > 0 && Number.isFinite(value.length)
    && [...value.origin.toArray(), ...value.direction.toArray()].every(Number.isFinite)
    && value.direction.lengthSq() > 0);
  const group = new THREE.Group();
  group.name = "solved-vector-glyphs";
  if (!valid.length) return group;
  const material = new THREE.MeshBasicMaterial({ depthTest:true, depthWrite:false, toneMapped:false });
  const shaft = new THREE.InstancedMesh(new THREE.CylinderGeometry(1, 1, 1, 6), material, valid.length);
  const head = new THREE.InstancedMesh(new THREE.ConeGeometry(1, 1, 8), material.clone(), valid.length);
  const y = new THREE.Vector3(0, 1, 0), transform = new THREE.Object3D();
  valid.forEach((value, index) => {
    const direction = value.direction.clone().normalize(), length = value.length;
    const headLength = length * .28, radius = length * .025;
    transform.quaternion.setFromUnitVectors(y, direction);
    transform.position.copy(value.origin).addScaledVector(direction, (length - headLength) / 2);
    transform.scale.set(radius, length - headLength, radius);
    transform.updateMatrix();shaft.setMatrixAt(index, transform.matrix);shaft.setColorAt(index,value.color);
    transform.position.copy(value.origin).addScaledVector(direction, length - headLength / 2);
    transform.scale.set(radius * 3.2, headLength, radius * 3.2);
    transform.updateMatrix();head.setMatrixAt(index, transform.matrix);head.setColorAt(index,value.color);
  });
  for (const mesh of [shaft, head]) {
    mesh.instanceMatrix.needsUpdate = true;
    if(mesh.instanceColor)mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();mesh.renderOrder=110;
    group.add(mesh);
  }
  return group;
}
