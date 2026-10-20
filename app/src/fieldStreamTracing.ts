// SPDX-License-Identifier: Apache-2.0
// Frozen-frame presentation geometry only; never exported as solved field data.
import type { FieldPoint, FieldVolumeData, FieldViewOptions } from "./fieldVolumeModel";
import { cartesianFluidGrid, type FieldStreamline } from "./fieldStreamPresentation";

export const FIELD_STREAM_SEGMENT_LIMIT = 16_000;
const bounded = (n: number | undefined, fallback: number, low: number, high: number) =>
  Number.isFinite(n) ? Math.min(high, Math.max(low, Math.trunc(n!))) : fallback;

/** Trilinear vectors + explicit midpoint arc-length tracing, inside center bounds.
 * See docs/validation/FIELD_STREAM_PRESENTATION_20261021.md for method and limits.
 * Empty output means unavailable or no drawable nonzero path, not zero flow proof.
 */
export function traceFieldGrid(data: FieldVolumeData, options: FieldViewOptions): FieldStreamline[] {
  const frameIndex = bounded(options.frame, 0, 0, data.frames.length - 1);
  const grid = cartesianFluidGrid(data, frameIndex), vectors = data.frames[frameIndex]?.vectors;
  if (!grid || !vectors || vectors.length !== data.cells.centers.length ||
      vectors.some(v => v.length !== 3 || v.some(x => !Number.isFinite(x))) ||
      grid.axes.some(a => a.some(x => !Number.isFinite(x)))) return [];
  const origin = grid.axes.map(a => a[0]);
  const span = grid.axes.reduce((largest, a) => Math.max(largest, a[a.length - 1] - a[0]), 0);
  if (!(span > 0) || !Number.isFinite(span)) return [];
  const axes = grid.axes.map((a, d) => a.map(v => (v - origin[d]) / span));
  let gap = Infinity;
  for (const a of axes) for (let i = 1; i < a.length; i++) gap = Math.min(gap, a[i] - a[i - 1]);
  // Reject unresolved relative coordinate spacing instead of tracing roundoff.
  if (!(gap >= 1e-12)) return [];
  const h = gap / 4, upper = axes.map(a => a[a.length - 1]);
  const inside = (p: FieldPoint) => p.every((v, d) => Number.isFinite(v) && v >= 0 && v <= upper[d]);
  const sample = (p: FieldPoint) => {
    if (!inside(p)) return null;
    const indices: number[] = [], fractions: number[] = [];
    for (let d = 0; d < 3; d++) {
      const a = axes[d];
      let low = 0, high = a.length - 1;
      while (high - low > 1) { const mid = (low + high) >> 1; if (a[mid] <= p[d]) low = mid; else high = mid; }
      indices.push(low); fractions.push((p[d] - a[low]) / (a[low + 1] - a[low]));
    }
    const v: FieldPoint = [0, 0, 0];
    for (let x = 0; x < 2; x++) for (let y = 0; y < 2; y++) for (let z = 0; z < 2; z++) {
      const bits = [x, y, z];
      const weight = bits.reduce((w, b, d) => w * (b ? fractions[d] : 1 - fractions[d]), 1);
      const index = ((indices[0] + x) * axes[1].length + indices[1] + y) * axes[2].length + indices[2] + z;
      const source = vectors[grid.order[index]];
      for (let d = 0; d < 3; d++) v[d] += weight * source[d];
    }
    const speed = Math.hypot(...v);
    if (!(speed > 0) || !Number.isFinite(speed)) return null;
    return { direction: v.map(x => x / speed) as FieldPoint, speed };
  };
  const density = bounded(options.seedDensity, 4, 2, 8);
  const budget = bounded(options.budget, 2500, 1, FIELD_STREAM_SEGMENT_LIMIT);
  const perDirection = Math.min(256, Math.floor(budget / (2 * density * density)));
  if (!perDirection) return [];
  const seedAxis = { x: 0, y: 1, z: 2 }[options.seedAxis ?? "x"] ?? 0;
  const sideAxes = [0, 1, 2].filter(d => d !== seedAxis);
  const result: FieldStreamline[] = [];
  const march = (seed: FieldPoint, sign: number) => {
    const points: FieldPoint[] = [], speeds: number[] = [];
    let p = seed;
    for (let step = 0; step < perDirection && step * h < 4; step++) {
      const start = sample(p);
      if (!start) break;
      const mid = p.map((v, d) => v + sign * h * start.direction[d] / 2) as FieldPoint;
      const middle = sample(mid);
      if (!middle) break;
      const next = p.map((v, d) => v + sign * h * middle.direction[d]) as FieldPoint;
      const end = sample(next);
      if (!end || next.every((v, d) => v === p[d])) break;
      points.push(next); speeds.push(end.speed); p = next;
    }
    return { points, speeds };
  };
  for (let a = 0; a < density; a++) for (let b = 0; b < density; b++) {
    const seed: FieldPoint = [0, 0, 0];
    seed[seedAxis] = upper[seedAxis] / 2;
    sideAxes.forEach((d, i) => { seed[d] = upper[d] * ((i ? b : a) + .5) / density; });
    const value = sample(seed);
    if (!value) continue;
    const back = march(seed, -1), forward = march(seed, 1);
    const points = [...back.points.reverse(), seed, ...forward.points];
    if (points.length < 2) continue;
    const physical = points.map(p => p.map((v, d) => origin[d] + span * v) as FieldPoint);
    if (physical.some((p, i) => p.some(v => !Number.isFinite(v)) ||
        (i > 0 && p.every((v, d) => v === physical[i - 1][d])))) continue;
    result.push({ points: physical, scalars: { speed_m_s: [...back.speeds.reverse(), value.speed, ...forward.speeds] } });
  }
  return result;
}
