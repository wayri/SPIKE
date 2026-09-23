import type { ThermalCoordinateFrame, ThermalPoint3 } from "./thermalScene";
import { numericMaximum } from "./numericRange";

/** A raw, solver-published thermal sample.  The viewport never interpolates it. */
export type ThermalFieldSample = {
  position_mm: ThermalPoint3;
  value: number;
  coordinate_frame?: ThermalCoordinateFrame;
  element_id?: string;
};

export type ThermalFieldName = "temperature_c" | "heat_flux_w_m2" | "temperature_gradient_c_per_mm";

export type ThermalFieldResult = {
  contract?: string;
  status?: string;
  model_status?: string;
  fields?: Partial<Record<ThermalFieldName, ThermalFieldSample[]>>;
};

const finite = (value: unknown): number | null => {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
};

function sample(raw: unknown, valueTransform: (value: unknown) => number | null = finite): ThermalFieldSample | null {
  if (!raw || typeof raw !== "object") return null;
  const item = raw as Record<string, unknown>;
  const pointInMetres = Array.isArray(item.point_m);
  const point = Array.isArray(item.position_mm) ? item.position_mm : Array.isArray(item.point_mm) ? item.point_mm : pointInMetres ? item.point_m as unknown[] : [item.x_mm, item.y_mm, item.z_mm];
  if (point.length < 3) return null;
  const position = point.slice(0, 3).map(value => { const coordinate = finite(value); return coordinate === null ? null : coordinate * (pointInMetres ? 1000 : 1); });
  const value = valueTransform(item.value);
  if (position.some(value => value === null) || value === null) return null;
  const frame = item.coordinate_frame;
  return {
    position_mm: position as ThermalPoint3,
    value,
    coordinate_frame: frame === "board_local" || frame === "board_absolute" || frame === "domain_local" ? frame : "domain_local",
    element_id: typeof item.element_id === "string" ? item.element_id : undefined,
  };
}

/**
 * Imports only explicitly published samples.  This deliberately rejects
 * malformed rows and does not manufacture a field from scalar summaries.
 */
export function normalizeThermalFieldResult(raw: unknown): ThermalFieldResult | null {
  if (!raw || typeof raw !== "object") return null;
  const result = raw as Record<string, unknown>;
  const candidate = result.fields && typeof result.fields === "object" ? result.fields as Record<string, unknown> : result;
  const rows = (value: unknown): unknown[] => Array.isArray(value)
    ? value
    : value && typeof value === "object" && Array.isArray((value as Record<string, unknown>).samples)
      ? (value as { samples: unknown[] }).samples
      : [];
  const magnitude = (value: unknown) => Array.isArray(value) && value.length === 3
    ? Math.hypot(...value.map(component => Number(component)))
    : finite(value);
  const temperatureC = rows(candidate.temperature_c).map(item => sample(item)).filter((item): item is ThermalFieldSample => item !== null);
  // The canonical worker result is Kelvin with point_mm samples. Convert only
  // this explicitly named field; never infer a field from summary extrema.
  if (!temperatureC.length) temperatureC.push(...rows(candidate.temperature_k)
    .map(item => sample(item, value => { const kelvin = finite(value); return kelvin === null ? null : kelvin - 273.15; }))
    .filter((item): item is ThermalFieldSample => item !== null));
  const heatFlux = rows(candidate.heat_flux_w_m2).map(item => sample(item, magnitude)).filter((item): item is ThermalFieldSample => item !== null);
  const gradient = rows(candidate.temperature_gradient_c_per_mm).map(item => sample(item, magnitude)).filter((item): item is ThermalFieldSample => item !== null);
  const fields = Object.fromEntries(([
    ["temperature_c", temperatureC],
    ["heat_flux_w_m2", heatFlux],
    ["temperature_gradient_c_per_mm", gradient],
  ] as Array<[ThermalFieldName, ThermalFieldSample[]]>).filter(([, samples]) => samples.length)) as Partial<Record<ThermalFieldName, ThermalFieldSample[]>>;
  return Object.keys(fields).length ? {
    contract: typeof result.contract === "string" ? result.contract : undefined,
    status: typeof result.status === "string" ? result.status : undefined,
    model_status: typeof result.model_status === "string" ? result.model_status : undefined,
    fields,
  } : null;
}

/**
 * Build the bounded payload retained by React/project snapshots. The complete
 * solver field remains in its digest-bound artifact or prepared case; keeping
 * hundreds of thousands of objects in application state would stall every
 * snapshot, report, and render even though the viewport draws only its LOD.
 */
