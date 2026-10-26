// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';
const compiled=ts.transpileModule(readFileSync(new URL('../src/geometryPodStudy.ts',import.meta.url),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {admitGeometryPodResult,admitGeometryPodStudy}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
// Explicit parser fixture: this is not a retained physical simulation.
const result={contract:'spike/geometry-propulsion-loop-result/v1',status:'completed',request:{b:2,a:1},
  production_qualified:false,physical_load_qualified:false,scope:'Parser fixture',accepted_steps:1,controller_ticks:1,
  energy:{defect_j:0},field_table_sha256:'a'.repeat(64),fluid_port_sha256:'b'.repeat(64),
  controller_executable_sha256:'c'.repeat(64),orchestrator_sha256:'d'.repeat(64),
  history:[0,.001].map(time_s=>({time_s,currents_a:[1,-1,0],temperature_k:Array(11).fill(300),
    duty:[.5,.5,.5],speed_rad_s:20,angle_rad:time_s*20,field_torque_n_m:.1,
    preceding_interval:time_s===0?null:{start_time_s:0,end_time_s:time_s,field_torque_dg_n_m:.1,
      fluid_midpoint:{torque_nm:.1,thrust_n:1,power_w:2},energy_j:{defect_j:0}}}))};
assert.equal(admitGeometryPodResult(result),result);
assert.deepEqual(admitGeometryPodStudy({contract:'spike/geometry-propulsion-ui-study/v1',request:{a:1,b:2},result}).request,result.request);
for(const mutate of [
  x=>x.contract='spike/geometry-propulsion-loop-result/v2',x=>x.status='running',
  x=>x.field_table_sha256='missing',x=>x.physical_load_qualified=true,
  x=>x.accepted_steps=2,x=>x.controller_ticks=2,x=>x.history[1].time_s=0,
  x=>x.history[1].preceding_interval.end_time_s=.002,x=>x.history[0].preceding_interval={},
  x=>x.history[1].currents_a=[1,1,1],x=>x.history[1].temperature_k[0]=-1,
  x=>x.history[1].duty[0]=1.1,x=>x.history[1].speed_rad_s=Infinity,
]){const bad=structuredClone(result);mutate(bad);assert.throws(()=>admitGeometryPodResult(bad));}
assert.throws(()=>admitGeometryPodStudy({contract:'spike/geometry-propulsion-ui-study/v1',request:{a:2},result}));
const cycle=structuredClone(result);cycle.request.self=cycle;assert.throws(()=>admitGeometryPodResult(cycle));
const setup={contract:'spike/geometry-propulsion-ui-study/v1',request:{a:1},result:null};
assert.deepEqual(admitGeometryPodStudy(setup),setup,'save without results preserves the setup');
const inputs={magnetic_table:{contract:'fixture'},cfd_table:{contract:'fixture'},field_table_sha256:'a'.repeat(64),fluid_port_sha256:'b'.repeat(64)};
assert.deepEqual(admitGeometryPodStudy({...setup,inputs}).inputs,inputs);
assert.throws(()=>admitGeometryPodStudy({...setup,request:result.request,result,inputs:{...inputs,field_table_sha256:'f'.repeat(64)}}));
const spatial=structuredClone(result),mesh={nodes_m:[[0,0],[1,0],[0,1]],triangles:[[0,1,2]],
  element_b_t:[[.1,.2]],source_element_ids:[7],presentation_only:true,source_field_order:2,source_field_sha256:'e'.repeat(64)};
spatial.field_snapshot_derivation=Object.fromEntries(['input_result_file_sha256','domain_file_sha256','magnetic_table_file_sha256','source_sha256','geometry_sha256'].map(k=>[k,'f'.repeat(64)]));
spatial.field_snapshots=[{history_index:0,snapshot:{angle_rad:0,currents_a:[1,-1,0],world_frame:true,
  physical_qualified:false,source_sha256:'f'.repeat(64),geometry_sha256:'f'.repeat(64),
  domains:{rotor:structuredClone(mesh),stator:structuredClone(mesh)}}}];
admitGeometryPodResult(spatial);
for(const mutate of [x=>x.field_snapshots[0].snapshot.angle_rad=.1,
  x=>x.field_snapshots[0].snapshot.currents_a=[0,0,0],x=>x.field_snapshots[0].snapshot.domains.rotor.triangles[0][2]=3,
  x=>x.field_snapshots[0].snapshot.physical_qualified=true,
  x=>x.field_snapshots[0].snapshot.domains.extra={}]){
  const bad=structuredClone(spatial);mutate(bad);assert.throws(()=>admitGeometryPodResult(bad));
}
const roundoff=structuredClone(result);roundoff.accepted_steps=20;roundoff.controller_ticks=1;
roundoff.history=Array.from({length:21},(_,i)=>({...structuredClone(result.history[i===0?0:1]),time_s:i*.001,
  preceding_interval:i===0?null:{...structuredClone(result.history[1].preceding_interval),start_time_s:(i-1)*.001,end_time_s:(i-1)*.001+.001}}));
admitGeometryPodResult(roundoff);
console.log('Geometry pod capture admission: valid, malformed, future, setup-only and mismatched capture checks passed.');
