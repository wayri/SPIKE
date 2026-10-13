// SPDX-License-Identifier: Apache-2.0

export type TracePopupIdentity = {
  id: string;
  net?: string;
  layer?: string;
  position: [number, number];
};

type ScalarDatum = {
  value: number;
  x_mm: number;
  y_mm: number;
  element_id?: string;
  net?: string;
  layer?: string;
};

type ScalarFields = {
  voltage_v?: ScalarDatum[];
  current_a?: ScalarDatum[];
};

type ResultFrame = {
  time_s: number;
  scalar_fields?: ScalarFields;
  scalar_values?: Record<string, number[]>;
};

export type TracePopupResult = {
  scalar_fields?: ScalarFields;
  time_series?: {
    times_s?: number[];
    frames?: ResultFrame[];
    layouts?: Record<string, Omit<ScalarDatum, "value">[]>;
    field_layouts?: Record<string, string>;
  };
};

export type TracePopupSeries = {
  quantity: "voltage" | "current";
  label: string;
  unit: "V" | "A";
  value?: number;
  source: "trace_id" | "nearby";
  history: { timeS: number; value: number }[];
};

export type TracePopupModel = {
  traceId: string;
  net: string;
  layer: string;
  series: TracePopupSeries[];
  unavailable: string[];
};

const FIELD_INFO = [
  ["voltage_v", "voltage", "Voltage", "V"],
  ["current_a", "current", "Current", "A"],
] as const;

function sameLayer(sample: Omit<ScalarDatum, "value">, trace: TracePopupIdentity): boolean {
  return !trace.layer || trace.layer === "through" || !sample.layer || sample.layer === "through" || sample.layer === trace.layer;
}

type SampleMatch = { index: number; source: "trace_id" | "nearby" };

function matchingSample(samples: readonly Omit<ScalarDatum, "value">[], trace: TracePopupIdentity): SampleMatch | undefined {
  const exact = samples.findIndex(sample => sample.element_id === trace.id && sameLayer(sample, trace));
  if (exact >= 0) return { index: exact, source: "trace_id" };
  const contextual = samples.map((sample, index) => ({ sample, index }))
    .filter(({ sample }) => (!trace.net || sample.net === trace.net) && sameLayer(sample, trace))
    .filter(({ sample }) => Number.isFinite(sample.x_mm) && Number.isFinite(sample.y_mm))
    .map(candidate => ({ ...candidate, distance: Math.hypot(candidate.sample.x_mm - trace.position[0], candidate.sample.y_mm - trace.position[1]) }))
    .sort((left, right) => left.distance - right.distance)[0];
  // A sample on the same net but elsewhere is not a value for this picked trace.
  return contextual && contextual.distance <= 0.5 ? { index: contextual.index, source: "nearby" } : undefined;
}

function finiteSample(samples: readonly ScalarDatum[] | undefined, trace: TracePopupIdentity): { sample: ScalarDatum; source: SampleMatch["source"] } | undefined {
  if (!samples?.length) return undefined;
  const match = matchingSample(samples, trace);
  const sample = match ? samples[match.index] : undefined;
  return sample && Number.isFinite(sample.value) ? { sample, source: match!.source } : undefined;
}

function bounded<T>(values: readonly T[], limit: number): T[] {
  if (values.length <= limit) return [...values];
  if (limit <= 1) return [values[values.length - 1]];
  return Array.from({ length: limit }, (_, index) => values[Math.round(index * (values.length - 1) / (limit - 1))]);
}

function fieldHistory(result: TracePopupResult, field: "voltage_v" | "current_a", trace: TracePopupIdentity, limit: number) {
  const frames = result.time_series?.frames ?? [];
  const layouts = result.time_series?.layouts ?? {};
  const layout = layouts[result.time_series?.field_layouts?.[field] ?? field] ?? [];
  const compactMatch = matchingSample(layout, trace);
  let explicitSource: SampleMatch["source"] | undefined;
  const points = frames.flatMap(frame => {
    if (!Number.isFinite(frame.time_s)) return [];
    const explicit = finiteSample(frame.scalar_fields?.[field], trace);
    if (explicit) {
      if (explicit.source === "trace_id" || !explicitSource) explicitSource = explicit.source;
      return [{ timeS: frame.time_s, value: explicit.sample.value }];
    }
    const value = compactMatch ? frame.scalar_values?.[field]?.[compactMatch.index] : undefined;
    return Number.isFinite(value) ? [{ timeS: frame.time_s, value: value as number }] : [];
  });
  return { points: bounded(points, Math.max(2, Math.min(128, Math.floor(limit)))), source: explicitSource ?? compactMatch?.source };
}

export function traceSparklinePoints(history: readonly { timeS: number; value: number }[], width = 92, height = 20): [number, number][] {
  if (!history.length) return [];
  let minimumTime = history[0].timeS, maximumTime = history[0].timeS;
  let minimumValue = history[0].value, maximumValue = history[0].value;
  for (const point of history) {
    minimumTime = Math.min(minimumTime, point.timeS); maximumTime = Math.max(maximumTime, point.timeS);
    minimumValue = Math.min(minimumValue, point.value); maximumValue = Math.max(maximumValue, point.value);
  }
  const timeSpan = maximumTime - minimumTime, valueSpan = maximumValue - minimumValue;
  return history.map(point => [
    timeSpan > 0 ? (point.timeS - minimumTime) / timeSpan * width : width / 2,
    valueSpan > 0 ? height - (point.value - minimumValue) / valueSpan * height : height / 2,
  ]);
}

export function traceValuePopupModel(result: TracePopupResult | null | undefined, trace: TracePopupIdentity, historyLimit = 48): TracePopupModel {
  const series: TracePopupSeries[] = [];
  const unavailable: string[] = [];
  for (const [field, quantity, label, unit] of FIELD_INFO) {
    const sample = finiteSample(result?.scalar_fields?.[field], trace);
    const history = result ? fieldHistory(result, field, trace, historyLimit) : { points: [], source: undefined };
    if (!sample && !history.points.length) {
      unavailable.push(`${label} unavailable`);
      continue;
    }
    series.push({ quantity, label, unit, value: sample?.sample.value, source: sample?.source ?? history.source!, history: history.points });
  }
  return {
    traceId: trace.id,
    net: trace.net?.trim() || "Unnamed net",
    layer: trace.layer?.trim() || "Unspecified layer",
    series,
    unavailable,
  };
}
