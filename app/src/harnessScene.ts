// SPDX-License-Identifier: Apache-2.0
import * as THREE from "three";
import type { HarnessConductorGeometry, VirtualHarnessVisual } from "./harnessVisualization";

export type HarnessScenePath = {
  harness: VirtualHarnessVisual;
  conductor: HarnessConductorGeometry;
};

export type HarnessSceneOptions = {
  roleColors: Readonly<Record<HarnessConductorGeometry["role"], number>>;
  maxMeshes?: number;
  tubularSegmentBudget?: number;
};

export type HarnessSceneStats = {
  meshes: number;
  truncatedMeshes: number;
  invalidPaths: number;
  sourcePoints: number;
  tubularSegments: number;
  triangles: number;
  samplingCappedMeshes: number;
  geometryBudgetCapped: boolean;
};

export type HarnessSceneBuild = {
  group: THREE.Group;
  pickables: THREE.Mesh<THREE.TubeGeometry, THREE.MeshStandardMaterial>[];
  stats: HarnessSceneStats;
};

/** Caps authored GPU objects independently of the higher level projection cap. */
export const MAX_HARNESS_SCENE_MESHES = 2048;
/** Six radial faces keep the tube legible without turning a loom into a dense CAD mesh. */
export const HARNESS_TUBE_RADIAL_SEGMENTS = 6;
export const MIN_HARNESS_TUBULAR_SEGMENTS = 8;
export const MAX_HARNESS_TUBULAR_SEGMENTS = 128;
/** At six radial faces this bounds the complete scene to fewer than 400k triangles. */
export const MAX_HARNESS_TUBULAR_SEGMENTS_TOTAL = 32768;

function boundedInteger(value: number | undefined, fallback: number, maximum: number): number {
  return Number.isFinite(value) ? Math.max(0, Math.min(maximum, Math.floor(value!))) : fallback;
}

function finiteCurvePoints(points: HarnessConductorGeometry["pointsMm"]): THREE.Vector3[] {
  const result: THREE.Vector3[] = [];
  for (const point of points) {
    if (point.length !== 3 || !point.every(Number.isFinite)) return [];
    const next = new THREE.Vector3(point[0], point[1], point[2]);
    if (!result.length || result[result.length - 1].distanceToSquared(next) > 1e-12) result.push(next);
  }
  return result;
}

function pathCurve(points: THREE.Vector3[]): THREE.Curve<THREE.Vector3> {
  if (points.length === 2) return new THREE.LineCurve3(points[0], points[1]);
  // Centripetal Catmull-Rom passes through the retained path points and limits
  // the loops and cusps that uniform splines can create around short segments.
  const curve = new THREE.CatmullRomCurve3(points, false, "centripetal", 0.5);
  curve.arcLengthDivisions = Math.min(384, Math.max(32, points.length * 2));
  return curve;
}

function conductorRadius(path: HarnessScenePath): number {
  if (path.conductor.presentation === "bundle-fallback") return 0.72;
  if (path.conductor.role === "shield") return 0.38;
  return 0.31;
}

function conductorIdentity(path: HarnessScenePath) {
  return path.conductor.wireId === null
    ? undefined
    : path.harness.conductors.find(item => item.id === path.conductor.wireId);
}

/**
 * Build display-only, depth-tested cable tubes from already admitted harness
 * paths. Electrical and solver geometry remains authoritative elsewhere.
 */