export function thermalFieldResultPreview(raw: unknown, perFieldLimit = 9000): Record<string, unknown> | null {
  const normalized = normalizeThermalFieldResult(raw);
  if (!normalized?.fields) return null;
  const source = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
  const fields = Object.fromEntries(Object.entries(normalized.fields).map(([name, samples]) => [name, thinThermalFieldSamples(samples ?? [], perFieldLimit)]));
  const publishedSamples = Object.values(normalized.fields).reduce((total, samples) => total + (samples?.length ?? 0), 0);
  const retainedSamples = Object.values(fields).reduce((total, samples) => total + (Array.isArray(samples) ? samples.length : 0), 0);
  return {
    contract: normalized.contract ?? source.contract ?? "spike/thermal-field-result-preview/v1",
    status: normalized.status ?? source.status,
    model_status: normalized.model_status ?? source.model_status,
    summary: source.summary && typeof source.summary === "object" ? source.summary : {},
    qualification: source.qualification && typeof source.qualification === "object" ? source.qualification : {},
    provenance: source.provenance && typeof source.provenance === "object" ? source.provenance : {},
    resource_usage: source.resource_usage && typeof source.resource_usage === "object" ? source.resource_usage : {},
    fields,
    visualization: {
      published_preview_samples: publishedSamples,
      retained_samples: retainedSamples,
      decimated: retainedSamples < publishedSamples,
      per_field_limit: Math.max(3, Math.floor(perFieldLimit)),
      full_field_location: "solver_artifact_or_prepared_case",
    },
  };
}

export function thermalFieldExtent(samples: ThermalFieldSample[]) {
  return samples.reduce((extent, sample) => ({ minimum: Math.min(extent.minimum, sample.value), maximum: Math.max(extent.maximum, sample.value) }), {
    minimum: Number.POSITIVE_INFINITY, maximum: Number.NEGATIVE_INFINITY,
  });
}

/**
 * Deterministic voxel LOD.  Representatives are original solver samples,
 * with global extrema retained, so large data stays interactive without
 * pretending a coarser display is a newly solved field.
 */
export function thinThermalFieldSamples(samples: ThermalFieldSample[], limit = 9000): ThermalFieldSample[] {
  const maximum = Math.max(3, Math.floor(limit));
  if (samples.length <= maximum) return samples;
  const finiteSamples = samples.filter(sample => sample.position_mm.every(Number.isFinite) && Number.isFinite(sample.value));
  if (finiteSamples.length <= maximum) return finiteSamples;
  // Do not materialize three additional million-entry arrays or spread them
  // into Math.min/Math.max. Both patterns become a memory/call-stack failure
  // well before the field contract's upper sample bound.
  const mins = [Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY];
  const maxs = [Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY, Number.NEGATIVE_INFINITY];
  let minimumSample = finiteSamples[0];
  let maximumSample = finiteSamples[0];
  finiteSamples.forEach(item => {
    for (let axis = 0; axis < 3; axis += 1) {
      mins[axis] = Math.min(mins[axis], item.position_mm[axis]);
      maxs[axis] = Math.max(maxs[axis], item.position_mm[axis]);
    }
    if (item.value < minimumSample.value) minimumSample = item;
    if (item.value > maximumSample.value) maximumSample = item;
  });
  const span = numericMaximum(maxs.map((value, axis) => value - mins[axis]), 1e-6);
  let cell = span / Math.cbrt(maximum);
  let retained: ThermalFieldSample[] = finiteSamples;
  for (let pass = 0; pass < 8; pass += 1) {
    const bins = new Map<string, { item: ThermalFieldSample; total: number; count: number }>();
    finiteSamples.forEach(item => {
      const key = item.position_mm.map((value, axis) => Math.floor((value - mins[axis]) / cell)).join(":");
      const current = bins.get(key);
      if (current) { current.total += item.value; current.count += 1; if (Math.abs(item.value - current.total / current.count) < Math.abs(current.item.value - current.total / current.count)) current.item = item; }
      else bins.set(key, { item, total: item.value, count: 1 });
    });
    retained = [...bins.values()].map(entry => entry.item);
    if (retained.length <= maximum - 2) break;
    cell *= Math.max(1.18, Math.cbrt(retained.length / maximum) * 1.04);
  }
  const mustKeep = [minimumSample, maximumSample];
  const output = [...new Set([...mustKeep, ...retained])];
  return output.slice(0, maximum);
}

/** Blue/cyan/yellow/red scientific palette, mapped only over published values. */
export function thermalFieldColor(value: number, minimum: number, maximum: number): [number, number, number] {
  const t = maximum > minimum ? Math.max(0, Math.min(1, (value - minimum) / (maximum - minimum))) : 0.5;
  const stops: [number, number, number][] = [[0.12, 0.35, 0.92], [0.18, 0.8, 0.8], [0.85, 0.88, 0.24], [0.94, 0.2, 0.16]];
  const scaled = t * (stops.length - 1); const index = Math.min(stops.length - 2, Math.floor(scaled)); const local = scaled - index;
  return stops[index].map((channel, axis) => channel + (stops[index + 1][axis] - channel) * local) as [number, number, number];
}
