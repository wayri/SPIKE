// SPDX-License-Identifier: Apache-2.0
// Presentation only: saved cell values are never interpolated into solved fields.
import type { PlotTrace } from "./plotClipboard";
import { streamPresentation, type FieldStreamline } from "./fieldStreamPresentation";
import { admitFieldSolidGeometry, fieldSolidOverlay, type FieldSolidGeometry } from "./fieldSolidOverlay";
export type FieldPoint = [number, number, number];
export type FieldVolumeData = {
  contract: "spike/field-volume-view/v1"; id: string; label: string; lengthUnit: "m" | "mm";
  geometryNote?: string;
  geometry?: FieldSolidGeometry;
  cells: { centers: FieldPoint[]; sizes?: FieldPoint[]; flowDomain?: "complete-cartesian-fluid" };
  quantities: { id: string; label: string; unit: string }[];
  frames: { timeS: number; scalars: Record<string, number[]>; vectors?: FieldPoint[]; streamlines?: FieldStreamline[] }[];
};
export const FIELD_CELL_LIMIT = 200_000;
export const FIELD_VALUE_LIMIT = 4_000_000;
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && Math.abs(v) <= 1e100;
const text = (v: unknown): v is string => typeof v === "string" && v.trim().length > 0 && v.length <= 500;
const triple = (v: unknown): v is FieldPoint => Array.isArray(v) && v.length === 3 && v.every(finite);
export function admitFieldVolume(value: unknown): FieldVolumeData {
  const data = record(value), cells = record(data.cells);
  if (data.contract !== "spike/field-volume-view/v1" || !text(data.id) || !text(data.label) || !["m", "mm"].includes(String(data.lengthUnit))) throw new Error("Unsupported field visualization envelope or coordinate units.");
  if (data.geometryNote !== undefined && !text(data.geometryNote)) throw new Error("Invalid field geometry note.");
  if (!Array.isArray(cells.centers) || !cells.centers.length || cells.centers.length > FIELD_CELL_LIMIT || !cells.centers.every(triple)) throw new Error("Field centers must be finite triples (1–200,000 samples).");
  const count = cells.centers.length;
  if (cells.flowDomain !== undefined && cells.flowDomain !== "complete-cartesian-fluid") throw new Error("Unsupported flow-domain declaration.");
  if (cells.sizes !== undefined && (!Array.isArray(cells.sizes) || cells.sizes.length !== count || !cells.sizes.every(v => triple(v) && v.every(n => n > 0)))) throw new Error("Voxel sizes must contain one positive XYZ size per cell.");
  if (!Array.isArray(data.quantities) || !data.quantities.length || data.quantities.length > 16) throw new Error("Field quantities are missing or exceed 16.");
  const quantities = data.quantities.map(q => { const row = record(q); if (!text(row.id) || !text(row.label) || !text(row.unit)) throw new Error("Every field quantity needs an ID, label and unit."); return { id: row.id, label: row.label, unit: row.unit }; });
  if (new Set(quantities.map(q => q.id)).size !== quantities.length) throw new Error("Field quantity IDs must be unique.");
  if (!Array.isArray(data.frames) || !data.frames.length || data.frames.length > 1000) throw new Error("Field frames must contain 1–1000 saved samples.");
  let values = 0, previous = -Infinity;
  const frames = data.frames.map(frame => {
    const row = record(frame), scalars = record(row.scalars);
    if (!finite(row.timeS) || row.timeS < 0 || row.timeS <= previous) throw new Error("Field frame times must be finite, nonnegative and strictly increasing seconds.");
    previous = row.timeS;
    const admitted: Record<string, number[]> = Object.create(null);
    for (const quantity of quantities) {
      const array = scalars[quantity.id]; values += count;
      if (values > FIELD_VALUE_LIMIT || !Array.isArray(array) || array.length !== count || !array.every(finite)) throw new Error("Field scalars must match the cells and stay within the four-million-value limit.");
      admitted[quantity.id] = array.slice();
    }
    const vectors = row.vectors;
    if (vectors !== undefined) {
      values += count * 3;
      if (values > FIELD_VALUE_LIMIT || !Array.isArray(vectors) || vectors.length !== count || !vectors.every(triple)) throw new Error("Velocity vectors must match the cells and be finite XYZ m/s triples.");
    }
    let streamlines: FieldStreamline[] | undefined;
    if (row.streamlines !== undefined) {
      if (!Array.isArray(row.streamlines) || row.streamlines.length > 256) throw new Error("At most 256 supplied curves are accepted per frame.");
      streamlines = row.streamlines.map(path => {
        const line = record(path), fields = record(line.scalars), points = line.points;
        if (!Array.isArray(points) || points.length < 2 || points.length > 16_000 || !points.every(triple)) throw new Error("Curve points must contain 2–16,000 finite XYZ triples.");
        for (let i = 1; i < points.length; i++) if (points[i].every((v, axis) => v === points[i - 1][axis])) throw new Error("Consecutive curve points must be distinct.");
        values += points.length * 3;
        const scalars: Record<string, number[]> = Object.create(null);
        for (const quantity of quantities) {
          values += points.length;
          const array = fields[quantity.id];
          if (!Array.isArray(array) || array.length !== points.length || !array.every(finite)) throw new Error("Supplied curve scalars must match each path point and declared quantity.");
          scalars[quantity.id] = array.slice();
        }
        if (values > FIELD_VALUE_LIMIT) throw new Error("Supplied curves exceed the four-million-value limit.");
        return { points: points.map(p => [...p] as FieldPoint), scalars };
      });
    }
    return { timeS: row.timeS, scalars: admitted, ...(Array.isArray(vectors) ? { vectors: vectors.map(v => [...v] as FieldPoint) } : {}), ...(streamlines ? { streamlines } : {}) };
  });
  const geometry = admitFieldSolidGeometry(data.geometry);
  return { contract: "spike/field-volume-view/v1", id: data.id, label: data.label, lengthUnit: data.lengthUnit as "m" | "mm", geometryNote: data.geometryNote as string | undefined, ...(geometry ? { geometry } : {}),
    cells: { centers: cells.centers.map(v => [...v] as FieldPoint), ...(Array.isArray(cells.sizes) ? { sizes: cells.sizes.map(v => [...v] as FieldPoint) } : {}), ...(cells.flowDomain ? { flowDomain: "complete-cartesian-fluid" as const } : {}) }, quantities, frames };
}
export type FieldViewOptions = { frame: number; quantity: string; mode: "voxels" | "points" | "streamlines" | "streamtubes"; arrows: boolean; opacity: number; budget: number; sliceAxis: "all" | "x" | "y" | "z"; slicePercent: number; celsius: boolean; seedAxis?: "x" | "y" | "z"; seedDensity?: number; streamWidth?: number; showSolids?: boolean; solidOpacity?: number };
export function fieldViewPlot(data: FieldVolumeData, options: FieldViewOptions) {
  const quantity = data.quantities.find(q => q.id === options.quantity);
  if (!quantity) throw new Error("Select an available field quantity.");
  const frame = data.frames[Math.max(0, Math.min(data.frames.length - 1, Math.trunc(options.frame)))];
  const convert = (v: number) => options.celsius && quantity.unit === "K" ? v - 273.15 : v;
  const unit = options.celsius && quantity.unit === "K" ? "°C" : quantity.unit;
  const solidOverlay = options.showSolids === false ? { traces: [] as PlotTrace[], shown: 0, total: data.geometry?.solids.length ?? 0 }
    : fieldSolidOverlay(data.geometry, data.lengthUnit, options.solidOpacity ?? 0.15);
  const bounds = [0, 1, 2].map(axis => {
    let low = Infinity, high = -Infinity;
    data.cells.centers.forEach((p, index) => { const half = (data.cells.sizes?.[index][axis] ?? 0) / 2; low = Math.min(low, p[axis] - half); high = Math.max(high, p[axis] + half); });
    return [low, high];
  });
  let minimum = Infinity, maximum = -Infinity, maxSpeed = 0;
  for (const saved of data.frames) {
    for (const v of saved.scalars[quantity.id]) { minimum = Math.min(minimum, convert(v)); maximum = Math.max(maximum, convert(v)); }
    if (saved.streamlines) for (const path of saved.streamlines) for (const v of path.scalars[quantity.id]) { minimum = Math.min(minimum, convert(v)); maximum = Math.max(maximum, convert(v)); }
    if (saved.vectors) for (const v of saved.vectors) maxSpeed = Math.max(maxSpeed, Math.hypot(...v));
  }
  if (options.mode === "streamlines" || options.mode === "streamtubes") {
    const streams = streamPresentation(data, { mode: options.mode, frame: Math.max(0, Math.min(data.frames.length - 1, Math.trunc(options.frame))), quantity: quantity.id, unit, celsius: options.celsius, minimum, maximum, opacity: options.opacity,
      budget: options.budget, seedAxis: options.seedAxis ?? "x", density: options.seedDensity ?? 4, width: options.streamWidth ?? 2 });
    return { traces: [...streams.traces, ...solidOverlay.traces], shown: 0, total: data.cells.centers.length, eligible: 0, arrowCount: 0, minimum, maximum, unit, streamCount: streams.count, streamNote: streams.note, solidShown: solidOverlay.shown, solidTotal: solidOverlay.total };
  }
  const axis = options.sliceAxis === "all" ? -1 : { x: 0, y: 1, z: 2 }[options.sliceAxis];
  const threshold = axis < 0 ? Infinity : bounds[axis][0] + (bounds[axis][1] - bounds[axis][0]) * Math.max(0, Math.min(100, options.slicePercent)) / 100;
  const candidates = data.cells.centers.flatMap((p, i) => axis < 0 || p[axis] <= threshold ? [i] : []);
  const budget = Math.max(1, Math.min(8000, Math.trunc(options.budget) || 2500));
  const step = Math.max(1, Math.ceil(candidates.length / budget));
  const indices = candidates.filter((_, i) => i % step === 0);
  const values = indices.map(i => convert(frame.scalars[quantity.id][i]));
  const scale = { colorscale: "Viridis", cmin: minimum, cmax: maximum > minimum ? maximum : minimum + Math.max(1, Math.abs(minimum) * 1e-6), showscale: true, colorbar: { thickness: 16, title: { text: `${quantity.label.slice(0, 40)} (${unit})`, side: "right" } } };
  const traces: PlotTrace[] = [];
  if (options.mode === "voxels" && data.cells.sizes) {
    const x: number[] = [], y: number[] = [], z: number[] = [], i: number[] = [], j: number[] = [], k: number[] = [], intensity: number[] = [];
    const faces = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]];
    indices.forEach((index, at) => {
      const p = data.cells.centers[index], size = data.cells.sizes![index], base = x.length;
      for (const v of [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]]) { x.push(p[0] + v[0] * size[0] / 2); y.push(p[1] + v[1] * size[1] / 2); z.push(p[2] + v[2] * size[2] / 2); }
      for (const f of faces) { i.push(base + f[0]); j.push(base + f[1]); k.push(base + f[2]); intensity.push(values[at]); }
    });
    traces.push({ type: "mesh3d", name: quantity.label, x, y, z, i, j, k, intensity, intensitymode: "cell", flatshading: true, opacity: options.opacity, ...scale,
      hovertemplate: `Cell face<br>%{intensity:.6g} ${unit}<extra></extra>` });
  } else {
    traces.push({ type: "scatter3d", mode: "markers", name: quantity.label, x: indices.map(i => data.cells.centers[i][0]), y: indices.map(i => data.cells.centers[i][1]), z: indices.map(i => data.cells.centers[i][2]),
      marker: { size: 4, color: values, opacity: options.opacity, ...scale }, customdata: values,
      hovertemplate: `x=%{x} ${data.lengthUnit}<br>y=%{y}<br>z=%{z}<br>%{customdata:.6g} ${unit}<extra></extra>` });
  }
  let arrowCount = 0;
  if (options.arrows && frame.vectors && maxSpeed > 0) {
    const x: (number | null)[] = [], y: (number | null)[] = [], z: (number | null)[] = [];
    const span = bounds.reduce((largest, b) => Math.max(largest, b[1] - b[0]), 1e-12);
    const length = span * 0.045, arrowStep = Math.max(1, Math.ceil(indices.length / 1500));
    indices.filter((_, n) => n % arrowStep === 0).forEach(index => {
      const p = data.cells.centers[index], v = frame.vectors![index], speed = Math.hypot(...v);
      if (speed === 0) return;
      const d = v.map(n => n / speed), extent = length * speed / maxSpeed;
      const tip = p.map((n, a) => n + d[a] * extent);
      const reference = Math.abs(d[2]) < .9 ? [0, 0, 1] : [0, 1, 0];
      const side = [d[1] * reference[2] - d[2] * reference[1], d[2] * reference[0] - d[0] * reference[2], d[0] * reference[1] - d[1] * reference[0]];
      const norm = Math.hypot(...side);
      const left = tip.map((n, a) => n - d[a] * extent * .28 + side[a] / norm * extent * .14);
      const right = tip.map((n, a) => n - d[a] * extent * .28 - side[a] / norm * extent * .14);
      for (const point of [p, tip, null, left, tip, right, null]) { x.push(point?.[0] ?? null); y.push(point?.[1] ?? null); z.push(point?.[2] ?? null); }
      arrowCount++;
    });
    traces.push({ type: "scatter3d", name: "Velocity direction (m/s)", mode: "lines", x, y, z, line: { color: "#57d8c7", width: 3 }, hoverinfo: "skip", showlegend: false });
  }
  traces.push(...solidOverlay.traces);
  return { traces, shown: indices.length, total: data.cells.centers.length, eligible: candidates.length, arrowCount, minimum, maximum, unit, streamCount: 0, streamNote: "", solidShown: solidOverlay.shown, solidTotal: solidOverlay.total };
}