export function buildHarnessScene(paths: readonly HarnessScenePath[], options: HarnessSceneOptions): HarnessSceneBuild {
  const group = new THREE.Group();
  group.name = "virtual-harness-cables-mm";
  group.userData.presentationOnly = true;
  const maxMeshes = boundedInteger(options.maxMeshes, MAX_HARNESS_SCENE_MESHES, MAX_HARNESS_SCENE_MESHES);
  const segmentBudget = boundedInteger(options.tubularSegmentBudget,
    MAX_HARNESS_TUBULAR_SEGMENTS_TOTAL, MAX_HARNESS_TUBULAR_SEGMENTS_TOTAL);
  const prepared = paths.map(path => ({ path, points: finiteCurvePoints(path.conductor.pointsMm) }))
    .filter(entry => entry.points.length >= 2);
  const invalidPaths = paths.length - prepared.length;
  const budgetMeshLimit = Math.floor(segmentBudget / MIN_HARNESS_TUBULAR_SEGMENTS);
  const admitted = prepared.slice(0, Math.min(maxMeshes, budgetMeshLimit));
  const pickables: THREE.Mesh<THREE.TubeGeometry, THREE.MeshStandardMaterial>[] = [];
  let sourcePoints = 0;
  let tubularSegments = 0;
  let samplingCappedMeshes = 0;

  for (const [index, entry] of admitted.entries()) {
    const { path, points } = entry;
    sourcePoints += points.length;
    const desiredSegments = Math.max(MIN_HARNESS_TUBULAR_SEGMENTS, (points.length - 1) * 4);
    const remainingPaths = admitted.length - index;
    const remainingBudget = segmentBudget - tubularSegments;
    const fairShare = Math.floor(remainingBudget / remainingPaths);
    const segments = Math.min(MAX_HARNESS_TUBULAR_SEGMENTS, desiredSegments, fairShare);
    const radius = conductorRadius(path);
    const geometry = new THREE.TubeGeometry(pathCurve(points), segments, radius, HARNESS_TUBE_RADIAL_SEGMENTS, false);
    const baseColor = options.roleColors[path.conductor.role];
    const material = new THREE.MeshStandardMaterial({
      color: baseColor,
      roughness: path.conductor.presentation === "bundle-fallback" ? 0.82 : 0.68,
      metalness: path.conductor.role === "shield" ? 0.18 : 0.04,
      depthTest: true,
      depthWrite: true,
      transparent: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    const identity = conductorIdentity(path);
    mesh.name = `harness:${path.harness.id}:${path.conductor.wireId ?? "bundle"}`;
    mesh.userData.virtualHarness = path.conductor.wireId
      ? { ...path.harness, selectedConductorId: path.conductor.wireId }
      : path.harness;
    mesh.userData.harnessSceneCable = true;
    mesh.userData.presentationOnly = true;
    mesh.userData.harnessId = path.harness.id;
    mesh.userData.harnessWireId = path.conductor.wireId;
    mesh.userData.harnessFromPin = identity?.fromPin;
    mesh.userData.harnessToPin = identity?.toPin;
    mesh.userData.harnessPairId = path.conductor.pairId;
    mesh.userData.harnessPresentation = path.conductor.presentation;
    mesh.userData.harnessRole = path.conductor.role;
    mesh.userData.harnessBaseColor = baseColor;
    mesh.userData.harnessRadiusMm = radius;
    mesh.userData.harnessRouteMm = path.harness.routeMm;
    mesh.userData.harnessRouteIsSaved = path.harness.routedPolyline === true;
    mesh.userData.harnessSamplingCapped = path.conductor.samplingCapped || segments < desiredSegments;
    mesh.userData.harnessDepthTested = true;
    group.add(mesh);
    pickables.push(mesh);
    tubularSegments += segments;
    samplingCappedMeshes += mesh.userData.harnessSamplingCapped ? 1 : 0;
  }

  const triangles = tubularSegments * HARNESS_TUBE_RADIAL_SEGMENTS * 2;
  const stats: HarnessSceneStats = {
    meshes: pickables.length,
    truncatedMeshes: Math.max(0, prepared.length - admitted.length),
    invalidPaths,
    sourcePoints,
    tubularSegments,
    triangles,
    samplingCappedMeshes,
    geometryBudgetCapped: prepared.length > admitted.length || pickables.some(mesh => mesh.userData.harnessSamplingCapped === true),
  };
  Object.assign(group.userData, { harnessSceneStats: stats });
  return { group, pickables, stats };
}

/** Update exact harness/wire selection without rebuilding tube geometry. */
export function updateHarnessSceneSelection(root: THREE.Object3D, selectedHarnessId: string | null,
  selectedWireId: string | null, selectionColor: number): void {
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh) || object.userData.harnessSceneCable !== true
      || !(object.material instanceof THREE.MeshStandardMaterial)) return;
    const harnessMatches = object.userData.harnessId === selectedHarnessId;
    const selected = harnessMatches && (!selectedWireId || object.userData.harnessWireId === selectedWireId);
    const baseColor = Number(object.userData.harnessBaseColor);
    object.material.color.setHex(selected ? selectionColor : baseColor);
    object.material.emissive.setHex(selected ? selectionColor : 0x000000);
    object.material.emissiveIntensity = selected ? 0.24 : 0;
  });
}

/** Release every resource owned by a harness scene and detach its objects. */
export function disposeHarnessScene(root: THREE.Object3D): void {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh) || object.userData.harnessSceneCable !== true) return;
    geometries.add(object.geometry);
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material);
  });
  geometries.forEach(geometry => geometry.dispose());
  materials.forEach(material => material.dispose());
  root.clear();
}
