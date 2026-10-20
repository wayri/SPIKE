// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { EMViewportData, EMViewportSettings } from "./emViewportResults";

export type EMBoardTransform = { centerX: number; centerY: number; scale: number; zOffsetMm?: number; angularAnchorMm?: readonly [number, number] };
const MAX_GLYPHS = 2048;
const UP = new THREE.Vector3(0, 0, 1);
const SIGNED_NEUTRAL = new THREE.Color(0xf5f5f2);
const SIGNED_NEGATIVE = new THREE.Color(0x2466ce);
const SIGNED_POSITIVE = new THREE.Color(0xda491e);

function point(position: readonly number[], transform: EMBoardTransform): THREE.Vector3 {
  return new THREE.Vector3((position[0]-transform.centerX)*transform.scale,
    (transform.centerY-position[1])*transform.scale, (position[2]+(transform.zOffsetMm ?? 0))*transform.scale);
}

/** Zero is the neutral midpoint for a signed field, including an asymmetric range. */
function colour(value: number, range: readonly number[], target = new THREE.Color()): THREE.Color {
  if (range[0] < 0 && range[1] > 0) {
    const ratio = Math.min(1, Math.abs(value)/Math.max(Math.abs(range[0]), Math.abs(range[1])));
    return target.copy(SIGNED_NEUTRAL).lerp(value < 0 ? SIGNED_NEGATIVE : SIGNED_POSITIVE, ratio);
  }
  const ratio = range[1] > range[0] ? THREE.MathUtils.clamp((value-range[0])/(range[1]-range[0]), 0, 1) : .5;
  return target.setHSL((1-ratio)*.65, .88, .52);
}
export function emViewportScaleGradient(range: readonly number[]): string {
  const stops = Array.from({length:17}, (_,i) => `${colour(range[0]+i/16*(range[1]-range[0]),range).getStyle()} ${i/16*100}%`);
  return `linear-gradient(to right, ${stops.join(',')})`;
}

function isSample(data: EMViewportData, index: number): boolean {
  const value = data.values[index];
  return Number.isInteger(index) && index >= 0 && index < data.positionsMm.length
    && typeof value === "number" && Number.isFinite(value)
    && data.positionsMm[index]?.length === 3 && data.positionsMm[index].every(Number.isFinite);
}

function sampleMask(data: EMViewportData): Uint8Array {
  const admitted = new Uint8Array(data.positionsMm.length);
  for (let index = 0; index < admitted.length; index++) admitted[index] = isSample(data, index) ? 1 : 0;
  return admitted;
}

function triangles(data: EMViewportData, admittedSamples: Uint8Array): number[] {
  const admitted: number[] = [];
  for (let i = 0; i+2 < data.indices.length; i += 3) {
    const a = data.indices[i], b = data.indices[i+1], c = data.indices[i+2];
    if (admittedSamples[a] && admittedSamples[b] && admittedSamples[c] && a !== b && a !== c && b !== c) admitted.push(a, b, c);
  }
  return admitted;
}

function tag(object: THREE.Object3D, name: string, metadata: Record<string, unknown> = {}): void {
  object.name = name;
  object.userData = { emOverlay: true, ...metadata };
  object.renderOrder = 130;
}

function surface(data: EMViewportData, admittedSamples: Uint8Array, transform: EMBoardTransform, opacity: number): THREE.Mesh | null {
  const faces = triangles(data, admittedSamples);
  if (!faces.length) return null;
  const positions = new Float32Array(data.positionsMm.length*3);
  const colours = new Float32Array(positions.length);
  const color = new THREE.Color();
  for (let i = 0; i < data.positionsMm.length; i++) {
    if (!admittedSamples[i]) continue;
    const position = data.positionsMm[i], offset = i*3;
    positions[offset] = (position[0]-transform.centerX)*transform.scale;
    positions[offset+1] = (transform.centerY-position[1])*transform.scale;
    positions[offset+2] = (position[2]+(transform.zOffsetMm ?? 0))*transform.scale;
    colour(data.values[i] as number, data.range, color).toArray(colours, offset);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colours, 3));
  geometry.setIndex(faces);
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ vertexColors: true,
    side: THREE.DoubleSide, transparent: true, opacity, depthWrite: false, polygonOffset: true,
    polygonOffsetFactor: -1, polygonOffsetUnits: -1 }));
  tag(mesh, "EM scalar surface", { emSampleIndices: data.positionsMm.map((_, index) => index),
    emDisplayInterpolation: true, emDomain: data.domain });
  return mesh;
}

