// SPDX-License-Identifier: MIT
import * as THREE from "three";

export type PlaceholderKind = "body" | "cap" | "marker";
export type PlaceholderInstance = {
  id: string; ref: string; layer: string; mount: "smd" | "tht"; side: 1 | -1;
  kind: PlaceholderKind; color: number; position: THREE.Vector3;
  rotationZ: number; scale: THREE.Vector3;
};

type BatchData = { proceduralComponentBatch: true; instances: PlaceholderInstance[]; baseColor: number };

export function placeholderBatchKey(instance: PlaceholderInstance) {
  return [instance.kind, instance.color, instance.mount, instance.side].join("|");
}

export function buildProceduralComponentInstances(instances: readonly PlaceholderInstance[], maximumBatch = 2048) {
  const root = new THREE.Group();
  const groups = new Map<string, PlaceholderInstance[]>();
  for (const instance of instances) {
    const key = placeholderBatchKey(instance);
    const group = groups.get(key);
    if (group) group.push(instance); else groups.set(key, [instance]);
  }
  for (const grouped of groups.values()) for (let start = 0; start < grouped.length; start += maximumBatch) {
    const records = grouped.slice(start, start + maximumBatch);
    const first = records[0];
    const geometry = first.kind === "marker"
      ? new THREE.CylinderGeometry(1, 1, 1, 16)
      : new THREE.BoxGeometry(1, 1, 1, 2, 2, 1);
    if (first.kind === "marker") geometry.rotateX(Math.PI / 2);
    // Instance colors carry the authored tint. A colored base material would
    // multiply that value in the shader and square/darken every placeholder.
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: first.kind === "cap" ? 0.3 : 0.43, metalness: first.kind === "cap" ? 0.75 : 0, vertexColors: true });
    const mesh = new THREE.InstancedMesh(geometry, material, records.length);
    mesh.castShadow = true; mesh.receiveShadow = true;
    mesh.userData = { proceduralComponentBatch: true, instances: records, baseColor: first.color } satisfies BatchData;
    root.add(mesh);
  }
  return root;
}

export function updateProceduralComponentInstances(root: THREE.Object3D, options: {
  showModels: boolean; showSmd: boolean; showTht: boolean; allowAll: boolean;
  missingRefs: ReadonlySet<string>; selectedId?: string | null;
  hoverId?: string | null; hoverRef?: string | null; separationForLayer: (layer: string) => number;
}) {
  root.visible = options.showModels;
  const matrix = new THREE.Matrix4();
  const quaternion = new THREE.Quaternion();
  const zAxis = new THREE.Vector3(0, 0, 1);
  const hiddenScale = new THREE.Vector3(0, 0, 0);
  const color = new THREE.Color();
  let visible = 0;
  root.traverse(object => {
    if (!(object instanceof THREE.InstancedMesh) || !object.userData.proceduralComponentBatch) return;
    const data = object.userData as BatchData;
    let batchVisible = 0;
    data.instances.forEach((instance, index) => {
      const category = instance.mount === "tht" ? options.showTht : options.showSmd;
      const shown = options.showModels && category && (options.allowAll || options.missingRefs.has(instance.ref));
      const position = instance.position.clone();
      position.z += options.separationForLayer(instance.layer);
      quaternion.setFromAxisAngle(zAxis, instance.rotationZ);
      matrix.compose(position, quaternion, shown ? instance.scale : hiddenScale);
      object.setMatrixAt(index, matrix);
      const hovered = options.hoverId === instance.id || Boolean(options.hoverRef && options.hoverRef === instance.ref);
      color.setHex(hovered ? 0xff38c7 : options.selectedId === instance.id ? 0xffa51f : data.baseColor);
      object.setColorAt(index, color);
      if (shown) { visible += 1; batchVisible += 1; }
    });
    object.instanceMatrix.needsUpdate = true;
    if (object.instanceColor) object.instanceColor.needsUpdate = true;
    object.computeBoundingBox(); object.computeBoundingSphere();
    object.visible = batchVisible > 0;
  });
  return visible;
}
