// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { ParsedBoard, ParsedPad, Point } from "./boardParser";
import { orderedCopperLayerNames } from "./boardParser";
import { batchAssemblyCopper } from "./assemblyCopperBatches";
import { configureImportedMaterial } from "./boardSurfaceMaterials";
import { tagImportedBoardLayers } from "./importedBoardLayers";
import { componentMountIndex, componentReferenceLookup } from "./componentSceneIndex";
import { batchAssemblyImported } from "./assemblyImportedBatches";
import { resolveAssemblyNetId } from "./assemblyNetIdentity";
import type { VirtualBoardVisual } from "./harnessVisualization";

export type BoardInstanceSceneOptions = { source?: ParsedBoard; boardScene?: THREE.Object3D | null; componentScene?: THREE.Object3D | null; showSmd?: boolean; showTht?: boolean };
export type BoardInstanceSceneResult = { group: THREE.Group; pickables: THREE.Object3D[] };
const GAP = 0.012;

function open(points: Point[]) { const last = points[points.length - 1]; return points.length > 1 && points[0][0] === last[0] && points[0][1] === last[1] ? points.slice(0, -1) : points; }
function shape(points: Point[], center: readonly [number, number, number]) {
  const result = new THREE.Shape();
  open(points).forEach(([x, y], i) => i ? result.lineTo(x - center[0], y - center[1]) : result.moveTo(x - center[0], y - center[1]));
  result.closePath(); return result;
}
function outline(source: ParsedBoard, center: readonly [number, number, number]) {
  const fallback: Point[] = [[source.bounds.minX, source.bounds.minY], [source.bounds.maxX, source.bounds.minY], [source.bounds.maxX, source.bounds.maxY], [source.bounds.minX, source.bounds.maxY]];
  const loops = source.outlineLoops.filter(loop => open(loop).length >= 3);
  const result = shape(loops[0] ?? fallback, center);
  loops.slice(1).forEach(loop => result.holes.push(shape(loop, center))); return result;
}
function layers(source: ParsedBoard) {
  return orderedCopperLayerNames(source.layerDefinitions, [...source.layers, ...source.tracks.map(x => x.layer), ...source.zones.map(x => x.layer), ...source.pads.flatMap(x => x.layers), ...source.vias.flatMap(x => x.layers)], source.stackup.map(x => x.name));
}
function layerZ(layer: string, ordered: string[], thickness: number) {
  // Outer copper clears laminate depth on both sides; inner copper stays inside.
  if (layer === "F.Cu") return thickness / 2 + GAP;
  if (layer === "B.Cu") return -thickness / 2 - GAP;
  return ordered.length < 2 ? thickness / 2 + GAP : thickness / 2 - Math.max(0, ordered.indexOf(layer)) * thickness / (ordered.length - 1);
}
function netId(board: VirtualBoardVisual, source: ParsedBoard, value?: string) {
  return resolveAssemblyNetId(source, board.netNamesById, board.netIdsByName, value) ?? undefined;
}
function tag(object: THREE.Object3D, board: VirtualBoardVisual, kind: string, id: string, layer?: string, net?: string) {
  object.userData = { ...object.userData, virtualBoard: board, boardOccurrenceId: board.id, sourceObjectId: id, sceneKind: kind, layer, assemblyNetId: net, canonicalNetId: net };
}
function copper(linked: boolean) {
  const material = new THREE.MeshStandardMaterial({ color: linked ? 0x55e5d5 : 0xc47b2b, metalness: .55, roughness: .42, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -1, polygonOffsetUnits: -1 });
  material.userData.assemblyBaseColor = 0xc47b2b;
  return material;
}
function capsule(length: number, width: number) {
  const r = Math.max(width / 2, .001), h = length / 2, result = new THREE.Shape();
  result.moveTo(-h, -r); result.lineTo(h, -r); result.absarc(h, 0, r, -Math.PI / 2, Math.PI / 2, false);
  result.lineTo(-h, r); result.absarc(-h, 0, r, Math.PI / 2, Math.PI * 1.5, false); return result;
}
function padShape(pad: ParsedPad) {
  const w = Math.max(pad.width || pad.size?.[0] || 0, .001), h = Math.max(pad.height || pad.size?.[1] || 0, .001);
  if (pad.shape === "circle") return new THREE.Shape().absarc(0, 0, w / 2, 0, Math.PI * 2, false);
  if (pad.shape === "oval") return capsule(Math.max(w - h, 0), Math.min(w, h));
  if (pad.shape === "custom" && pad.customPolygon && pad.customPolygon.length >= 3) return shape(pad.customPolygon, [0, 0, 0]);
  const result = new THREE.Shape(); result.moveTo(-w / 2, -h / 2); result.lineTo(w / 2, -h / 2); result.lineTo(w / 2, h / 2); result.lineTo(-w / 2, h / 2); result.closePath(); return result;
}