function samplePoints(data: EMViewportData, admittedSamples: Uint8Array, transform: EMBoardTransform, opacity: number): THREE.Points | null {
  const ids: number[] = [];
  for (let index = 0; index < admittedSamples.length; index++) if (admittedSamples[index]) ids.push(index);
  if (!ids.length) return null;
  const positions = new Float32Array(ids.length*3), colours = new Float32Array(positions.length);
  ids.forEach((index, order) => {
    point(data.positionsMm[index], transform).toArray(positions, order*3);
    colour(data.values[index] as number, data.range).toArray(colours, order*3);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colours, 3));
  const points = new THREE.Points(geometry, new THREE.PointsMaterial({ size: 5, sizeAttenuation: false,
    vertexColors: true, transparent: true, opacity, depthWrite: false }));
  tag(points, "EM solved samples", { emSampleIndices: ids, emDomain: data.domain });
  return points;
}

function glyphSize(data: EMViewportData, transform: EMBoardTransform): number {
  const lower = [Infinity, Infinity, Infinity], upper = [-Infinity, -Infinity, -Infinity];
  for (const position of data.positionsMm) for (let axis = 0; axis < 3; axis++) {
    if (!Number.isFinite(position[axis])) continue;
    lower[axis] = Math.min(lower[axis], position[axis]);
    upper[axis] = Math.max(upper[axis], position[axis]);
  }
  let span = 0;
  for (let axis = 0; axis < 3; axis++) if (Number.isFinite(lower[axis])) span = Math.max(span, upper[axis]-lower[axis]);
  return Math.max(span*transform.scale/Math.max(10, Math.sqrt(data.positionsMm.length)), .015);
}

function vectorLines(data: EMViewportData, admittedSamples: Uint8Array, transform: EMBoardTransform, opacity: number): THREE.LineSegments | null {
  const ids = data.positionsMm.map((_, index) => index).filter(index => admittedSamples[index]
    && data.directions[index]?.length === 3 && data.directions[index]!.every(Number.isFinite)
    && Math.hypot(...data.directions[index]!) > 0);
  if (!ids.length) return null;
  const stride = Math.max(1, Math.ceil(ids.length/MAX_GLYPHS));
  const displayed = ids.filter((_, index) => index % stride === 0);
  const positions: number[] = [], colours: number[] = [], mapping: number[] = [];
  const length = glyphSize(data, transform)*.9;
  for (const index of displayed) {
    const origin = point(data.positionsMm[index], transform);
    const raw = data.directions[index]!;
    const direction = new THREE.Vector3(raw[0], -raw[1], raw[2]).normalize();
    const end = origin.clone().addScaledVector(direction, length);
    const reference = Math.abs(direction.dot(UP)) < .9 ? UP : new THREE.Vector3(1, 0, 0);
    const perpendicular = direction.clone().cross(reference).normalize();
    const base = end.clone().addScaledVector(direction, -length*.3);
    const left = base.clone().addScaledVector(perpendicular, length*.16);
    const right = base.clone().addScaledVector(perpendicular, -length*.16);
    const color = colour(data.values[index] as number, data.range);
    for (const position of [origin, end, end, left, end, right]) {
      positions.push(...position.toArray()); colours.push(...color.toArray()); mapping.push(index);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colours, 3));
  const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ vertexColors: true,
    transparent: true, opacity, depthWrite: false }));
  tag(lines, "EM normalized direction arrows", { emSampleIndices: mapping, emNormalizedDirections: true,
    emGlyphDecimated: displayed.length < ids.length, emGlyphCount: displayed.length });
  return lines;
}

