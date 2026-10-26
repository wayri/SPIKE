// SPDX-License-Identifier: Apache-2.0
// Presentation-only motion along admitted frozen/steady streamline geometry.
import * as THREE from "three";
import type { FieldPoint } from "./fieldVolumeModel";

export const FIELD_STREAM_MARKER_LIMIT = 256;

export type FieldStreamAnimationOptions = {
  enabled: boolean;
  /** Normalized curve traversals per display second; this is not solver time. */
  speed: number;
  markerCount: number;
  pointSize: number;
  opacity: number;
};

export type FieldStreamAnimationController = {
  readonly points: THREE.Points;
  readonly pathCount: number;
  readonly markerCount: number;
  readonly sourceCurveDirection: "supplied-point-order" | "generated-velocity-trace-order";
  update(deltaSeconds: number, enabled?: boolean): boolean;
  dispose(): void;
};

type CompiledPath = { points: Float64Array; cumulative: Float64Array; length: number };
const defaults: FieldStreamAnimationOptions = { enabled: false, speed: 0.12, markerCount: 0, pointSize: 5, opacity: 0.92 };
const finitePoint = (point: readonly number[]): point is FieldPoint => point.length === 3
  && point.every(value => Number.isFinite(value) && Math.abs(value) <= 3.402823466e38);
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));

function compile(paths: readonly (readonly (readonly number[])[])[]): CompiledPath[] {
  const result: CompiledPath[] = [];
  for (const path of paths) {
    if (path.length < 2 || !path.every(finitePoint)) continue;
    const cumulative = new Float64Array(path.length), points = new Float64Array(path.length * 3);
    let length = 0;
    for (let index = 0; index < path.length; index++) {
      const point = path[index]; points.set(point, index * 3);
      if (index) {
        const previous = path[index - 1];
        length += Math.hypot(point[0] - previous[0], point[1] - previous[1], point[2] - previous[2]);
      }
      cumulative[index] = length;
    }
    if (Number.isFinite(length) && length > 0) result.push({ points, cumulative, length });
  }
  return result;
}

function markerBudget(pathCount: number, requested: number) {
  if (!pathCount) return 0;
  const fallback = Math.min(FIELD_STREAM_MARKER_LIMIT, pathCount * 2);
  return Math.max(1, Math.min(FIELD_STREAM_MARKER_LIMIT, Math.trunc(requested) || fallback));
}

function sampleCompiled(paths: readonly CompiledPath[], elapsedSeconds: number, speed: number, markerCount: number, target: Float32Array) {
  if (!paths.length || !Number.isFinite(elapsedSeconds) || !Number.isFinite(speed)) return false;
  const motion = Math.max(0, elapsedSeconds) * Math.max(0, speed), perPath = Math.ceil(markerCount / paths.length);
  for (let marker = 0; marker < markerCount; marker++) {
    const path = paths[marker % paths.length], lane = Math.floor(marker / paths.length);
    const phase = ((lane + 0.5) / perPath + motion) % 1, distance = phase * path.length;
    let low = 1, high = path.cumulative.length - 1;
    while (low < high) { const middle = (low + high) >>> 1; if (path.cumulative[middle] < distance) low = middle + 1; else high = middle; }
    const end = low, start = end - 1, span = path.cumulative[end] - path.cumulative[start];
    const fraction = span > 0 ? (distance - path.cumulative[start]) / span : 0;
    for (let axis = 0; axis < 3; axis++) {
      const a = path.points[start * 3 + axis], b = path.points[end * 3 + axis];
      target[marker * 3 + axis] = a + (b - a) * fraction;
    }
  }
  return true;
}

/** Pure deterministic sampler used by tests and non-rendering previews. */
export function sampleFieldStreamMarkers(paths: readonly (readonly (readonly number[])[])[], elapsedSeconds: number,
  options: Partial<Pick<FieldStreamAnimationOptions, "speed" | "markerCount">> = {}): Float32Array {
  const compiled = compile(paths), count = markerBudget(compiled.length, options.markerCount ?? 0);
  const positions = new Float32Array(count * 3);
  if (count) sampleCompiled(compiled, elapsedSeconds, options.speed ?? defaults.speed, count, positions);
  return positions;
}

/** Attach one bounded GPU point buffer following the exact provided polylines. */
export function attachFieldStreamAnimation(group: THREE.Group, paths: readonly (readonly (readonly number[])[])[],
  sourceCurveDirection: FieldStreamAnimationController["sourceCurveDirection"],
  options: Partial<FieldStreamAnimationOptions> = {}): FieldStreamAnimationController | null {
  const compiled = compile(paths), count = markerBudget(compiled.length, options.markerCount ?? defaults.markerCount);
  if (!compiled.length || !count) return null;
  const speed = Number.isFinite(options.speed) ? clamp(options.speed!, 0, 4) : defaults.speed;
  const positions = new Float32Array(count * 3);
  sampleCompiled(compiled, 0, speed, count, positions);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  const material = new THREE.PointsMaterial({ color: 0xf7fbff, size: clamp(options.pointSize ?? defaults.pointSize, 1, 12),
    sizeAttenuation: false, transparent: true, opacity: clamp(options.opacity ?? defaults.opacity, 0.05, 1),
    depthWrite: false, toneMapped: false });
  const points = new THREE.Points(geometry, material); points.name = "field-flow-motion-markers";
  points.visible = options.enabled ?? defaults.enabled; points.frustumCulled = false; group.add(points);
  let elapsed = 0, disposed = false;
  const controller: FieldStreamAnimationController = {
    points, pathCount: compiled.length, markerCount: count, sourceCurveDirection,
    update(deltaSeconds, enabled = points.visible) {
      if (disposed) return false;
      points.visible = Boolean(enabled);
      if (!points.visible || !Number.isFinite(deltaSeconds) || deltaSeconds < 0) return false;
      elapsed += Math.min(deltaSeconds, 0.25);
      if (!sampleCompiled(compiled, elapsed, speed, count, positions)) return false;
      geometry.attributes.position.needsUpdate = true;
      return true;
    },
    dispose() {
      if (disposed) return;
      disposed = true; points.removeFromParent(); geometry.dispose(); material.dispose();
      if (group.userData.fieldStreamAnimation === controller) delete group.userData.fieldStreamAnimation;
    },
  };
  group.userData.fieldStreamAnimation = controller;
  return controller;
}

/** Advance an attached overlay without allocating new GPU resources. */
export function updateFieldStreamAnimation(group: THREE.Group | null | undefined, deltaSeconds: number, enabled?: boolean) {
  const controller = group?.userData.fieldStreamAnimation as FieldStreamAnimationController | undefined;
  return controller?.update(deltaSeconds, enabled) ?? false;
}
