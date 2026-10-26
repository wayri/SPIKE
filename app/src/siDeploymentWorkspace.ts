// SPDX-License-Identifier: Apache-2.0
import { defaultSiSpatialNoiseSettings } from "./siSpatialNoise";
import type { SiSpatialNoiseSettings } from "./siSpatialNoise";

type Row = Record<string, unknown>;
export type IbisDeploymentWorkspace = {
  contract: "spike/ibis-deployment-workspace/v1";
  request: Row; result: Row | null; resultRequest: Row | null; draft: string;
};
export type SpatialDeploymentWorkspace = {
  contract: "spike/si-spatial-workspace/v1";
  candidate: Row | null; fileName: string; aggressor: string; victim: string;
  requestId: string; pairDraft: string; settings: SiSpatialNoiseSettings;
};
export const SI_WORKSPACE_BYTES = 24 * 1024 * 1024;
const row = (value: unknown): value is Row => Boolean(value && typeof value === "object" && !Array.isArray(value));
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const text = (value: unknown, limit: number): value is string => typeof value === "string" && value.length <= limit;

/** Saved files are data only: reject lossy JSON, cycles, excessive depth and oversized payloads. */
export function boundedSiWorkspaceJson(value: unknown): boolean {
  const ancestors = new Set<object>(); let nodes = 0;
  const visit = (item: unknown, depth: number): boolean => {
    if (++nodes > 2500000 || depth > 48) return false;
    if (item === null || typeof item === "boolean") return true;
    if (typeof item === "number") return Number.isFinite(item);
    if (typeof item === "string") return item.length <= SI_WORKSPACE_BYTES;
    if (typeof item !== "object" || ancestors.has(item)) return false;
    if (Object.getOwnPropertySymbols(item).length || Array.isArray(item) && (Object.keys(item).length !== item.length || Object.keys(item).some((key, index) => key !== String(index)))
      || Object.getPrototypeOf(item) !== Object.prototype && !Array.isArray(item) && Object.getPrototypeOf(item) !== null) return false;
    ancestors.add(item);
    const valid = (Array.isArray(item) ? item : Object.values(item)).every(child => visit(child, depth + 1));
    ancestors.delete(item); return valid;
  };
  try { return visit(value, 0) && new TextEncoder().encode(JSON.stringify(value)).byteLength <= SI_WORKSPACE_BYTES; }
  catch { return false; }
}

/** Structural validation only; the worker remains the authority for model compilation. */
export function isIbisDeploymentRequest(value: unknown): value is Row {
  if (!row(value) || value.contract !== "spike/ibis-behavioral-request/v1" || !boundedSiWorkspaceJson(value)) return false;
  for (const role of ["driver", "receiver"]) {
    const endpoint = value[role];
    if (!row(endpoint) || !text(endpoint.text, 8 * 1024 * 1024)
      || ["name", "model", "component", "pin"].some(key => !text(endpoint[key], 4096))
      || ["corner", "capacitance_corner", "package_corner"].some(key => !["typ", "min", "max"].includes(String(endpoint[key])))) return false;
  }
  const { analysis, stimulus, interconnect } = value;
  return row(analysis) && finite(analysis.time_step_s) && finite(analysis.stop_time_s)
    && row(interconnect) && typeof interconnect.kind === "string" && row(stimulus)
    && ["low", "high", "z"].includes(String(stimulus.initial_state)) && Array.isArray(stimulus.transitions)
    && stimulus.transitions.length <= 128 && stimulus.transitions.every(item => row(item) && finite(item.time_s)
      && ["low", "high"].includes(String(item.state)) && Array.isArray(item.waveform_indices)
      && item.waveform_indices.length === 2 && item.waveform_indices.every(index => Number.isSafeInteger(index) && Number(index) >= 0));
}

/** A copied request snapshot binds retained evidence; it grants no executable trust or readiness. */
export function ibisResultForRequest(result: unknown, resultRequest: unknown, request: Row): Row | null {
  if (!isIbisDeploymentRequest(resultRequest) || JSON.stringify(resultRequest) !== JSON.stringify(request)
    || !row(result) || result.contract !== "spike/ibis-behavioral-result/v1"
    || typeof result.status !== "string" || !/^[a-f0-9]{64}$/.test(String(result.request_sha256))
    || !Array.isArray(result.time_s) || result.time_s.length > 200000 || !row(result.probes)
    || !result.time_s.every((time, index, times) => finite(time) && time >= 0 && (index === 0 || time > Number(times[index - 1])))
    || !boundedSiWorkspaceJson(result)) return null;
  if (Object.values(result.probes).some(probe => !Array.isArray(probe) || probe.length !== (result.time_s as unknown[]).length || !probe.every(finite))) return null;
  if (result.status === "completed" && (!(result.time_s.length > 1)
    || ["driver_pad_v", "receiver_pad_v", "driver_die_v", "receiver_die_v"].some(name => !Array.isArray((result.probes as Row)[name])))) return null;
  return result;
}

export function coerceIbisDeploymentWorkspace(value: unknown): IbisDeploymentWorkspace | null {
  if (!row(value) || value.contract !== "spike/ibis-deployment-workspace/v1" || !boundedSiWorkspaceJson(value)
    || !isIbisDeploymentRequest(value.request) || !text(value.draft, 17 * 1024 * 1024)) return null;
  const result = ibisResultForRequest(value.result, value.resultRequest, value.request);
  return { contract: value.contract, request: value.request, result, resultRequest: result ? value.resultRequest as Row : null, draft: value.draft };
}

function spatialSettings(value: unknown): SiSpatialNoiseSettings {
  if (!row(value)) return { ...defaultSiSpatialNoiseSettings };
  return {
    quantity: value.quantity === "electric_field" ? "electric_field" : "induced_voltage",
    frequencyIndex: Number.isSafeInteger(value.frequencyIndex) && Number(value.frequencyIndex) >= 0 && Number(value.frequencyIndex) < 10000 ? Number(value.frequencyIndex) : 0,
    projection: ["magnitude", "real", "imaginary", "phase", "instantaneous"].includes(String(value.projection)) ? value.projection as SiSpatialNoiseSettings["projection"] : "magnitude",
    component: ["norm", "x", "y", "z"].includes(String(value.component)) ? value.component as SiSpatialNoiseSettings["component"] : "norm",
    phaseDeg: finite(value.phaseDeg) ? value.phaseDeg : 0,
    opacity: finite(value.opacity) && value.opacity >= 0 && value.opacity <= 1 ? value.opacity : defaultSiSpatialNoiseSettings.opacity,
    scaleLimit: finite(value.scaleLimit) && value.scaleLimit > 0 ? value.scaleLimit : null,
  };
}

/** Retain a candidate and independent reviewed controls. No capture, binding authority or display survives reopen. */
export function coerceSpatialDeploymentWorkspace(value: unknown): SpatialDeploymentWorkspace | null {
  if (!row(value) || value.contract !== "spike/si-spatial-workspace/v1" || !boundedSiWorkspaceJson(value)
    || !text(value.fileName, 4096) || ![value.aggressor, value.victim, value.requestId].every(item => text(item, 512))
    || !text(value.pairDraft, 2 * 1024 * 1024)) return null;
  const candidate = row(value.candidate) && value.candidate.contract === "spike/si-spatial-noise/v1" ? value.candidate : null;
  return { contract: value.contract, candidate, fileName: value.fileName, aggressor: value.aggressor as string,
    victim: value.victim as string, requestId: value.requestId as string, pairDraft: value.pairDraft, settings: spatialSettings(value.settings) };
}