function contourLines(data: EMViewportData, admittedSamples: Uint8Array, transform: EMBoardTransform, opacity: number): THREE.LineSegments | null {
  const faces = triangles(data, admittedSamples), positions: number[] = [], colours: number[] = [], mapping: number[] = [];
  if (!faces.length || data.range[1] <= data.range[0]) return null;
  const zOffset = transform.zOffsetMm ?? 0;
  for (let step = 1; step < 8; step++) {
    const level = data.range[0]+(data.range[1]-data.range[0])*step/8;
    const color = colour(level, data.range);
    for (let i = 0; i < faces.length; i += 3) {
      const a = faces[i], b = faces[i+1], c = faces[i+2];
      const face = [a, b, c];
      let count = 0, firstX = 0, firstY = 0, firstZ = 0, firstIndex = -1;
      let secondX = 0, secondY = 0, secondZ = 0, secondIndex = -1;
      for (let edge = 0; edge < 3; edge++) {
        const first = face[edge], second = face[(edge+1)%3];
        const va = data.values[first] as number, vb = data.values[second] as number;
        if (!((va < level && vb >= level) || (vb < level && va >= level))) continue;
        const ratio = (level-va)/(vb-va);
        const pa = data.positionsMm[first], pb = data.positionsMm[second];
        const x = (pa[0]+(pb[0]-pa[0])*ratio-transform.centerX)*transform.scale;
        const y = (transform.centerY-(pa[1]+(pb[1]-pa[1])*ratio))*transform.scale;
        const z = (pa[2]+(pb[2]-pa[2])*ratio+zOffset)*transform.scale;
        if (count && (x-firstX)**2+(y-firstY)**2+(z-firstZ)**2 < 1e-18) continue;
        const sampleIndex = ratio <= .5 ? first : second;
        if (!count) { firstX=x; firstY=y; firstZ=z; firstIndex=sampleIndex; }
        else { secondX=x; secondY=y; secondZ=z; secondIndex=sampleIndex; }
        count++;
      }
      if (count !== 2) continue;
      positions.push(firstX,firstY,firstZ,secondX,secondY,secondZ);
      colours.push(color.r,color.g,color.b,color.r,color.g,color.b);
      mapping.push(firstIndex,secondIndex);
    }
  }
  if (!positions.length) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colours, 3));
  const lines = new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ vertexColors: true,
    transparent: true, opacity, depthWrite: false }));
  tag(lines, "EM display contours", { emSampleIndices: mapping, emDisplayInterpolation: true });
  return lines;
}

function markers(data: EMViewportData, admittedSamples: Uint8Array, settings: EMViewportSettings, transform: EMBoardTransform, kind: "node" | "antinode"): THREE.InstancedMesh | null {
  if (!(kind === "node" ? settings.nodes : settings.antinodes)) return null;
  const ids = data.highlights.map((entry, index) => entry === kind && admittedSamples[index] ? index : -1).filter(index => index >= 0);
  if (!ids.length) return null;
  const displayed = ids.filter((_, index) => index % Math.max(1, Math.ceil(ids.length/MAX_GLYPHS)) === 0);
  const material = new THREE.MeshBasicMaterial({ color: kind === "node" ? 0x15d9ff : 0xffd438, transparent: true, opacity: .95 });
  const mesh = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 8, 6), material, displayed.length);
  const matrix = new THREE.Matrix4(), radius = glyphSize(data, transform)*.18;
  displayed.forEach((index, order) => {
    matrix.makeScale(radius, radius, radius).setPosition(point(data.positionsMm[index], transform));
    mesh.setMatrixAt(order, matrix);
  });
  mesh.instanceMatrix.needsUpdate = true;
  tag(mesh, `EM ${kind} threshold candidates`, { emSampleIndices: displayed, emHighlightKind: kind,
    emThresholdCandidates: true, emGlyphDecimated: displayed.length < ids.length });
  mesh.renderOrder = 135;
  return mesh;
}

function structureMesh(data: EMViewportData, transform: EMBoardTransform): THREE.Mesh | null {
  const structure = data.structure;
  if (!structure || structure.vertices_mm.length > 120000 || structure.triangles.length > 40000) return null;
  if (structure.vertices_mm.some(value => value.length !== 3 || !value.every(Number.isFinite))
    || structure.triangles.some(face => face.length !== 3 || face.some(index => !Number.isInteger(index) || index < 0 || index >= structure.vertices_mm.length))) return null;
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(structure.vertices_mm.length*3);
  structure.vertices_mm.forEach((value, index) => point(value, transform).toArray(positions, index*3));
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(structure.triangles.flat());
  geometry.computeVertexNormals();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ color: 0x8596a7, side: THREE.DoubleSide,
    transparent: true, opacity: .22, depthWrite: false }));
  tag(mesh, "EM numerical STEP structure", { emStructure: true, emCoordinatesAlreadyPlaced: true });
  mesh.renderOrder = 125;
  return mesh;
}

