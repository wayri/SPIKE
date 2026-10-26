// SPDX-License-Identifier: Apache-2.0

import { numericExtent } from "./numericRange";

export type Complex = [number, number];
export type SiSpatialNoiseQuantity = "induced_voltage" | "electric_field";
export type SiSpatialNoiseProjection = "magnitude" | "real" | "imaginary" | "phase" | "instantaneous";
export type SiSpatialNoiseComponent = "norm" | "x" | "y" | "z";

export type SiTraceSegment = {
  id: string; occurrenceId: string; netId: string;
  startMm: [number, number, number]; endMm: [number, number, number];
};
export type SiSpatialNoiseBinding = {
  sourceDesignId: string; sourceDesignDigest: string; requestId: string;
  occurrenceId: string; aggressorNetId: string; victimNetId: string;
};
export type SiSpatialNoiseResult = {
  contract: "spike/si-spatial-noise/v1";
  status: "completed" | "completed_with_warnings";
  modelStatus: string;
  binding: SiSpatialNoiseBinding;
  sourceResult: { contract: string; resultId?: string; rawPointer: string; modelScope: {
    basis: "provided_rlgc" | "extracted_rlgc" | "solved_em_field"; extracted: boolean; limitations: string[];
  } };
  frequenciesHz: number[];
  traceSamples?: Array<{ segmentId: string; fraction: number; inducedVoltageV: Complex[] }>;
  fieldSamples?: Array<{ id: string; positionMm: [number, number, number]; electricFieldVM: [Complex, Complex, Complex][] }>;
  issues?: string[];
};
export type SiSpatialNoiseContext = {
  designId: string; designDigest: string; requestId: string; occurrenceId: string;
  aggressorNetId: string; victimNetId: string; traceSegments: readonly SiTraceSegment[];
};
export type AdmittedSiTraceNoiseSample = NonNullable<SiSpatialNoiseResult["traceSamples"]>[number] & { positionMm: [number, number, number] };
export type AdmittedSiSpatialNoise = Omit<SiSpatialNoiseResult, "traceSamples" | "fieldSamples"> & {
  traceSamples: AdmittedSiTraceNoiseSample[];
  fieldSamples: NonNullable<SiSpatialNoiseResult["fieldSamples"]>;
};
export type SiSpatialNoiseSettings = {
  quantity: SiSpatialNoiseQuantity; frequencyIndex: number; projection: SiSpatialNoiseProjection;
  component: SiSpatialNoiseComponent; phaseDeg: number; opacity: number; scaleLimit: number | null;
};
export const defaultSiSpatialNoiseSettings: SiSpatialNoiseSettings = {
  quantity: "induced_voltage", frequencyIndex: 0, projection: "magnitude", component: "norm",
  phaseDeg: 0, opacity: .72, scaleLimit: null,
};
export type SiSpatialNoiseDisplay = {
  quantity: SiSpatialNoiseQuantity; label: string; unit: "V" | "V/m" | "degrees"; frequencyHz: number;
  positionsMm: [number, number, number][]; values: number[]; sourceIds: string[];
  range: [number, number]; opacity: number; modelStatus: string; notices: string[];
};
export type SiSpatialNoiseViewport = {
  display: SiSpatialNoiseDisplay; binding: SiSpatialNoiseBinding;
  sourceDesign: Record<string, unknown>; selectedSample: number | null;
  origin?: "imported" | "supplied_pair";
  onSelectSample: (index: number) => void;
};

/** Exact sample coordinates: canonical board mm to centered, Y-flipped viewport units. */
export function siSpatialNoiseScenePosition(point: [number, number, number], transform: { centerX: number; centerY: number; scale: number }): [number, number, number] {
  return [(point[0] - transform.centerX) * transform.scale, (transform.centerY - point[1]) * transform.scale, point[2] * transform.scale];
}

export function siSpatialNoiseColor(value: number, range: [number, number]): [number, number, number] {
  const fraction = range[1] === range[0] ? .5 : Math.max(0, Math.min(1, (value - range[0]) / (range[1] - range[0])));
  // Blue -> cyan -> yellow. This only maps admitted sample scalars to colors.
  return [Math.max(0, 2 * fraction - 1), Math.min(1, 2 * fraction), 1 - fraction];
}

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const complex = (value: unknown): value is Complex => Array.isArray(value) && value.length === 2 && value.every(finite);
const position = (value: unknown): value is [number, number, number] => Array.isArray(value) && value.length === 3 && value.every(finite);
const safeId = (value: unknown) => typeof value === "string" && value.length > 0 && value.length <= 512;

