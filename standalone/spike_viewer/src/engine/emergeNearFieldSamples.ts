// SPDX-License-Identifier: Apache-2.0
export type Vector = [number, number][];
export type Plane = { frequency_hz: number; grid_shape: number[]; coordinates_mm: number[][]; valid: boolean[]; e_v_m: (Vector | null)[]; h_a_m: (Vector | null)[] };
const vector = (value: unknown): value is Vector => Array.isArray(value) && value.length === 3 && value.every(pair => Array.isArray(pair) && pair.length === 2 && pair.every(number => typeof number === "number" && Number.isFinite(number)));
export function admitEMergeFieldPlanes(value: unknown): Plane[] {
  if (!value || typeof value !== "object") return [];
  const data = value as { contract?: string; planes?: unknown[]; frequencies_hz?: unknown[] };
  const frequencies = data.frequencies_hz;
  if (data.contract !== "spike/emerge-nearfield-plane/v1" || !Array.isArray(data.planes)
      || !Array.isArray(frequencies) || !frequencies.length || frequencies.length > 64
      || data.planes.length !== frequencies.length
      || frequencies.some((value, i) => typeof value !== "number" || !Number.isFinite(value) || value <= 0
        || (i > 0 && value <= (frequencies[i - 1] as number)))) return [];
  let samples = 0;
  const planes: Plane[] = [];
  for (const [frequencyIndex, value] of data.planes.entries()) {
    const plane = value as Plane;
    if (!plane || plane.frequency_hz !== frequencies[frequencyIndex] || !Array.isArray(plane.grid_shape) || plane.grid_shape.length !== 2 || plane.grid_shape.some(n => !Number.isInteger(n) || n < 3 || n > 41)) return [];
    const count = plane.grid_shape[0] * plane.grid_shape[1];
    samples += count;
    if (samples > 100000 || ![plane.coordinates_mm, plane.valid, plane.e_v_m, plane.h_a_m].every(array => Array.isArray(array) && array.length === count)
        || !plane.coordinates_mm.every(point => Array.isArray(point) && point.length === 3 && point.every(Number.isFinite))
        || !plane.valid.every((valid, i) => typeof valid === "boolean" && (valid ? vector(plane.e_v_m[i]) && vector(plane.h_a_m[i]) : plane.e_v_m[i] === null && plane.h_a_m[i] === null))) return [];
    const [ny, nx] = plane.grid_shape;
    const xs = plane.coordinates_mm.slice(0, nx).map(point => point[0]);
    const ys = Array.from({ length: ny }, (_, row) => plane.coordinates_mm[row * nx][1]);
    const depth = plane.coordinates_mm[0][2];
    if (xs.some((x, i) => i > 0 && x <= xs[i - 1]) || ys.some((y, i) => i > 0 && y <= ys[i - 1])
        || plane.coordinates_mm.some((point, i) => point[0] !== xs[i % nx] || point[1] !== ys[Math.floor(i / nx)] || point[2] !== depth)) return [];
    if (planes.length && (plane.grid_shape.some((value, i) => value !== planes[0].grid_shape[i])
        || plane.coordinates_mm.some((point, i) => point.some((value, axis) => value !== planes[0].coordinates_mm[i][axis])))) return [];
    planes.push(plane);
  }
  return planes;
}
