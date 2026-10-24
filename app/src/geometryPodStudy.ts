// SPDX-License-Identifier: Apache-2.0
// Presentation admission only: numerical convergence is established separately.
export type GeometryPodSample = {
  time_s:number; currents_a:number[]; speed_rad_s:number; angle_rad:number;
  temperature_k:number[]; duty:number[]; field_torque_n_m:number;
  preceding_interval:null | { start_time_s:number; end_time_s:number;
    field_torque_dg_n_m:number; fluid_midpoint:{torque_nm:number; thrust_n:number; power_w:number};
    energy_j:Record<string,number> };
};
export type GeometryPodField = {history_index:number;snapshot:{angle_rad:number;currents_a:number[];
  source_sha256:string;geometry_sha256:string;domains:Record<"rotor"|"stator",{
    nodes_m:number[][];triangles:number[][];element_b_t:number[][];source_field_sha256:string;
    source_element_ids:number[];presentation_only:true;source_field_order:2}>}};
export type GeometryPodResult = {
  contract:"spike/geometry-propulsion-loop-result/v1"; status:"completed";
  request:Record<string,unknown>; history:GeometryPodSample[]; accepted_steps:number;
  controller_ticks:number; energy:Record<string,number>; field_table_sha256:string;
  fluid_port_sha256:string; controller_executable_sha256:string; orchestrator_sha256:string;
  physical_load_qualified:false; production_qualified:false; scope:string;
  field_snapshots?:GeometryPodField[];
};
export type GeometryPodInputs = {magnetic_table:Record<string,unknown>;cfd_table:Record<string,unknown>;
  field_table_sha256:string;fluid_port_sha256:string};
export type GeometryPodStudy = { contract:"spike/geometry-propulsion-ui-study/v1";
  request:Record<string,unknown>; result:GeometryPodResult|null; captured_at?:string;inputs?:GeometryPodInputs;notices?:string[] };
