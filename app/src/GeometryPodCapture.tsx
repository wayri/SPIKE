// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from "react";
import {admitGeometryPodStudy,type GeometryPodStudy,type GeometryPodResult} from "./geometryPodStudy";
import {numericExtent} from "./numericRange";
import GeometryPodFields from "./GeometryPodFields";
import {runLocalWorker} from "./workerBridge";
import "./buttonStandard.css";
import "./PropulsionPodWorkbench.css";
function Trace({title,rows}:{title:string;rows:number[][]}) {
  const values=rows.flatMap(row=>row.slice(1)),{minimum:lo,maximum:hi}=numericExtent(values),span=hi-lo||1;
  const end=rows[rows.length-1][0];
  return <section className="pod-trace"><h4>{title}</h4><svg viewBox="0 0 400 140" role="img" aria-label={title}>
    {rows[0].slice(1).map((_,j)=><polyline key={j} className={`pod-line pod-line--${j%6}`} fill="none" strokeWidth="1.5" points={rows.map(row=>`${10+380*row[0]/end},${125-110*(row[j+1]-lo)/span}`).join(" ")}/>)}
    <text x="10" y="12">{hi.toPrecision(4)}</text><text x="10" y="138">{lo.toPrecision(4)} / 0-{end.toPrecision(3)} s</text>
  </svg></section>;
}
export default function GeometryPodCapture({study,onClose,workerAvailable=false,onStudy,onStatus}:{study:GeometryPodStudy;onClose?:()=>void;workerAvailable?:boolean;onStudy?:(study:GeometryPodStudy)=>void;onStatus?:(message:string)=>void}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState("");const alive=useRef(true),currentStudy=useRef(study);currentStudy.current=study;
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const run=async()=>{if(!workerAvailable||!study.inputs||!onStudy||busy)return;setBusy(true);setError("");
    const submitted=structuredClone(study),inputs=submitted.inputs!;
    onStatus?.("Running compiled controller with retained magnetic/CFD ports and thermal feedback...");
    try{const response=await runLocalWorker({method:"run_propulsion_pod_geometry",params:{request:submitted.request,
      magnetic_table:inputs.magnetic_table,cfd_table:inputs.cfd_table,expected_field_sha256:inputs.field_table_sha256,expected_fluid_sha256:inputs.fluid_port_sha256}});
      if(!response.ok)throw new Error(response.error||"Geometry loop failed.");
      const next=admitGeometryPodStudy({...submitted,request:response.result?.request,result:response.result,captured_at:new Date().toISOString()});
      if(alive.current&&currentStudy.current===study){onStudy(next);onStatus?.("Geometry-port loop completed; spatial reconstruction and physical qualification remain separate.");}
      else if(alive.current)setError("The retained setup changed while the worker ran; the earlier run was not attached to the changed study.");
    }catch(e){if(alive.current){setError(e instanceof Error?e.message:String(e));onStatus?.("Geometry-port loop failed; previous capture retained.");}}
    finally{if(alive.current)setBusy(false);}};
  return <><div className="pod-actions" aria-busy={busy}><button type="button" className="spike-control--primary" disabled={busy||!workerAvailable||!study.inputs||!onStudy} onClick={()=>void run()}>{busy?"Running geometry loop...":"Run coupled geometry loop"}</button><span role="status">{busy?"Worker running; previous capture remains available.":!workerAvailable?"Local worker unavailable; saved replay remains available.":!study.inputs?"Retained constitutive inputs are required for rerun.":"Rerun uses fixed compiled C and retained quasi-steady ports; no new CFD solve."}</span></div>{error&&<p role="alert">{error}</p>}
    {study.notices?.length?<details open><summary>Source assumptions and reference comparison</summary><ul>{study.notices.map((notice,i)=><li key={i}>{notice}</li>)}</ul></details>:null}
    {study.result?<GeometryPodResultCapture result={study.result} onClose={onClose}/>:<section className="pod-workbench" aria-label="Geometry propulsion setup"><h2>Geometry propulsion setup</h2><p>No captured result. Explicit retained setup and source tables can be run through the worker.</p><pre>{JSON.stringify(study.request,null,2)}</pre>{onClose&&<button type="button" onClick={onClose}>Close</button>}</section>}</>;
}
function GeometryPodResultCapture({result,onClose}:{result:GeometryPodResult;onClose?:()=>void}) {
  const [index,setIndex]=useState(0),[playing,setPlaying]=useState(false);
  useEffect(()=>{setIndex(0);setPlaying(false);},[result]);
  useEffect(()=>{if(!playing)return;const timer=window.setInterval(()=>setIndex(i=>result.field_snapshots?.length?(result.field_snapshots.find(f=>f.history_index>i)?.history_index??result.field_snapshots[0].history_index):(i+1)%result.history.length),1000/12);return()=>window.clearInterval(timer);},[playing,result]);
  const sample=result.history[Math.min(index,result.history.length-1)],interval=sample.preceding_interval;
  // Downsample only plot vertices; the scrubber and saved result retain every accepted state.
  const stride=Math.max(1,Math.ceil(result.history.length/1000));
  const history=result.history.filter((_,i)=>i%stride===0||i===result.history.length-1);
  return <section className="pod-workbench" aria-label="Saved geometry propulsion loop">
    <header><h2>Propulsion / geometry loop capture</h2><span>Experimental saved result</span>{onClose&&<button type="button" onClick={onClose}>Close</button>}</header>
    <p className="pod-scope">{result.scope} Numerical convergence receipts and material qualifications remain separate. Replay displays accepted stored states at 12 frames/s.</p>
    <div className="pod-actions"><button type="button" onClick={()=>setPlaying(p=>!p)}>{playing?"Pause saved states":"Replay saved states"}</button><label>Accepted state / {sample.time_s.toPrecision(6)} s<input aria-label="Accepted geometry loop state" type="range" min={0} max={result.history.length-1} value={index} onChange={e=>{setPlaying(false);setIndex(Number(e.target.value));}}/></label></div>
    <div className="pod-columns"><section className="pod-panel"><h3>Endpoint state</h3><dl>
      <dt>Phase currents A / B / C (A)</dt><dd>{sample.currents_a.map(v=>v.toPrecision(6)).join(" / ")}</dd>
      <dt>Shaft speed (rad/s)</dt><dd>{sample.speed_rad_s.toPrecision(7)}</dd><dt>Mechanical angle (rad)</dt><dd>{sample.angle_rad.toPrecision(7)}</dd>
      <dt>Endpoint field torque (N m)</dt><dd>{sample.field_torque_n_m.toPrecision(7)}</dd>
      <dt>Thermal network nodes 0-10 (K)</dt><dd>{sample.temperature_k.map(t=>t.toPrecision(7)).join(" / ")}</dd>
    </dl><GeometryPodFields result={result} index={index} onSelect={i=>{setPlaying(false);setIndex(i);}}/><h3>Preceding accepted interval</h3>{interval?<dl><dt>Time interval (s)</dt><dd>{interval.start_time_s.toPrecision(6)} - {interval.end_time_s.toPrecision(6)}</dd>
      <dt>Energy-conserving mean field torque (N m)</dt><dd>{interval.field_torque_dg_n_m.toPrecision(7)}</dd>
      <dt>Midpoint CFD table torque / thrust / power (N m / N / W)</dt><dd>{[interval.fluid_midpoint.torque_nm,interval.fluid_midpoint.thrust_n,interval.fluid_midpoint.power_w].map(v=>v.toPrecision(7)).join(" / ")}</dd>
      <dt>Interval energy defect (J)</dt><dd>{interval.energy_j.defect_j.toExponential(4)}</dd></dl>:<p>Initial state: no preceding interval.</p>}</section>
    <section className="pod-panel pod-traces"><Trace title="Phase currents A / B / C (A)" rows={history.map(s=>[s.time_s,...s.currents_a])}/><Trace title="Shaft speed (rad/s)" rows={history.map(s=>[s.time_s,s.speed_rad_s])}/><Trace title="Thermal network nodes 0-10 (K)" rows={history.map(s=>[s.time_s,...s.temperature_k])}/></section>
    <section className="pod-panel"><h3>Retained evidence</h3><dl><dt>Accepted steps / controller ticks</dt><dd>{result.accepted_steps} / {result.controller_ticks}</dd><dt>Whole-loop energy defect (J)</dt><dd>{result.energy.defect_j.toExponential(4)}</dd></dl>
      <details><summary>Source identities</summary><pre>{JSON.stringify({field_table_sha256:result.field_table_sha256,fluid_port_sha256:result.fluid_port_sha256,controller_executable_sha256:result.controller_executable_sha256,orchestrator_sha256:result.orchestrator_sha256},null,2)}</pre></details>
      <details><summary>Exact solved setup</summary><pre>{JSON.stringify(result.request,null,2)}</pre></details>
      <p>Saved histories contain thermal network temperatures. Spatial magnetic snapshots and resolved heat-transfer fields require their own retained datasets.</p>
    </section></div>
  </section>;
}