/** Convert KiCad GLB metres (X right, Y up, Z source-board Y) to board-local
 * millimetres. Keep the imported root untouched because it may carry its own
 * transform; the coordinate-system swap is an explicit parent matrix. */
export function kiCadLaminateMidplaneMm(source: ParsedBoard) {
  // KiCad's GLB zero is the bottom laminate surface, not the centered board
  // midplane used by procedural geometry. Outer copper/mask lie outside that
  // laminate; retaining their thickness here would shift component mount planes.
  const laminate = source.stackup.filter(row => !["F.Cu", "B.Cu", "F.Mask", "B.Mask"].includes(row.name))
    .reduce((sum, row) => sum + (row.thickness ?? 0), 0);
  return (laminate || 1.6) / 2;
}

export function normalizeKiCadScenes(boardScene: THREE.Object3D | null | undefined, componentScene: THREE.Object3D | null | undefined, source: ParsedBoard, center: readonly [number, number, number]) {
  const group = new THREE.Group(); group.name = "authoritative-board-geometry";
  for (const [kind, scene] of [["board", boardScene], ["components", componentScene]] as const) {
    if (!scene) continue;
    if (kind === "board") tagImportedBoardLayers(scene);
    const frame = new THREE.Group();
    frame.name = `kicad-${kind}-millimetre-frame`;
    frame.matrix.set(
      1000, 0, 0, -center[0],
      0, 0, 1000, -center[1],
      0, 1000, 0, -center[2],
      0, 0, 0, 1,
    );
    frame.matrixAutoUpdate = false;
    frame.userData.authoritativeModel = true;
    frame.userData.kiCadSceneKind = kind;
    scene.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
        object.userData.boardSurface = configureImportedMaterial(material, kind, object.name);
      }
      object.castShadow = kind === "components";
      object.receiveShadow = object.userData.boardSurface !== "soldermask";
    });
    frame.add(scene);
    group.add(frame);
  }
  group.userData.boardModelIncludesCopper = Boolean(boardScene && source.boardModelIncludesCopper); return group;
}

/** Mount late cache clones into an existing occurrence and update procedural visibility/picking. */
export function mountKiCadScenes(result: BoardInstanceSceneResult, board: VirtualBoardVisual, source: ParsedBoard, boardScene?: THREE.Object3D | null, componentScene?: THREE.Object3D | null) {
  const authoritative = normalizeKiCadScenes(boardScene, componentScene, source, board.localCenterMm);
  const resolvedRefs = new Set<string>();
  const components = new Map(source.components.map(component => [component.ref, component]));
  const referenceFromName = componentReferenceLookup(components.keys());
  const throughHole = componentMountIndex(source.pads);
  const visit = (object: THREE.Object3D, inheritedRef?: string) => {
    const ref = inheritedRef ?? referenceFromName(object.name);
    if (ref) {
      // A named exporter group is not evidence of resolved CAD geometry.
      if (object instanceof THREE.Mesh && (object.geometry.getAttribute("position")?.count ?? 0) > 0) resolvedRefs.add(ref);
      object.userData.componentRef = ref;
      const kind = throughHole.has(ref) ? "tht" : "smd";
      object.userData.componentMount = kind;
      if ((kind === "smd" && result.group.userData.showSmd === false)
        || (kind === "tht" && result.group.userData.showTht === false)) object.visible = false;
    }
    tag(object, board, ref ? "component-model" : "authoritative-model", object.name || "authoritative-model");
    if (object instanceof THREE.Mesh) result.pickables.push(object);
    object.children.forEach(child => visit(child, ref));
  };
  authoritative.children.forEach(scene => visit(scene));
  authoritative.children.forEach(frame => batchAssemblyImported(frame as THREE.Group));
  if (boardScene && source.boardModelIncludesCopper) result.group.traverse(object => {
    if (!["copper-zone", "copper-track", "copper-pad", "via-face", "via-barrel"].includes(String(object.userData.sceneKind)) || object.userData.linkedAssemblyNet) return;
    if (!(object instanceof THREE.Mesh)) return;
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) { material.transparent = true; material.opacity = 0; material.depthWrite = false; material.colorWrite = false; }
  });
  if (componentScene && resolvedRefs.size) result.group.traverse(object => {
    if (object.userData.sceneKind !== "component-placeholder" || !resolvedRefs.has(String(object.userData.componentRef))) return;
    object.userData.replacedByResolvedModel = true;
    object.visible = false;
  });
  result.group.add(authoritative);
  return authoritative;
}

