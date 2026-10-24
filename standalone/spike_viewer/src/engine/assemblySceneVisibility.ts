// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { ParsedBoard } from "./boardTypes";

export function updateAssemblySceneSelection(group: THREE.Object3D, selected: boolean, linked: readonly string[]) {
  const nets = new Set(linked);
  group.traverse(object => {
    const kind = String(object.userData.sceneKind ?? "");
    const copper = kind.startsWith("copper-") || kind.startsWith("via-");
    if (copper) object.userData.linkedAssemblyNet = nets.has(object.userData.canonicalNetId);
    if (!(object instanceof THREE.Mesh) || (!copper && kind !== "substrate")) return;
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (!(material instanceof THREE.MeshStandardMaterial || material instanceof THREE.MeshBasicMaterial)) continue;
      material.userData.assemblyBaseColor ??= material.color.getHex();
      material.color.setHex(copper && object.userData.linkedAssemblyNet ? 0xffd32a
        : kind === "substrate" && selected ? 0x6c913a : material.userData.assemblyBaseColor);
    }
  });
}

/** Update occurrence display only; layer controls never change retained geometry. */
export function applyAssemblySceneVisibility(group: THREE.Object3D, source: ParsedBoard,
  layers: Record<string, boolean>, opacity: Record<string, number>, showVias: boolean) {
  const copper = source.layers.filter(layer => layer.endsWith(".Cu"));
  const defaultVisible = (name: string) => name === "Board body" || name.endsWith(".Cu") || name.endsWith(".Mask") || name.endsWith(".SilkS") || name === "Edge.Cuts";
  const filtered = Object.entries(layers).some(([name, value]) => value !== defaultVisible(name))
    || Object.values(opacity).some(value => value !== 1);
  let bakedBoard = false;
  group.traverse(object => { if (object.userData.kiCadSceneKind === "board") bakedBoard = true; });
  const bakedCopperVisible = bakedBoard && source.boardModelIncludesCopper && !filtered;
  group.traverse(object => {
    const data = object.userData;
    if (data.kiCadSceneKind === "board") object.visible = !filtered && layers["Board body"] !== false;
    const kind = String(data.sceneKind ?? "");
    if (kind === "substrate") object.visible = layers["Board body"] !== false && !(bakedBoard && !filtered);
    else if (kind.startsWith("via-")) object.visible = showVias && copper.some(layer => layers[layer] !== false);
    else if (data.layer && !data.authoritativeModel && kind !== "component-model") object.visible = layers[data.layer] !== false;
    if (!(object instanceof THREE.Mesh || object instanceof THREE.LineSegments)) return;
    const logicalCopper = kind.startsWith("copper-") || kind.startsWith("via-");
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      material.userData.assemblyBaseOpacity ??= logicalCopper ? 1 : material.opacity;
      const hiddenCopper = logicalCopper && bakedCopperVisible && !data.linkedAssemblyNet;
      material.opacity = hiddenCopper ? 0 : material.userData.assemblyBaseOpacity * (opacity[data.layer] ?? 1);
      material.transparent = material.opacity < 1;
      if (logicalCopper) { material.colorWrite = !hiddenCopper; material.depthWrite = !hiddenCopper && material.opacity === 1; }
    }
  });
}