/** Admit only result samples bound to the exact design revision, request, board occurrence and two net identities. */
export function admitSiSpatialNoise(value: unknown, context: SiSpatialNoiseContext): AdmittedSiSpatialNoise | null {
  if (!value || typeof value !== "object") return null;
  const result = value as SiSpatialNoiseResult, binding = result.binding;
  if (!Array.isArray(context.traceSegments) || context.traceSegments.length > 200000 || ![context.designId, context.designDigest, context.requestId, context.occurrenceId, context.aggressorNetId, context.victimNetId].every(safeId)
    || context.traceSegments.some(segment => !segment || !safeId(segment.id) || !position(segment.startMm) || !position(segment.endMm))
    || new Set(context.traceSegments.map(segment => segment.id)).size !== context.traceSegments.length) return null;
  if (result.contract !== "spike/si-spatial-noise/v1" || !["completed", "completed_with_warnings"].includes(result.status)
    || !safeId(result.modelStatus) || !binding || binding.sourceDesignId !== context.designId
    || binding.sourceDesignDigest !== context.designDigest || binding.requestId !== context.requestId
    || binding.occurrenceId !== context.occurrenceId || binding.aggressorNetId !== context.aggressorNetId
    || binding.victimNetId !== context.victimNetId || binding.aggressorNetId === binding.victimNetId
    || !result.sourceResult || !safeId(result.sourceResult.contract) || !safeId(result.sourceResult.rawPointer)
    || !result.sourceResult.modelScope || !["provided_rlgc", "extracted_rlgc", "solved_em_field"].includes(result.sourceResult.modelScope.basis)
    || typeof result.sourceResult.modelScope.extracted !== "boolean" || !Array.isArray(result.sourceResult.modelScope.limitations)
    || result.sourceResult.modelScope.limitations.length > 100 || result.sourceResult.modelScope.limitations.some(limit => !safeId(limit))
    || !Array.isArray(result.frequenciesHz) || !result.frequenciesHz.length || result.frequenciesHz.length > 10000
    || result.frequenciesHz.some((frequency, index) => !finite(frequency) || frequency <= 0 || index > 0 && frequency <= result.frequenciesHz[index - 1])) return null;
  const segmentIndex = new Map<string, SiTraceSegment>(context.traceSegments.map(segment => [segment.id, segment]));
  const traceSamples = result.traceSamples === undefined ? [] : result.traceSamples;
  if (!Array.isArray(traceSamples) || traceSamples.length > 200000 || traceSamples.some(sample => {
    if (!sample || !safeId(sample.segmentId)) return true;
    const segment = segmentIndex.get(sample.segmentId);
    return !segment || segment.occurrenceId !== binding.occurrenceId || segment.netId !== binding.victimNetId
      || !finite(sample.fraction) || sample.fraction < 0 || sample.fraction > 1
      || !Array.isArray(sample.inducedVoltageV) || sample.inducedVoltageV.length !== result.frequenciesHz.length
      || !sample.inducedVoltageV.every(complex);
  })) return null;
  const fieldSamples = result.fieldSamples === undefined ? [] : result.fieldSamples;
  if (!Array.isArray(fieldSamples) || fieldSamples.length > 200000
    || (traceSamples.length + fieldSamples.length) > 200000
    || (traceSamples.length + fieldSamples.length * 3) * result.frequenciesHz.length > 2000000
    || fieldSamples.some(sample => !sample || !safeId(sample.id) || !position(sample.positionMm)
    || !Array.isArray(sample.electricFieldVM) || sample.electricFieldVM.length !== result.frequenciesHz.length
    || !sample.electricFieldVM.every(vector => Array.isArray(vector) && vector.length === 3 && vector.every(complex)))) return null;
  if (!traceSamples.length && !fieldSamples.length
    || new Set(fieldSamples.map(sample => sample.id)).size !== fieldSamples.length
    || new Set(traceSamples.map(sample => `${sample.segmentId}:${sample.fraction}`)).size !== traceSamples.length
    || result.issues !== undefined && (!Array.isArray(result.issues) || result.issues.length > 100 || result.issues.some(issue => !safeId(issue)))) return null;
  return { ...result, traceSamples: traceSamples.map(sample => {
    const segment = segmentIndex.get(sample.segmentId)!;
    return { ...sample, positionMm: segment.startMm.map((start, axis) => start + sample.fraction * (segment.endMm[axis] - start)) as [number, number, number] };
  }), fieldSamples } as AdmittedSiSpatialNoise;
}

