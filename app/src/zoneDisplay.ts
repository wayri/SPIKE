// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";

/** Presentation only; never changes conductor geometry or solver results. */
export type ZoneDisplayMode = "filled" | "transparent" | "outline";
export const zoneFillOpacity = (mode: ZoneDisplayMode) => mode === "outline" ? 0 : mode === "transparent" ? .18 : 1;
export const zoneSceneKind = (object: THREE.Object3D) => String(object.userData.sceneKind ?? String(object.userData.spikeSceneIdentity ?? "").split(":")[1] ?? "");
export const zoneSvgStyle = (mode: ZoneDisplayMode, color: string, opacity: number) => ({
  fill: mode === "outline" ? "none" : color, fillOpacity: opacity * zoneFillOpacity(mode),
  stroke: mode === "filled" ? "none" : color, strokeOpacity: opacity,
  strokeWidth: .12, fillRule: "evenodd" as const,
});

/** Triangle boundary edges, including hole perimeters; never wireframe diagonals.
 * Exact vertex positions join indexed and nonindexed retained triangulations. */
export function zoneBoundaryGeometry(geometry: THREE.BufferGeometry): THREE.BufferGeometry {
  const position = geometry.getAttribute("position"), indices = geometry.index;
  const edges = new Map<string, { count: number; a: number; b: number }>();
  const vertex = (i: number) => `${position.getX(i)},${position.getY(i)},${position.getZ(i)}`;
  const count = indices?.count ?? position.count;
  const ends: number[] = geometry.userData.zoneTriangleEnds ?? [count];
  let polygon = 0;
  for (let i = 0; i + 2 < count; i += 3) {
    while (polygon + 1 < ends.length && i >= ends[polygon]) polygon++;
    const face = [0, 1, 2].map(offset => indices ? indices.getX(i + offset) : i + offset);
    for (let edge = 0; edge < 3; edge++) {
      const a = face[edge], b = face[(edge + 1) % 3], ak = vertex(a), bk = vertex(b);
      const key = `${polygon}:` + (ak < bk ? `${ak}|${bk}` : `${bk}|${ak}`);
      const existing = edges.get(key);
      if (existing) existing.count++; else edges.set(key, { count: 1, a, b });
    }
  }
  const points: number[] = [];
  for (const { count: uses, a, b } of edges.values()) if (uses === 1) {
    for (const index of [a, b]) points.push(position.getX(index), position.getY(index), position.getZ(index));
  }
  return new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
}

type MaterialState = { material: THREE.Material; opacity: number; transparent: boolean; depthWrite: boolean; colorWrite: boolean };
const stateByRoot = new WeakMap<THREE.Object3D, { materials: MaterialState[]; visibility: { object: THREE.Object3D; visible: boolean }[] }>();
const boundaryByMesh = new WeakMap<THREE.Mesh, THREE.LineSegments<THREE.BufferGeometry, THREE.LineBasicMaterial>>();

/** Restore before the owner's ordinary visibility/opacity pass (which may cache). */
export function restoreZoneDisplayScene(root: THREE.Object3D) {
  const state = stateByRoot.get(root);
  if (!state) return;
  for (const { material, ...base } of state.materials) {
    if (material.transparent !== base.transparent) material.needsUpdate = true;
    Object.assign(material, base);
  }
  for (const { object, visible } of state.visibility) object.visible = visible;
  stateByRoot.delete(root);
}

/** Apply after ordinary presentation. Native KiCad copper merges zones, tracks
 * and pads, so alternate modes use known retained copper instead of guessing.
 * Boundaries are owned children and disposed with the parent scene. */
export function applyZoneDisplayScene(root: THREE.Object3D, mode: ZoneDisplayMode,
  layerOpacity: Record<string, number> = {}, replaceImportedCopper = false) {
  const state = { materials: [] as MaterialState[], visibility: [] as { object: THREE.Object3D; visible: boolean }[] };
  stateByRoot.set(root, state);
  const objects: THREE.Object3D[] = [];
  root.traverse(object => { if (!object.userData.zoneDisplayBoundary) objects.push(object); });
  const covered = new Set(objects.map(object => object.userData.importedBoardLayer as string | undefined)
    .filter((layer): layer is string => Boolean(layer && (layer.endsWith(".Cu") || layer === "through"))));
  const savedMaterials = new Set<THREE.Material>();
  const fallbackMaterials = new Set<THREE.Material>();
  const zoneMaterialOpacity = new Map<THREE.Material, number>();
  const save = (material: THREE.Material) => {
    if (savedMaterials.has(material)) return;
    savedMaterials.add(material);
    state.materials.push({ material, opacity: material.opacity, transparent: material.transparent, depthWrite: material.depthWrite, colorWrite: material.colorWrite });
  };
  for (const object of objects) {
    const data = object.userData, kind = zoneSceneKind(object);
    if (mode !== "filled" && covered.has(data.importedBoardLayer)) {
      state.visibility.push({ object, visible: object.visible }); object.visible = false;
    }
    if (!(object instanceof THREE.Mesh) || data.pickingProxy) continue;
    const copperPolygon = kind === "copper-zone" || kind === "drawing" && String(data.layer).endsWith(".Cu") && object.geometry.type === "ShapeGeometry";
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    if (mode !== "filled" && replaceImportedCopper && covered.has(data.layer)
      && (kind.startsWith("copper-") || kind.startsWith("via-") || copperPolygon)) {
      for (const material of materials) {
        if (fallbackMaterials.has(material)) continue;
        fallbackMaterials.add(material);
        save(material);
        const focus = root.userData.assemblyNetFocusActive && !data.linkedAssemblyNet ? .28 : 1;
        material.opacity = (material.userData.assemblyBaseOpacity ?? 1) * (layerOpacity[data.layer] ?? 1) * focus;
        material.colorWrite = true; material.transparent = material.opacity < .999; material.depthWrite = !material.transparent;
      }
    }
    if (!copperPolygon) continue;
    for (const material of materials) if (!zoneMaterialOpacity.has(material)) zoneMaterialOpacity.set(material, material.opacity);
    let boundary = boundaryByMesh.get(object);
    if (!boundary && mode !== "filled") {
      boundary = new THREE.LineSegments(zoneBoundaryGeometry(object.geometry), new THREE.LineBasicMaterial({ depthWrite: false, transparent: true }));
      boundary.userData.zoneDisplayBoundary = true;
      boundary.renderOrder = object.renderOrder + 1;
      boundary.raycast = () => {};
      object.add(boundary); boundaryByMesh.set(object, boundary);
    }
    if (boundary) {
      boundary.visible = mode !== "filled";
      const material = materials[0];
      const color = (material as THREE.MeshStandardMaterial).color;
      if (color) boundary.material.color.copy(color);
      boundary.material.opacity = zoneMaterialOpacity.get(material) ?? material.opacity;
      boundary.material.depthTest = material.depthTest;
    }
    if (mode !== "filled") for (const material of materials) {
      save(material);
      const wasTransparent = material.transparent;
      material.opacity = (zoneMaterialOpacity.get(material) ?? material.opacity) * zoneFillOpacity(mode);
      material.transparent = true; material.depthWrite = false;
      if (!wasTransparent) material.needsUpdate = true;
      if (mode === "outline") material.colorWrite = false;
    }
  }
}
