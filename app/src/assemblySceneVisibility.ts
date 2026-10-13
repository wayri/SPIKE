// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { ParsedBoard } from "./boardParser";
import { importedBoardLayerVisible } from "./importedBoardLayers";

const selectionState = new WeakMap<THREE.Object3D, { selected: boolean; focusActive: boolean; linked: readonly string[]; children: number }>();
const visibilityState = new WeakMap<THREE.Object3D, { source: ParsedBoard; layers: Record<string, boolean>; opacity: Record<string, number>; showVias: boolean; children: number; revision: number }>();
const sameSettings = (a: Record<string, unknown>, b: Record<string, unknown>) => Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(key => a[key] === b[key]);

export function updateAssemblySceneSelection(group: THREE.Object3D, selected: boolean, linked: readonly string[], focusActive = linked.length > 0) {
  const previous = selectionState.get(group);
  if (previous && previous.children === group.children.length && previous.selected === selected && previous.focusActive === focusActive
    && previous.linked.length === linked.length && previous.linked.every((net, i) => net === linked[i])) return 0;
  selectionState.set(group, { selected, focusActive, linked: [...linked], children: group.children.length });
  group.userData.assemblySelectionRevision = (group.userData.assemblySelectionRevision ?? 0) + 1;
  group.userData.assemblyNetFocusActive = focusActive;
  const nets = new Set(linked);
  let visited = 0;
  group.traverse(object => {
    visited++;
    const kind = String(object.userData.sceneKind ?? "");
    const copper = kind.startsWith("copper-") || kind.startsWith("via-") || Boolean(object.userData.importedBoardLayer?.endsWith(".Cu") || object.userData.importedBoardLayer === "through");
    if (copper) object.userData.linkedAssemblyNet = nets.has(object.userData.canonicalNetId);
    if (!(object instanceof THREE.Mesh) || (!copper && kind !== "substrate")) return;
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (!(material instanceof THREE.MeshStandardMaterial || material instanceof THREE.MeshBasicMaterial)) continue;
      material.userData.assemblyBaseColor ??= material.color.getHex();
      material.userData.assemblySelectionDepthTest ??= material.depthTest;
      material.userData.assemblySelectionToneMapped ??= material.toneMapped;
      if(copper) {
        const linkedNet=Boolean(object.userData.linkedAssemblyNet);
        object.userData.assemblySelectionRenderOrder ??= object.renderOrder;
        object.renderOrder=linkedNet?390:object.userData.assemblySelectionRenderOrder;
        material.depthTest=linkedNet?false:material.userData.assemblySelectionDepthTest;
        material.toneMapped=linkedNet?false:material.userData.assemblySelectionToneMapped;
        if(material instanceof THREE.MeshStandardMaterial) {
          material.userData.assemblySelectionEmissive ??= material.emissive.getHex();
          material.userData.assemblySelectionIntensity ??= material.emissiveIntensity;
          material.emissive.setHex(linkedNet?0x55e5d5:material.userData.assemblySelectionEmissive);
          material.emissiveIntensity=linkedNet?.65:material.userData.assemblySelectionIntensity;
        }
      }
      material.color.setHex(copper && object.userData.linkedAssemblyNet ? 0x55e5d5
        : copper && focusActive ? 0x667076 : kind === "substrate" && selected ? 0x6c913a : material.userData.assemblyBaseColor);
    }
  });
  return visited;
}

/** Update occurrence display only; layer controls never change retained geometry. */
export function applyAssemblySceneVisibility(group: THREE.Object3D, source: ParsedBoard,
  layers: Record<string, boolean>, opacity: Record<string, number>, showVias: boolean) {
  const revision = group.userData.assemblySelectionRevision ?? 0;
  const previous = visibilityState.get(group);
  if (previous && previous.source === source && previous.showVias === showVias && previous.children === group.children.length
    && previous.revision === revision && sameSettings(previous.layers, layers) && sameSettings(previous.opacity, opacity)) return 0;
  visibilityState.set(group, { source, layers: { ...layers }, opacity: { ...opacity }, showVias, children: group.children.length, revision });
  const copper = source.layers.filter(layer => layer.endsWith(".Cu"));
  const covered = new Set<string>();
  group.traverse(object => {
    const layer = object.userData.importedBoardLayer as string | undefined;
    if (layer && !(source.boardModelIncludesCopper === false && (layer.endsWith(".Cu") || layer === "through"))) covered.add(layer);
  });
  let visited = 0;
  group.traverse(object => {
    visited++;
    const data = object.userData;
    // Board body is a surface, never a parent gate for copper/mask/silk.
    if (data.kiCadSceneKind === "board") object.visible = covered.size > 0;
    const kind = String(data.sceneKind ?? "");
    if (data.importedBoardUnaddressable) object.visible = false;
    else if (data.importedBoardLayer) object.visible = covered.has(data.importedBoardLayer)
      && importedBoardLayerVisible(data.importedBoardLayer, layers, copper, showVias);
    else if (kind === "component-placeholder" && data.replacedByResolvedModel) object.visible = false;
    else if (kind === "component-placeholder") object.visible = true;
    else if (kind === "substrate") object.visible = layers["Board body"] !== false && !covered.has("Board body");
    else if (kind.startsWith("via-")) object.visible = showVias && copper.some(layer => layers[layer] !== false);
    else if (data.layer && !data.authoritativeModel && kind !== "component-model") object.visible = layers[data.layer] !== false;
    if (!(object instanceof THREE.Mesh || object instanceof THREE.LineSegments)) return;
    const logicalCopper = kind.startsWith("copper-") || kind.startsWith("via-");
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      material.userData.assemblyBaseOpacity ??= logicalCopper ? 1 : material.opacity;
      material.userData.assemblyBaseDepthWrite ??= logicalCopper ? true : material.depthWrite;
      const hiddenCopper = logicalCopper && covered.has(data.layer) && source.boardModelIncludesCopper && !data.linkedAssemblyNet;
      const hiddenDrawing = kind === "drawing" && covered.has(data.layer);
      const component = kind === "component-placeholder" || kind === "component-model";
      const value = component ? 1 : opacity[data.importedBoardLayer ?? (kind === "substrate" ? "Board body" : data.layer)] ?? 1;
      const layerOpacity = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 1;
      const focusCopper = logicalCopper || Boolean(data.importedBoardLayer?.endsWith(".Cu") || data.importedBoardLayer === "through");
      const netFocusOpacity = group.userData.assemblyNetFocusActive && focusCopper && !data.linkedAssemblyNet ? .28 : 1;
      material.opacity = hiddenCopper || hiddenDrawing ? 0 : material.userData.assemblyBaseOpacity * layerOpacity * netFocusOpacity;
      const wasTransparent = material.transparent;
      material.transparent = material.opacity < 1;
      material.depthWrite = material.userData.assemblyBaseDepthWrite && material.opacity >= .999;
      if (material.transparent !== wasTransparent) material.needsUpdate = true;
      if (logicalCopper || hiddenDrawing) { material.colorWrite = !hiddenCopper && !hiddenDrawing; material.depthWrite = material.colorWrite && material.opacity === 1; }
    }
  });
  return visited;
}