function procedural(board: VirtualBoardVisual, source: ParsedBoard, selected: boolean, linked: Set<string>, omitCopper: boolean) {
  const group = new THREE.Group(), pickables: THREE.Object3D[] = [], center = board.localCenterMm;
  // The occurrence transform is expressed in the native board frame. Keep
  // imported solids at their exact source Z and place centered fallback shapes
  // around the same laminate midplane, including when no CAD solid resolves.
  group.position.z = kiCadLaminateMidplaneMm(source) - center[2];
  const stackupThickness = source.stackup.reduce((sum, x) => sum + (x.thickness ?? 0), 0);
  const thickness = board.thicknessMm ?? (stackupThickness || 1.6), ordered = layers(source);
  const substrate = new THREE.Mesh(new THREE.ExtrudeGeometry(outline(source, center), { depth: thickness, bevelEnabled: false, curveSegments: 8 }), new THREE.MeshStandardMaterial({ color: selected ? 0x6c913a : 0x315f45, roughness: .82 }));
  substrate.position.z = -thickness / 2; tag(substrate, board, "substrate", "board-substrate", "Edge.Cuts"); group.add(substrate); pickables.push(substrate);
  if (!omitCopper) {
    for (const zone of source.zones) { if (zone.points.length < 3) continue; const s = shape(zone.points, center); for (const hole of zone.holes ?? []) if (hole.length >= 3) s.holes.push(shape(hole, center)); const net = netId(board, source, zone.net); const mesh = new THREE.Mesh(new THREE.ShapeGeometry(s, 4), copper(Boolean(net && linked.has(net)))); mesh.position.z = layerZ(zone.layer, ordered, thickness); tag(mesh, board, "copper-zone", zone.id, zone.layer, net); mesh.userData.linkedAssemblyNet = Boolean(net && linked.has(net)); group.add(mesh); pickables.push(mesh); }
    // Render all retained tracks at imported width; assembly detail has no density truncation.
    for (const track of source.tracks) { const sx = track.start[0] - center[0], sy = track.start[1] - center[1], ex = track.end[0] - center[0], ey = track.end[1] - center[1], net = netId(board, source, track.net); const mesh = new THREE.Mesh(new THREE.ShapeGeometry(capsule(Math.hypot(ex - sx, ey - sy), track.width), 8), copper(Boolean(net && linked.has(net)))); mesh.position.set((sx + ex) / 2, (sy + ey) / 2, layerZ(track.layer, ordered, thickness)); mesh.rotation.z = Math.atan2(ey - sy, ex - sx); tag(mesh, board, "copper-track", track.id, track.layer, net); mesh.userData.linkedAssemblyNet = Boolean(net && linked.has(net)); group.add(mesh); pickables.push(mesh); }
    for (const pad of source.pads) for (const layer of ordered.filter(x => pad.layers.includes(x) || pad.layers.includes("*.Cu") || pad.layers.includes("F&B.Cu") && (x === "F.Cu" || x === "B.Cu"))) { const net = netId(board, source, pad.net), mesh = new THREE.Mesh(new THREE.ShapeGeometry(padShape(pad), 8), copper(Boolean(net && linked.has(net)))); mesh.position.set(pad.at[0] - center[0], pad.at[1] - center[1], layerZ(layer, ordered, thickness)); mesh.rotation.z = -pad.rotation * Math.PI / 180; tag(mesh, board, "copper-pad", `${pad.id}:${layer}`, layer, net); mesh.userData.linkedAssemblyNet = Boolean(net && linked.has(net)); group.add(mesh); pickables.push(mesh); }
    for (const via of source.vias) { const outer = Math.max(via.size / 2, .001), inner = Math.min(Math.max(via.drill / 2, 0), outer), net = netId(board, source, via.net); const ring = new THREE.Mesh(new THREE.RingGeometry(inner, outer, 24), copper(Boolean(net && linked.has(net)))); ring.position.set(via.at[0] - center[0], via.at[1] - center[1], thickness / 2 + GAP); tag(ring, board, "via-face", via.id, "through", net); ring.userData.linkedAssemblyNet = Boolean(net && linked.has(net)); group.add(ring); pickables.push(ring); if (inner > 0) { const barrel = new THREE.Mesh(new THREE.CylinderGeometry(inner, inner, thickness + .035, 20, 1, true), copper(false)); barrel.rotation.x = Math.PI / 2; barrel.position.set(ring.position.x, ring.position.y, 0); tag(barrel, board, "via-barrel", `${via.id}:barrel`, "through", net); barrel.userData.linkedAssemblyNet = Boolean(net && linked.has(net)); group.add(barrel); } }
  }
  const lines = new Map<string, number[]>();
  for (const drawing of source.drawings.filter(x => x.layer !== "Edge.Cuts")) { const z = drawing.layer.startsWith("B.") ? -thickness / 2 - GAP : thickness / 2 + GAP; if (drawing.filled && drawing.points.length >= 3) { const mesh = new THREE.Mesh(new THREE.ShapeGeometry(shape(drawing.points, center), 4), new THREE.MeshBasicMaterial({ color: drawing.layer.endsWith("SilkS") ? 0xf2eee1 : 0x7896a0, side: THREE.DoubleSide })); mesh.position.z = z; tag(mesh, board, "drawing", drawing.id, drawing.layer); group.add(mesh); continue; } const values = lines.get(drawing.layer) ?? []; for (let i = 0; i + 1 < drawing.points.length; i++) values.push(drawing.points[i][0] - center[0], drawing.points[i][1] - center[1], z, drawing.points[i + 1][0] - center[0], drawing.points[i + 1][1] - center[1], z); lines.set(drawing.layer, values); }
  lines.forEach((values, layer) => { const geometry = new THREE.BufferGeometry(); geometry.setAttribute("position", new THREE.Float32BufferAttribute(values, 3)); const object = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color: layer.endsWith("SilkS") ? 0xf2eee1 : 0x7896a0 })); tag(object, board, "drawing", `${layer}:drawings`, layer); group.add(object); });
  batchAssemblyCopper(group);
  return { group, pickables, thickness };
}