function projectScalar(value: Complex, projection: SiSpatialNoiseProjection, phaseDeg: number): number | null {
  if (projection === "magnitude") return Math.hypot(...value);
  if (projection === "real") return value[0];
  if (projection === "imaginary") return value[1];
  if (projection === "phase") return value[0] === 0 && value[1] === 0 ? null : Math.atan2(value[1], value[0]) * 180 / Math.PI;
  const phase = phaseDeg * Math.PI / 180;
  return value[0] * Math.cos(phase) - value[1] * Math.sin(phase);
}

export function availableSiSpatialNoiseQuantities(data: AdmittedSiSpatialNoise): SiSpatialNoiseQuantity[] {
  return [...(data.traceSamples.length ? ["induced_voltage" as const] : []), ...(data.fieldSamples.length ? ["electric_field" as const] : [])];
}

/** Build display samples without interpolation, distance falloff, or conversion of port metrics into spatial values. */
export function buildSiSpatialNoiseDisplay(data: AdmittedSiSpatialNoise, settings: SiSpatialNoiseSettings): SiSpatialNoiseDisplay | null {
  if (!availableSiSpatialNoiseQuantities(data).includes(settings.quantity) || !Number.isInteger(settings.frequencyIndex)
    || !["magnitude", "real", "imaginary", "phase", "instantaneous"].includes(settings.projection)
    || !["norm", "x", "y", "z"].includes(settings.component)
    || settings.frequencyIndex < 0 || settings.frequencyIndex >= data.frequenciesHz.length || !finite(settings.phaseDeg)
    || !finite(settings.opacity) || settings.opacity < .05 || settings.opacity > 1
    || settings.scaleLimit !== null && (!finite(settings.scaleLimit) || settings.scaleLimit <= 0)) return null;
  let positionsMm: [number, number, number][], sourceIds: string[], projected: Array<number | null>;
  if (settings.quantity === "induced_voltage") {
    positionsMm = data.traceSamples.map(sample => sample.positionMm); sourceIds = data.traceSamples.map(sample => sample.segmentId);
    projected = data.traceSamples.map(sample => projectScalar(sample.inducedVoltageV[settings.frequencyIndex], settings.projection, settings.phaseDeg));
  } else {
    if (settings.component === "norm" && settings.projection !== "magnitude") return null;
    positionsMm = data.fieldSamples.map(sample => sample.positionMm); sourceIds = data.fieldSamples.map(sample => sample.id);
    projected = data.fieldSamples.map(sample => {
      const vector = sample.electricFieldVM[settings.frequencyIndex];
      if (settings.component === "norm") return Math.hypot(...vector.flat());
      return projectScalar(vector[{ x: 0, y: 1, z: 2 }[settings.component]], settings.projection, settings.phaseDeg);
    });
  }
  if (!projected.length || projected.some(value => value === null || !finite(value))) return null;
  const raw = projected as number[], limit = settings.scaleLimit;
  const values = limit === null ? raw : raw.map(value => Math.max(-limit, Math.min(limit, value)));
  const { minimum: low, maximum: high } = numericExtent(values);
  return { quantity: settings.quantity, label: settings.quantity === "induced_voltage" ? "Induced victim-trace voltage" : "Surrounding electric field",
    unit: settings.projection === "phase" ? "degrees" : settings.quantity === "induced_voltage" ? "V" : "V/m",
    frequencyHz: data.frequenciesHz[settings.frequencyIndex], positionsMm, values, sourceIds, range: [low, high], opacity: settings.opacity,
    modelStatus: data.modelStatus, notices: [
      "Only returned spatial samples are colored; the display does not infer distance falloff or paint global crosstalk metrics.",
      settings.quantity === "induced_voltage" ? "Positions are derived from authoritative victim-trace segments and returned segment fractions." : "Electric-field points use returned solver coordinates; voltage samples are never labelled as field.",
      ...(settings.projection === "instantaneous" ? ["Phase-rotated real projection preserves source phasor units; no peak/RMS amplitude conversion or transient solve is performed."] : []),
      ...(limit === null ? [] : [`Display values are clipped at ${limit} ${settings.projection === "phase" ? "degrees" : settings.quantity === "induced_voltage" ? "V" : "V/m"}; source samples are unchanged.`]),
    ] };
}

export function searchSiSpatialNoiseSamples(display: SiSpatialNoiseDisplay, query: string): number[] {
  const term = query.trim().toLowerCase();
  if (!term) return display.sourceIds.map((_, index) => index);
  return display.sourceIds.map((id, index) => ({ id, index })).filter(row => row.id.toLowerCase().includes(term) || String(row.index).includes(term)).map(row => row.index);
}
