// SPDX-License-Identifier: Apache-2.0
import type { Vector } from "./emergeNearFieldSamples";
export type AssemblyEmStudy = {contract:"spike/assembly-em-study/v1";request:Record<string,any>;result:Record<string,any>|null};
export function assemblyEmStudyByteLimit(study: any): number {
  const geometry=study?.request?.geometry ?? study?.geometry;
  return geometry?.domain==="em" && geometry?.resource_profile==="routed_pcb_em_v1" ? 128*1024*1024 : 8*1024*1024;
}
export function assemblyEmStudy(value: unknown): AssemblyEmStudy {
  const raw=value as any;
  const study=raw?.contract==="spike/assembly-em-request/v1"?{contract:"spike/assembly-em-study/v1",request:raw,result:null}:raw;
  if(!study || study.contract!=="spike/assembly-em-study/v1" || study.request?.contract!=="spike/assembly-em-request/v1"
    || !(study.result===null || study.result?.contract==="spike/assembly-em-result/v1")
    || new TextEncoder().encode(JSON.stringify(study)).length>assemblyEmStudyByteLimit(study))throw new Error("Invalid or oversized retained assembly EM study.");
  return study;
}
export function retainedEmPreview(value: unknown, quantity:string) {
  const raw=value as any;
  if(raw?.contract!=="spike/assembly-em-preview/v1" || raw.coordinate_frame!=="assembly"
    || raw.coordinate_units!=="m" || raw.normalization!=="1V_peak_incident"
    || !Number.isFinite(raw.frequency_hz) || raw.frequency_hz<=0)return null;
  const name=quantity==="volume_e"?"electric-field":quantity==="volume_h"?"magnetic-field":"";
  const data=raw.datasets?.[name], unit=name==="electric-field"?"V/m":"A/m";
  if(!data || data.units!==unit || !Array.isArray(data.positions_m) || !data.positions_m.length || data.positions_m.length>8000
    || !Array.isArray(data.vectors) || data.vectors.length!==data.positions_m.length
    || !Array.isArray(data.native_indices) || data.native_indices.length!==data.positions_m.length
    || !Number.isInteger(data.source_sample_count) || data.source_sample_count<data.positions_m.length)return null;
  const finite=(v:unknown)=>typeof v==="number"&&Number.isFinite(v);
  if(data.positions_m.some((p:any)=>!Array.isArray(p)||p.length!==3||!p.every(finite))
    || data.vectors.some((v:any)=>!Array.isArray(v)||v.length!==3||v.some((p:any)=>!Array.isArray(p)||p.length!==2||!p.every(finite)))
    || data.native_indices.some((i:any)=>!Number.isInteger(i)||i<0||i>=data.source_sample_count)
    || new Set(data.native_indices).size!==data.native_indices.length)return null;
  return {frequencyHz:raw.frequency_hz,unit:`${unit} · 1 V peak incident`,
    positionsMm:data.positions_m.map((p:number[])=>p.map(v=>v*1000) as [number,number,number]),
    vectors:data.vectors as Vector[], nativeIndices:data.native_indices as number[], sourceSampleCount:data.source_sample_count as number};
}