/** Complete board occurrence in board-local millimetres followed by the retained assembly transform. */
export function boardInstanceScene(board: VirtualBoardVisual, selected: boolean, linked: string[], sourceOrOptions: ParsedBoard | BoardInstanceSceneOptions = {}): BoardInstanceSceneResult {
  const group = new THREE.Group(); group.name = `board-instance:${board.id}`; group.matrix.set(...board.transform as [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number]); group.matrix.multiply(new THREE.Matrix4().makeTranslation(...board.localCenterMm)); group.userData.boardLocalCenterMm = board.localCenterMm; group.userData.virtualBoard = board; group.matrixAutoUpdate = false;
  const options: BoardInstanceSceneOptions = "tracks" in sourceOrOptions ? { source: sourceOrOptions } : sourceOrOptions;
  group.userData.showSmd = options.showSmd;
  group.userData.showTht = options.showTht;
  const pickables: THREE.Object3D[] = [], source = options.source;
  if (!source) { const body = new THREE.Mesh(new THREE.BoxGeometry(board.widthMm, board.heightMm, board.thicknessMm ?? 1.6), new THREE.MeshBasicMaterial({ color: selected ? 0x658930 : 0x185841 })); tag(body, board, "substrate", "board-envelope"); group.add(body); pickables.push(body); return { group, pickables }; }
  const generated = procedural(board, source, selected, new Set(linked), false); group.add(generated.group);
  const throughHole = componentMountIndex(source.pads);
  for (const component of source.components) {
    const kind = throughHole.has(component.ref) ? "tht" : "smd";
    if (kind === "smd" && options.showSmd === false || kind === "tht" && options.showTht === false) continue;
    const bounds = component.bodyBounds ?? component.courtyardBounds;
    const width = Math.max(bounds ? bounds.maxX - bounds.minX : component.width, .4);
    const height = Math.max(bounds ? bounds.maxY - bounds.minY : component.height, .4), bodyHeight = kind === "tht" ? 3.2 : 1.25;
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(width, height, bodyHeight), new THREE.MeshStandardMaterial({ color: 0x343940, roughness: .58 }));
    const bottom = component.layer.startsWith("B.");
    mesh.position.set(component.at[0] - board.localCenterMm[0], component.at[1] - board.localCenterMm[1],
      kiCadLaminateMidplaneMm(source) - board.localCenterMm[2] + (bottom ? -1 : 1) * (generated.thickness / 2 + bodyHeight / 2 + GAP));
    // Native board XY has Y down; the enclosing viewport applies its Y flip.
    mesh.rotation.z = -component.rotation * Math.PI / 180;
    mesh.userData.componentMount = kind; mesh.userData.componentRef = component.ref;
    mesh.userData.geometryStatus = "fallback-not-cad";
    tag(mesh, board, "component-placeholder", component.id, component.layer); group.add(mesh); pickables.push(mesh);
  }
  pickables.push(...generated.pickables);
  const result = { group, pickables };
  if (options.boardScene || options.componentScene) mountKiCadScenes(result, board, source, options.boardScene, options.componentScene);
  return result;
}
