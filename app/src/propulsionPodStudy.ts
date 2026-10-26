// SPDX-License-Identifier: Apache-2.0
import {admitGeometryPodStudy,type GeometryPodStudy} from "./geometryPodStudy";
export type PropulsionPodSample = { time_s: number; currents_a: number[]; speed_rad_s: number; temperature_k: number[]; neutral_voltage_v: number };
export type PropulsionPodFrame = { time_s: number; element_b_t: number[][]; temperature_k: number[] };
export type PropulsionPodResult = { contract: string; status: string; request: Record<string, unknown>; history: PropulsionPodSample[];
  frames: PropulsionPodFrame[]; field_mesh: { nodes_m: number[][]; triangles: number[][]; region_ids: string[] };
  thermal_node_names: string[]; energy: Record<string, unknown>; provenance: Record<string, unknown>; limitations: string[] };
export type SyntheticPropulsionPodStudy = { contract?: "spike/propulsion-pod-ui-study/v1"; request: Record<string, unknown>; result: PropulsionPodResult | null; captured_at?: string };
export type PropulsionPodStudy = SyntheticPropulsionPodStudy | GeometryPodStudy;
const object = (x: unknown): x is Record<string, unknown> => Boolean(x && typeof x === "object" && !Array.isArray(x));
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const vector = (x: unknown, n: number): x is number[] => Array.isArray(x) && x.length === n && x.every(finite);
export function parsePropulsionPodRequest(text: string): Record<string, unknown> {
  if (text.length > 1_000_000) throw new Error("Setup exceeds 1 MB.");
  const value: unknown = JSON.parse(text);
  if (!object(value) || value.contract !== "spike/propulsion-pod-three-phase-request/v1") throw new Error("Expected a three-phase propulsion request v1.");
  return value;
}
function finiteJson(value: unknown): void {
  const pending: unknown[]=[value],seen=new Set<object>();let count=0;
  while(pending.length){const x=pending.pop();if(++count>2_000_000)throw new Error("Capture exceeds the value budget.");
    if(typeof x === "number" && !Number.isFinite(x))throw new Error("Capture contains a nonfinite number.");
    if(x && typeof x === "object"){if(seen.has(x))throw new Error("Capture contains a cycle or shared object.");seen.add(x);for(const child of Object.values(x))pending.push(child);}
  }
}
export function admitPropulsionPodResult(value: unknown): PropulsionPodResult {
  finiteJson(value);
  if (!object(value) || value.contract !== "spike/propulsion-pod-three-phase-result/v1" || value.status !== "completed") throw new Error("Worker did not return a completed three-phase result.");
  if (JSON.stringify(value).length > 14*1024*1024) throw new Error("Result exceeds the 14 MB capture budget.");
  if (!object(value.request) || !object(value.energy) || !object(value.provenance) || !Array.isArray(value.limitations) || !value.limitations.every(x => typeof x === "string")) throw new Error("Result evidence is incomplete.");
  if (!Array.isArray(value.history) || !value.history.length || value.history.length > 20001 || !value.history.every((s: unknown) => object(s) && finite(s.time_s) && vector(s.currents_a,3) && finite(s.speed_rad_s) && vector(s.temperature_k,11) && finite(s.neutral_voltage_v))) throw new Error("Invalid current, speed or temperature history.");
  const mesh=value.field_mesh;
  if (!object(mesh) || !Array.isArray(mesh.nodes_m) || mesh.nodes_m.length > 12000 || !mesh.nodes_m.every(x => vector(x,2)) || !Array.isArray(mesh.triangles) || mesh.triangles.length > 24000 || !mesh.triangles.every(x => vector(x,3) && x.every(i => Number.isInteger(i) && i >= 0 && i < (mesh.nodes_m as unknown[]).length))) throw new Error("Invalid field mesh.");
  if (!Array.isArray(mesh.region_ids) || mesh.region_ids.length !== mesh.triangles.length || !mesh.region_ids.every(x => typeof x === "string")) throw new Error("Invalid field region identities.");
  if (!Array.isArray(value.frames) || !value.frames.length || value.frames.length > 101 || !value.frames.every((f: unknown) => object(f) && finite(f.time_s) && vector(f.temperature_k,11) && Array.isArray(f.element_b_t) && f.element_b_t.length === (mesh.triangles as unknown[]).length && f.element_b_t.every(x => vector(x,2)))) throw new Error("Invalid returned field frames.");
  if (!Array.isArray(value.thermal_node_names) || value.thermal_node_names.length !== 11 || !value.thermal_node_names.every(x => typeof x === "string")) throw new Error("Eleven thermal node names are required.");
  return value as unknown as PropulsionPodResult;
}

export function normalizePropulsionPodStudy(value: unknown): PropulsionPodStudy | null {
  try {
    if(object(value)&&value.contract==="spike/geometry-propulsion-ui-study/v1")return admitGeometryPodStudy(value);
    if (!object(value) || (value.contract !== undefined && value.contract !== "spike/propulsion-pod-ui-study/v1") || !object(value.request)) return null;
    const request=parsePropulsionPodRequest(JSON.stringify(value.request));
    const result=value.result == null ? null : admitPropulsionPodResult(value.result);
    return { contract:"spike/propulsion-pod-ui-study/v1", request, result,
      ...(typeof value.captured_at === "string" ? { captured_at:value.captured_at } : {}) };
  } catch { return null; }
}
