// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { runLocalWorker } from "./workerBridge";
import { admitPropulsionPodResult, parsePropulsionPodRequest, type PropulsionPodStudy, type SyntheticPropulsionPodStudy, type PropulsionPodResult } from "./propulsionPodStudy";
import GeometryPodCapture from "./GeometryPodCapture";
import "./buttonStandard.css";
import "./PropulsionPodWorkbench.css";
export type PropulsionPodWorkbenchProps = { workerAvailable?: boolean; onStatus?: (message: string) => void; study: PropulsionPodStudy | null; onClose?: () => void; onStudy?: (study: PropulsionPodStudy) => void };
const errorText=(x: unknown) => x instanceof Error ? x.message : String(x);
function Trace({ title, times, series, labels }: { title: string; times: number[]; series: number[][]; labels: string[] }) {
  const values=series.flat(),lo=values.reduce((a,b)=>Math.min(a,b),Infinity),hi=values.reduce((a,b)=>Math.max(a,b),-Infinity),span=hi-lo || 1,last=times[times.length-1] || 1;
  return <section className="pod-trace"><h4>{title}</h4><svg viewBox="0 0 400 140" role="img" aria-label={title}>{series.map((data,k) => <polyline key={k} className={`pod-line pod-line--${k%6}`} fill="none" strokeWidth="1.5" strokeDasharray={k>=6?"5 3":undefined} points={data.map((v,j) => `${10+380*times[j]/last},${125-110*(v-lo)/span}`).join(" ")} />)}<text x="10" y="12">{hi.toPrecision(4)}</text><text x="10" y="138">{lo.toPrecision(4)}  /  0-{last.toPrecision(3)} s</text></svg><div className="pod-legend">{labels.map((label,k)=><span key={label} className={`pod-line--${k%6}`}>{label}</span>)}</div></section>;
}
export default function PropulsionPodWorkbench(props:PropulsionPodWorkbenchProps) {
  if(props.study?.contract==="spike/geometry-propulsion-ui-study/v1")return <GeometryPodCapture study={props.study} onClose={props.onClose} workerAvailable={props.workerAvailable} onStudy={props.onStudy} onStatus={props.onStatus}/>;
  return <SyntheticPropulsionPodWorkbench {...props} study={props.study}/>;
}
function SyntheticPropulsionPodWorkbench({workerAvailable=true,onStatus,study,onStudy,onClose}:Omit<PropulsionPodWorkbenchProps,"study">&{study:SyntheticPropulsionPodStudy|null}) {
  const [text,setText]=useState(study ? JSON.stringify(study.request,null,2) : "");
  const [result,setResult]=useState<PropulsionPodResult|null>(()=>{try{return study?.result ? admitPropulsionPodResult(study.result):null;}catch{return null;}});
  const [captured,setCaptured]=useState(study ? JSON.stringify(study.request):"");
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[frame,setFrame]=useState(0);
  const [playing,setPlaying]=useState(false),[replayFps,setReplayFps]=useState(6);
  useEffect(()=>{if(!playing||!result||result.frames.length<2)return;const timer=window.setInterval(()=>setFrame(value=>(value+1)%result.frames.length),1000/replayFps);return()=>window.clearInterval(timer);},[playing,replayFps,result]);
  const alive=useRef(true),sequence=useRef(0);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;sequence.current++;};},[]);
  useEffect(()=>{if(study){setText(JSON.stringify(study.request,null,2));setCaptured(JSON.stringify(study.request));setResult(study.result);setFrame(0);}},[study]);
  const loadDefaults=async()=>{setBusy(true);setError("");const token=++sequence.current;try{
    const response=await runLocalWorker({method:"propulsion_pod_three_phase_capabilities",params:{}});
    if(!response.ok)throw new Error(response.error || "Capabilities unavailable.");
    const setup=response.result?.default_request;
    if(!setup)throw new Error("Worker returned no default request.");
    const next=JSON.stringify(setup,null,2);parsePropulsionPodRequest(next);
    if(alive.current&&token===sequence.current)setText(next);
  }catch(e){if(alive.current)setError(errorText(e));}finally{if(alive.current&&token===sequence.current)setBusy(false);}};
  useEffect(()=>{if(!study&&workerAvailable)void loadDefaults();},[]);
  let request:Record<string,unknown>|null=null,parseError="";
  try{request=parsePropulsionPodRequest(text);}catch(e){parseError=errorText(e);}
  const stale=Boolean(result&&(!request||JSON.stringify(request)!==captured));
  const run=async()=>{if(!request||busy||!workerAvailable)return;const submitted=JSON.parse(JSON.stringify(request)) as Record<string,unknown>;const token=++sequence.current;setPlaying(false);setBusy(true);setError("");onStatus?.("Running compiled controller, three-phase field and thermal loop...");
    try{const response=await runLocalWorker({method:"run_propulsion_pod_three_phase",params:{request:submitted}});
      if(!response.ok)throw new Error(response.error||"Propulsion run failed.");
      const admitted=admitPropulsionPodResult(response.result);
      if(alive.current&&token===sequence.current){setResult(admitted);setCaptured(JSON.stringify(submitted));setFrame(0);onStudy?.({contract:"spike/propulsion-pod-ui-study/v1",request:submitted,result:admitted,captured_at:new Date().toISOString()});onStatus?.("Three-phase electrothermal benchmark completed.");}
    }catch(e){if(alive.current&&token===sequence.current){setError(errorText(e));onStatus?.("Propulsion run failed.");}}finally{if(alive.current&&token===sequence.current)setBusy(false);}};
  const field=useMemo(()=>{if(!result)return null;const f=result.frames[Math.min(frame,result.frames.length-1)],nodes=result.field_mesh.nodes_m;const xs=nodes.map(n=>n[0]),ys=nodes.map(n=>n[1]);const minX=xs.reduce((a,b)=>Math.min(a,b),Infinity),minY=ys.reduce((a,b)=>Math.min(a,b),Infinity),width=xs.reduce((a,b)=>Math.max(a,b),-Infinity)-minX,height=ys.reduce((a,b)=>Math.max(a,b),-Infinity)-minY;const magnitudes=f.element_b_t.map(b=>Math.hypot(b[0],b[1])),maximum=magnitudes.reduce((a,b)=>Math.max(a,b),0)||1;return {f,nodes,minX,minY,width,height,magnitudes,maximum};},[result,frame]);
  const history=result?.history||[],times=history.map(s=>s.time_s);
  return <section className="pod-workbench" aria-label="Three-phase propulsion benchmark" aria-busy={busy}>
    <header><h2>Propulsion  /  three-phase electrothermal benchmark</h2><span>Experimental</span>{onClose&&<button type="button" onClick={onClose}>Close</button>}</header>
    <p className="pod-scope">Synthetic planar PM motor  /  actual compiled C controller  /  averaged bridge  /  11 thermal nodes  /  hover BEM. No real motor calibration, VESC firmware qualification, blade-resolved operating-speed CFD or automatic source-board binding.</p>
    <div className="pod-actions"><button type="button" disabled={busy||!workerAvailable} onClick={()=>void loadDefaults()}>Load worker defaults</button><button type="button" className="spike-control--primary" disabled={busy||!request||!workerAvailable} onClick={()=>void run()}>{busy?"Running...":"Run coupled simulation"}</button><button type="button" disabled={busy||!request} onClick={()=>{if(request){onStudy?.({contract:"spike/propulsion-pod-ui-study/v1",request,result:stale?null:result});onStatus?.("Propulsion setup retained; save the project to write it to disk.");}}}>Keep setup in project</button><span role="status">{!workerAvailable?"Local worker unavailable.":busy?"Worker running; controls resume on completion.":stale?"Setup changed; displayed result belongs to captured setup.":result?"Completed worker result.":"Load or edit setup, then run."}</span></div>
    {error&&<p role="alert">{error}</p>}
    <div className="pod-columns"><section className="pod-panel"><h3>Setup JSON</h3><label htmlFor="pod-setup">Explicit simulation inputs</label><textarea id="pod-setup" value={text} disabled={busy} onChange={e=>setText(e.target.value)} spellCheck={false}/>{parseError&&text&&<p role="status">{parseError}</p>}<small>Worker validates all physics bounds before compiling. Current limit bounds the controller request; it is not a hard protection clamp.</small></section>
    <section className="pod-panel"><h3>Returned magnetic field</h3>{field&&result?<><div className="pod-actions"><button type="button" disabled={busy||result.frames.length<2} onClick={()=>setPlaying(value=>!value)}>{playing?"Pause saved frames":"Replay saved frames"}</button><label>Replay frames/s<select value={replayFps} onChange={event=>setReplayFps(Number(event.target.value))}><option value={2}>2</option><option value={6}>6</option><option value={12}>12</option></select></label></div><small>Replay displays computed snapshots; the timestamp is simulation time.</small><label>Field frame  /  {field.f.time_s.toFixed(5)} s<input aria-label="Returned field frame" type="range" min={0} max={result.frames.length-1} value={frame} onChange={e=>{setPlaying(false);setFrame(Number(e.target.value));}}/></label><svg className="pod-field" viewBox={`${field.minX} ${field.minY} ${field.width} ${field.height}`} role="img" aria-label="Actual FEM triangle magnetic flux density magnitude">{result.field_mesh.triangles.map((tri,k)=><polygon key={k} points={tri.map(i=>field.nodes[i].join(",")).join(" ")} fill={`hsl(${240-240*field.magnitudes[k]/field.maximum} 75% 48%)`} />)}</svg><small>|B| 0-{field.maximum.toPrecision(4)} T  /  actual returned P1 elements</small><dl><dt>Global energy defect</dt><dd>{Number(result.energy.defect_j).toExponential(3)} J</dd><dt>Fluid provider</dt><dd>{String(result.provenance.fluid_provider_kind)}</dd></dl><details open><summary>Temperatures at this saved frame</summary><dl>{result.thermal_node_names.map((name,index)=><div key={name}><dt>{name}</dt><dd>{(field.f.temperature_k[index]-273.15).toFixed(5)} C</dd></div>)}</dl></details><details><summary>Run limits and provenance</summary><ul>{result.limitations.map(x=><li key={x}>{x}</li>)}</ul><pre>{JSON.stringify(result.provenance,null,2)}</pre></details></>:<p>No completed field data yet.</p>}</section>
    <section className="pod-panel pod-traces"><h3>Returned histories</h3>{result?<><Trace title="Phase currents (A)" times={times} series={[0,1,2].map(j=>history.map(s=>s.currents_a[j]))} labels={["A","B","C"]}/><Trace title="Shaft speed (rad/s)" times={times} series={[history.map(s=>s.speed_rad_s)]} labels={["Speed"]}/><Trace title="Node temperatures (K)" times={times} series={result.thermal_node_names.map((_,j)=>history.map(s=>s.temperature_k[j]))} labels={result.thermal_node_names}/></>:<p>Currents, shaft speed and eleven node temperatures appear after an accepted run.</p>}</section></div>
  </section>;
}