const object=(x:unknown):x is Record<string,unknown>=>Boolean(x&&typeof x==="object"&&!Array.isArray(x));
const finite=(x:unknown):x is number=>typeof x==="number"&&Number.isFinite(x);
const vector=(x:unknown,n:number):x is number[]=>Array.isArray(x)&&x.length===n&&x.every(finite);
const hash=(x:unknown)=>typeof x==="string"&&/^[a-f0-9]{64}$/.test(x);
const sameTime=(a:unknown,b:number)=>finite(a)&&Math.abs(a-b)<=32*Number.EPSILON*Math.max(Math.abs(a),Math.abs(b),1e-12);
const ledger=(x:unknown):x is Record<string,number>=>object(x)&&finite(x.defect_j)&&Object.values(x).every(finite);
function boundedJson(value:unknown) {
  const stack=[value],seen=new Set<object>();let count=0;
  while(stack.length){const x=stack.pop();if(++count>2_000_000)throw new Error("Geometry capture exceeds the value budget.");
    if(typeof x==="number"&&!Number.isFinite(x))throw new Error("Nonfinite geometry capture.");
    if(x&&typeof x==="object"){if(seen.has(x))throw new Error("Cyclic or shared geometry capture.");seen.add(x);for(const child of Object.values(x))stack.push(child);}}
  if(JSON.stringify(value).length>14*1024*1024)throw new Error("Geometry capture exceeds 14 MB.");
}
export function admitGeometryPodResult(value:unknown):GeometryPodResult {
  boundedJson(value);
  if(!object(value)||value.contract!=="spike/geometry-propulsion-loop-result/v1"||value.status!=="completed")throw new Error("Expected a completed geometry propulsion loop v1.");
  if(value.production_qualified!==false||value.physical_load_qualified!==false)throw new Error("This experimental capture cannot assert physical qualification.");
  if(!object(value.request)||!ledger(value.energy)||typeof value.scope!=="string"||!value.scope)throw new Error("Missing geometry loop evidence.");
  for(const key of ["field_table_sha256","fluid_port_sha256","controller_executable_sha256","orchestrator_sha256"])if(!hash(value[key]))throw new Error("Missing source hash: "+key);
  if(!Number.isInteger(value.accepted_steps)||Number(value.accepted_steps)<1||Number(value.accepted_steps)>20000||!Number.isInteger(value.controller_ticks)||Number(value.controller_ticks)<1||Number(value.controller_ticks)>Number(value.accepted_steps))throw new Error("Invalid loop counts.");
  if(!Array.isArray(value.history)||value.history.length!==Number(value.accepted_steps)+1)throw new Error("Incomplete accepted history.");
  let previous=0;
  value.history.forEach((s:unknown,index:number)=>{
    if(!object(s)||!finite(s.time_s)||(index===0?s.time_s!==0:s.time_s<=previous)||!vector(s.currents_a,3)||!vector(s.temperature_k,11)||s.temperature_k.some(t=>t<=0)||!vector(s.duty,3)||s.duty.some(d=>d<0||d>1)||!finite(s.speed_rad_s)||!finite(s.angle_rad)||!finite(s.field_torque_n_m))throw new Error("Invalid geometry history sample.");
    if(Math.abs(s.currents_a.reduce((a,b)=>a+b,0))>1e-8)throw new Error("Unbalanced phase history.");
    const interval=s.preceding_interval;
    if(index===0){if(interval!==null)throw new Error("Initial state cannot contain an interval load.");}
    else if(!object(interval)||!sameTime(interval.start_time_s,previous)||!sameTime(interval.end_time_s,s.time_s)||!finite(interval.field_torque_dg_n_m)||!object(interval.fluid_midpoint)||![interval.fluid_midpoint.torque_nm,interval.fluid_midpoint.thrust_n,interval.fluid_midpoint.power_w].every(finite)||!ledger(interval.energy_j))throw new Error("Invalid preceding interval evidence.");
    previous=s.time_s;
  });
  if(value.field_snapshots!==undefined){
    const derivation=value.field_snapshot_derivation;
    if(!object(derivation)||![derivation.input_result_file_sha256,derivation.domain_file_sha256,derivation.magnetic_table_file_sha256,derivation.source_sha256,derivation.geometry_sha256].every(hash))throw new Error("Missing spatial field derivation.");
    if(!Array.isArray(value.field_snapshots)||!value.field_snapshots.length||value.field_snapshots.length>25)throw new Error("Invalid spatial frame count.");
    let last=-1;
    for(const frame of value.field_snapshots){
      if(!object(frame)||!Number.isInteger(frame.history_index)||Number(frame.history_index)<=last||Number(frame.history_index)>=value.history.length||!object(frame.snapshot))throw new Error("Invalid spatial state reference.");
      last=Number(frame.history_index);const state=value.history[last],field=frame.snapshot;
      if(field.world_frame!==true||field.physical_qualified!==false||field.angle_rad!==state.angle_rad||!vector(field.currents_a,3)||field.currents_a.some((v,j)=>v!==state.currents_a[j])||field.source_sha256!==derivation.source_sha256||field.geometry_sha256!==derivation.geometry_sha256||!object(field.domains)||Object.keys(field.domains).sort().join(",")!=="rotor,stator")throw new Error("Spatial frame differs from the accepted state/source.");
      for(const name of ["rotor","stator"]){const mesh=field.domains[name];
        if(!object(mesh)||mesh.presentation_only!==true||mesh.source_field_order!==2||!hash(mesh.source_field_sha256)||!Array.isArray(mesh.nodes_m)||!mesh.nodes_m.length||mesh.nodes_m.length>9409||!mesh.nodes_m.every(v=>vector(v,2))||!Array.isArray(mesh.triangles)||!mesh.triangles.length||mesh.triangles.length>18432||!mesh.triangles.every(t=>vector(t,3)&&t.every(i=>Number.isInteger(i)&&i>=0&&i<(mesh.nodes_m as unknown[]).length)))throw new Error("Invalid spatial display mesh.");
        if(!Array.isArray(mesh.element_b_t)||mesh.element_b_t.length!==mesh.triangles.length||!mesh.element_b_t.every(v=>vector(v,2))||!Array.isArray(mesh.source_element_ids)||mesh.source_element_ids.length!==mesh.triangles.length||!mesh.source_element_ids.every(i=>Number.isInteger(i)&&i>=0))throw new Error("Invalid source field samples.");
      }
    }
  }
  return value as unknown as GeometryPodResult;
}
export function admitGeometryPodStudy(value:unknown):GeometryPodStudy {
  if(!object(value)||value.contract!=="spike/geometry-propulsion-ui-study/v1"||!object(value.request))throw new Error("Unsupported geometry study.");
  boundedJson(value.request);
  if(value.notices!==undefined&&(!Array.isArray(value.notices)||value.notices.length>100||!value.notices.every(n=>typeof n==="string"&&n.length<=10000)))throw new Error("Invalid source assumption notices.");
  const notices=value.notices as string[]|undefined;
  let inputs:GeometryPodInputs|undefined;
  if(value.inputs!==undefined){boundedJson(value.inputs);const i=value.inputs;
    if(!object(i)||!object(i.magnetic_table)||!object(i.cfd_table)||!hash(i.field_table_sha256)||!hash(i.fluid_port_sha256))throw new Error("Missing immutable constitutive inputs.");
    inputs=i as GeometryPodInputs;
  }
  if(value.result===null){return {contract:value.contract,request:value.request,result:null,...(inputs?{inputs}:{}),...(notices?{notices}:{})};}
  const result=admitGeometryPodResult(value.result);
  if(inputs&&(inputs.field_table_sha256!==result.field_table_sha256||inputs.fluid_port_sha256!==result.fluid_port_sha256))throw new Error("Input source hashes differ from captured result.");
  // JSON key ordering is not evidence that inputs differ.
  const canonical=(x:unknown):string=>Array.isArray(x)?"["+x.map(canonical).join(",")+"]":object(x)?"{"+Object.keys(x).sort().map(k=>JSON.stringify(k)+":"+canonical(x[k])).join(",")+"}":JSON.stringify(x);
  if(canonical(value.request)!==canonical(result.request))throw new Error("Captured setup differs from the solved setup.");
  return {contract:value.contract,request:result.request,result,...(inputs?{inputs}:{}),...(notices?{notices}:{}),...(typeof value.captured_at==="string"?{captured_at:value.captured_at}:{})};
}
