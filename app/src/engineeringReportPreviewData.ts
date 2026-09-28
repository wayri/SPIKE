// SPDX-License-Identifier: Apache-2.0

import type { ScalarSample } from "./analysisResults";
import { sharedVertexValues } from "./resultSurfaceInterpolation";

const escapeHtml = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]!);

function boundedSamples(samples: ScalarSample[], limit: number) {
  if (samples.length <= limit) return samples;
  const output: ScalarSample[] = [];
  const step = (samples.length - 1) / (limit - 1);
  for (let index = 0; index < limit; index += 1) output.push(samples[Math.round(index * step)]);
  return output;
}

export function reportFieldSamples(samples: ScalarSample[]) {
  const bounded = boundedSamples(samples, 600);
  const vertexValues = sharedVertexValues(bounded);
  return bounded.map(sample => ({ ...sample, vertex_values: vertexValues.get(sample) }));
}

export function reportSparklineSvg(samples: ScalarSample[], label: string, unit: string) {
  const bounded = boundedSamples(samples.filter(sample => Number.isFinite(sample.value)), 180);
  if (!bounded.length) return "";
  const range = bounded.reduce((state, sample) => ({ minimum: Math.min(state.minimum, sample.value), maximum: Math.max(state.maximum, sample.value) }), { minimum: Infinity, maximum: -Infinity });
  const span = range.maximum - range.minimum || 1;
  const faceSamples = bounded.filter(sample => (sample.vertices_mm?.length ?? 0) >= 3);
  const positions = (faceSamples.length ? faceSamples.flatMap(sample => sample.vertices_mm!) : bounded.map(sample => [sample.x_mm, sample.y_mm] as [number, number]));
  const bounds = positions.reduce((state, point) => ({ minX: Math.min(state.minX, point[0]), maxX: Math.max(state.maxX, point[0]), minY: Math.min(state.minY, point[1]), maxY: Math.max(state.maxY, point[1]) }), { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity });
  const project = (point: readonly number[]) => [10 + (point[0] - bounds.minX) / (bounds.maxX - bounds.minX || 1) * 680, 115 - (point[1] - bounds.minY) / (bounds.maxY - bounds.minY || 1) * 100];
  const color = (value: number) => `hsl(${210 - Math.max(0, Math.min(1, (value - range.minimum) / span)) * 175} 70% 48%)`;
  const marks = faceSamples.length
    ? faceSamples.map(sample => `<polygon points="${sample.vertices_mm!.map(vertex => project(vertex).join(",")).join(" ")}" fill="${color(sample.value)}" stroke="#173b47" stroke-width="0.7"/>`).join("")
    : bounded.map(sample => { const point = project([sample.x_mm, sample.y_mm]); return `<circle cx="${point[0]}" cy="${point[1]}" r="3" fill="${color(sample.value)}"/>`; }).join("");
  const format = (value: number) => value.toLocaleString("en-US", { maximumSignificantDigits: 6 });
  return `<figure class="net-plot"><figcaption>${escapeHtml(label)} <span>${format(range.minimum)} to ${format(range.maximum)} ${escapeHtml(unit)}</span></figcaption><svg viewBox="0 0 700 125" role="img" aria-label="${escapeHtml(label)} explicit field preview">${marks}</svg><small>${faceSamples.length ? "Explicit solver faces" : "Disconnected returned points"}; no values are inferred across gaps.</small></figure>`;
}
