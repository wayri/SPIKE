// SPDX-License-Identifier: Apache-2.0
import type { PlotTrace } from "./plotClipboard";

export type PlotColorScale = { label: string; unit: string; minimum: number; maximum: number; gradient?: string; scope?: string };
type Row = Record<string, unknown>;
const record = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const text = (value: unknown): string => typeof value === "string" ? value.replace(/<[^>]*>/g, "").trim() : "";

function bounds(values: unknown): [number, number] | null {
  let minimum = Infinity, maximum = -Infinity;
  const visit = (value: unknown) => {
    if (finite(value)) { minimum = Math.min(minimum, value); maximum = Math.max(maximum, value); }
    else if (Array.isArray(value) || ArrayBuffer.isView(value)) for (const entry of Array.from(value as ArrayLike<unknown>)) visit(entry);
  };
  visit(values);
  return finite(minimum) && finite(maximum) ? [minimum, maximum] : null;
}

/** Use Plotly's resolved palette when available; unknown named palettes have no invented ramp. */
export function plotScaleGradient(colorscale: unknown, reversed = false): string | undefined {
  if (!Array.isArray(colorscale) || colorscale.length < 2) return;
  const stops: [number, string][] = [];
  for (const stop of colorscale) {
    if (!Array.isArray(stop) || !finite(stop[0]) || stop[0] < 0 || stop[0] > 1 || typeof stop[1] !== "string") return;
    const color = stop[1].trim();
    if (!/^(?:#[\da-f]{3,8}|[a-z]+|(?:rgb|rgba|hsl|hsla)\([\d\s.,%+\-/]+\))$/i.test(color)) return;
    stops.push([stop[0], color]);
  }
  if (stops.some((stop, index) => index > 0 && stop[0] < stops[index - 1][0])) return;
  const ordered = reversed ? stops.slice().reverse().map(([position, color]): [number, string] => [1 - position, color]) : stops;
  return `linear-gradient(to right, ${ordered.map(([position, color]) => `${color} ${position * 100}%`).join(", ")})`;
}

/** Scalar color domains only. Coordinate/log axis settings never transform these values. */
export function plotColorScales(data: readonly PlotTrace[], layout: Row = {}): PlotColorScale[] {
  const scales: PlotColorScale[] = [], axes = new Set<string>();
  for (const trace of data) {
    if (trace.visible === false || trace.visible === "legendonly") continue;
    const type = String(trace.type ?? "scatter");
    let owner = trace, samples: unknown, prefix = "c";
    if (type === "heatmap" || type === "contour") { samples = trace.z; prefix = "z"; }
    else if (type === "surface") samples = trace.surfacecolor ?? trace.z;
    else if (type === "mesh3d") samples = trace.intensity;
    else if (["scatter3d", "scatter", "scattergl"].includes(type)) { owner = record(trace.marker); samples = owner.color; }
    else continue;
    if (!Array.isArray(samples) && !ArrayBuffer.isView(samples)) continue;
    const observed = bounds(samples); if (!observed) continue;
    const axis = typeof owner.coloraxis === "string" ? owner.coloraxis : "";
    if (axis) { if (axes.has(axis)) continue; owner = record(layout[axis]); prefix = "c"; }
    const minimum = finite(owner[`${prefix}min`]) ? owner[`${prefix}min`] as number : observed[0];
    const maximum = finite(owner[`${prefix}max`]) ? owner[`${prefix}max`] as number : observed[1];
    if (maximum < minimum) continue;
    const title = record(owner.colorbar).title;
    const label = text(typeof title === "string" ? title : record(title).text) || text(trace.name) || "Scalar value";
    scales.push({ label, unit: "", minimum, maximum, gradient: plotScaleGradient(owner.colorscale, owner.reversescale === true), scope: "Color domain" });
    if (axis) axes.add(axis);
  }
  return scales;
}
