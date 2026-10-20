// SPDX-License-Identifier: Apache-2.0
// Presentation only: these are exact supplied axis-aligned cuboids, not reconstructed CAD.
import type { PlotTrace } from "./plotClipboard";

export type FieldSolid = { label: string; min: [number, number, number]; max: [number, number, number] };
export type FieldSolidGeometry = { solids: FieldSolid[] };

export const FIELD_SOLID_LIMIT = 4096;
export const FIELD_SOLID_DISPLAY_LIMIT = 1000;
const COORDINATE_LIMIT = 1e100;

const plainRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
const exactKeys = (value: Record<string, unknown>, keys: readonly string[]) => {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
};
const coordinate = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= COORDINATE_LIMIT;
const point = (value: unknown): value is [number, number, number] =>
  Array.isArray(value) && value.length === 3 && value.every(coordinate);

export function admitFieldSolidGeometry(value: unknown): FieldSolidGeometry | undefined {
  if (value === undefined) return undefined;
  const geometry = plainRecord(value);
  if (!geometry || !exactKeys(geometry, ["solids"]) || !Array.isArray(geometry.solids)
      || geometry.solids.length < 1 || geometry.solids.length > FIELD_SOLID_LIMIT) {
    throw new Error(`Field geometry must contain only 1–${FIELD_SOLID_LIMIT.toLocaleString("en-US")} supplied solids.`);
  }
  const solids = geometry.solids.map((candidate, index) => {
    const solid = plainRecord(candidate);
    if (!solid || !exactKeys(solid, ["label", "min", "max"])
        || typeof solid.label !== "string" || !solid.label.trim() || solid.label.length > 200
        || !point(solid.min) || !point(solid.max)) {
      throw new Error(`Solid ${index + 1} must contain only a label and finite min/max XYZ triples.`);
    }
    const minimum = solid.min;
    if (solid.max.some((valueAtAxis, axis) => valueAtAxis <= minimum[axis])) {
      throw new Error(`Solid ${index + 1} must have max greater than min on every axis.`);
    }
    return { label: solid.label, min: [...solid.min] as FieldSolid["min"], max: [...solid.max] as FieldSolid["max"] };
  });
  return { solids };
}

export function fieldSolidOverlay(
  geometry: FieldSolidGeometry | undefined,
  lengthUnit: "m" | "mm",
  opacity = 0.15,
): { traces: PlotTrace[]; shown: number; total: number } {
  const total = geometry?.solids.length ?? 0;
  const displayed = geometry?.solids.slice(0, FIELD_SOLID_DISPLAY_LIMIT) ?? [];
  if (!displayed.length) return { traces: [], shown: 0, total };
  const x: number[] = [], y: number[] = [], z: number[] = [];
  const i: number[] = [], j: number[] = [], k: number[] = [], customdata: string[] = [];
  const faces = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]];
  displayed.forEach(solid => {
    const base = x.length;
    for (const vertex of [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]]) {
      x.push(vertex[0] ? solid.max[0] : solid.min[0]);
      y.push(vertex[1] ? solid.max[1] : solid.min[1]);
      z.push(vertex[2] ? solid.max[2] : solid.min[2]);
      customdata.push(solid.label);
    }
    for (const face of faces) { i.push(base + face[0]); j.push(base + face[1]); k.push(base + face[2]); }
  });
  const boundedOpacity = Number.isFinite(opacity) ? Math.max(0, Math.min(1, opacity)) : 0.15;
  return { shown: displayed.length, total, traces: [{
    type: "mesh3d", name: "Supplied solid geometry", x, y, z, i, j, k, customdata,
    color: "#8a9ba6", opacity: boundedOpacity, flatshading: true, showscale: false,
    hovertemplate: `Supplied solid · %{customdata}<br>x=%{x} ${lengthUnit}<br>y=%{y} ${lengthUnit}<br>z=%{z} ${lengthUnit}<extra></extra>`,
  }] };
}