/** Fields use their physical plane; angular patterns use the supplied display sphere. */
export function buildEMViewportScene(data: EMViewportData, settings: EMViewportSettings, transform: EMBoardTransform): THREE.Group {
  if (!Number.isFinite(transform.scale) || transform.scale <= 0 || !Number.isFinite(transform.centerX) || !Number.isFinite(transform.centerY) || !Number.isFinite(transform.zOffsetMm ?? 0)) throw new Error("EM overlay requires a finite board transform.");
  const group = new THREE.Group();
  tag(group, "EM solved result overlay", { emDomain: data.domain, emLabel: data.label, emUnit: data.unit,
    emFrequencyHz: data.frequencyHz, emNotices: data.notices, emDisplaySphere: data.domain === "angular" });
  if (settings.visible === false) return group;
  // Angular samples without a recorded origin are display-relative, not PCB coordinates.
  // Explicit solver origins and spatial samples retain their original physical frame.
  const anchor = transform.angularAnchorMm ?? [transform.centerX, transform.centerY];
  if (data.domain === "angular" && data.angularNeedsBoardAnchor && !anchor.every(Number.isFinite)) throw new Error("EM overlay requires a finite angular anchor.");
  const sampleTransform = data.domain === "angular" && data.angularNeedsBoardAnchor
    ? { ...transform, centerX: transform.centerX - anchor[0], centerY: transform.centerY - anchor[1] } : transform;
  const admittedSamples = sampleMask(data);
  const opacity = Number.isFinite(settings.opacity) ? THREE.MathUtils.clamp(settings.opacity, 0, 1) : .65;
  const main = data.assemblyFrame && ["surface", "contours"].includes(settings.style) ? samplePoints(data, admittedSamples, sampleTransform, opacity) : settings.style === "surface" ? surface(data, admittedSamples, sampleTransform, opacity)
    : settings.style === "vectors" ? vectorLines(data, admittedSamples, sampleTransform, opacity)
      : settings.style === "contours" ? contourLines(data, admittedSamples, sampleTransform, opacity) : samplePoints(data, admittedSamples, sampleTransform, opacity);
  if (main) group.add(main);
  for (const kind of ["node", "antinode"] as const) {
    const marker = markers(data, admittedSamples, settings, sampleTransform, kind);
    if (marker) group.add(marker);
  }
  if (settings.showStructure) {
    const structure = structureMesh(data, transform);
    if (structure) group.add(structure);
  }
  if (admittedSamples[settings.selectedSample]) {
    const selected = new THREE.Mesh(new THREE.SphereGeometry(glyphSize(data, transform)*.24, 12, 8),
      new THREE.MeshBasicMaterial({ color: 0xff51dc, wireframe: true, depthTest: false }));
    selected.position.copy(point(data.positionsMm[settings.selectedSample], sampleTransform));
    tag(selected, "EM selected solved sample", { emSampleIndex: settings.selectedSample });
    selected.renderOrder = 140;
    group.add(selected);
  }
  return group;
}

/** Picking interpolated geometry always returns an existing solved sample. */
export function emViewportSampleIndexForIntersection(hit: THREE.Intersection): number | null {
  const object = hit.object;
  if (Number.isInteger(object.userData.emSampleIndex)) return object.userData.emSampleIndex;
  const ids = object.userData.emSampleIndices;
  if (!Array.isArray(ids)) return null;
  if (hit.instanceId !== undefined) return ids[hit.instanceId] ?? null;
  if (hit.face && object instanceof THREE.Mesh) {
    const positions = object.geometry.getAttribute("position");
    const local = object.worldToLocal(hit.point.clone());
    let nearest = -1, distance = Infinity;
    for (const index of [hit.face.a, hit.face.b, hit.face.c]) {
      const candidate = new THREE.Vector3().fromBufferAttribute(positions, index);
      const next = candidate.distanceToSquared(local);
      if (next < distance) { distance = next; nearest = index; }
    }
    return ids[nearest] ?? null;
  }
  return hit.index === undefined ? null : ids[hit.index] ?? null;
}
