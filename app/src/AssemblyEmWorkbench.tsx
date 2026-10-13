// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from "react";
import {openNativeTextFile,runLocalWorker,runNativeProjectWorker,saveNativeTextFile} from "./workerBridge";
import {assertFieldAssembly} from "./assemblyFieldStudyPresentation";
import {assemblyEmStudy,type AssemblyEmStudy} from "./retainedAssemblyEm";
import InteractivePlot from "./InteractivePlot";
import "./EngineeringReview.css";
import "./buttonStandard.css";

export default function AssemblyEmWorkbench({study,projectPath,manifestDigest,onStudy,onActivate,onClose}:{
  study:AssemblyEmStudy|null;projectPath:string|null;manifestDigest:string|null;
  onStudy:(value:AssemblyEmStudy)=>void;onActivate:()=>void;onClose:()=>void;
}) {
  const largeRequestMarker="Large retained geometry: use the reproducible request builder or import a revised study. Inline editing is disabled.";
  const requestText=(value:AssemblyEmStudy|null)=>{const raw=value?JSON.stringify(value.request):"";return raw.length>2*1024*1024?largeRequestMarker:raw;};
  const [text,setText]=useState(()=>requestText(study));
  const [busy,setBusy]=useState(false),[error,setError]=useState(""),[prepared,setPrepared]=useState(false);
  const [physical,setPhysical]=useState<Record<string,any>|null>(null);
  const generation=useRef(0),dialog=useRef<HTMLDivElement>(null);
  useEffect(()=>{let active=true;generation.current++;setPhysical(null);setPrepared(false);
    if(projectPath&&manifestDigest)void runNativeProjectWorker({method:"read_assembly_field_study_in_project",params:{project_path:projectPath,expected_manifest_payload_sha256:manifestDigest}})
      .then(response=>{if(!active)return;if(!response.ok)throw new Error(response.error);setPhysical(response.result?.assembly as Record<string,any>);})
      .catch(cause=>{if(active)setError(String(cause));});
    return()=>{active=false;generation.current++;};
  },[projectPath,manifestDigest]);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();return()=>{if(previous?.isConnected)previous.focus();};},[]);
  const action=async(work:(ticket:number)=>Promise<void>)=>{const ticket=generation.current;setBusy(true);setError("");try{await work(ticket);}catch(cause){if(ticket===generation.current)setError(String(cause));}finally{if(ticket===generation.current)setBusy(false);}};
  const admit=async(value:unknown)=>{const candidate=assemblyEmStudy(value);assertFieldAssembly(candidate.request.geometry,physical);const response=await runLocalWorker({method:"admit_assembly_em_study",params:{record:candidate}});if(!response.ok)throw new Error(response.error);return assemblyEmStudy(response.result);};
  const lockedRequest=text===largeRequestMarker;
  const editedRequest=():Record<string,any>=>lockedRequest&&study?study.request:JSON.parse(text);
  const validate=()=>action(async ticket=>{const value=await admit({contract:"spike/assembly-em-study/v1",request:editedRequest(),result:null});if(ticket!==generation.current)return;onStudy(value);setPrepared(true);});
  const run=()=>action(async ticket=>{const value=await admit({contract:"spike/assembly-em-study/v1",request:editedRequest(),result:null});
    const response=await runLocalWorker({method:"run_assembly_em",params:{request:value.request}});if(!response.ok)throw new Error(response.error);if(ticket!==generation.current)return;
    const completed=await admit({...value,result:response.result});if(ticket===generation.current){onStudy(completed);setPrepared(true);}});
  const open=()=>action(async ticket=>{const file=await openNativeTextFile("result");if(!file)return;if(new TextEncoder().encode(file.contents).length>128*1024*1024)throw new Error("Study exceeds 128 MiB.");
    const value=await admit(JSON.parse(file.contents));if(ticket!==generation.current)return;onStudy(value);setText(requestText(value));setPrepared(true);});
  const current=study&&(lockedRequest||text===requestText(study)), result=current?study.result:null;
  const frequencies=(result?.frequency_hz??[]) as number[],columns=(result?.s_parameter_column??[]) as any[];
  return <div className="modal-shade engineering-shade"><div ref={dialog} className="engineering-review assembly-em-workbench" role="dialog" aria-modal="true" aria-labelledby="assembly-em-title" onKeyDown={event=>{
    if(event.key==="Escape"){event.preventDefault();onClose();}
    if(event.key==="Tab"){const nodes=[...dialog.current!.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled)')];const first=nodes[0],last=nodes[nodes.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}
  }}><header><h2 id="assembly-em-title">Retained assembly EM · OpenEMS</h2><button type="button" aria-label="Close assembly EM" onClick={onClose}>×</button></header>
  <div className="engineering-actions"><button type="button" disabled={busy||!physical} onClick={()=>void open()}>Open study / request</button><button type="button" disabled={busy||!physical||!text} onClick={()=>void validate()}>Validate geometry and ports</button><button type="button" disabled={busy||!physical||!prepared||!current} onClick={()=>void run()}>Run OpenEMS</button><button type="button" disabled={busy||!physical||!result?.field_capture?.preview} onClick={()=>void action(async()=>{await admit(study);onActivate();onClose();})}>Show saved fields in viewport</button><button type="button" disabled={busy||!study} onClick={()=>void saveNativeTextFile("assembly-em-study.json",JSON.stringify(study),"result")}>Export study</button></div>
  <div className="engineering-body">{!projectPath&&<p role="status">Save the assembly project first so input geometry can be checked against its physical occurrences.</p>}{busy&&<p role="status">Managed worker running; this may take several minutes.</p>}{error&&<p role="alert">{error}</p>}
  <p>Explicit copper, dielectric and connector volumes and conductor-face ports are required. Materials and source assumptions remain part of the study. Results are experimental and unvalidated for production.</p>
  <details open={!result}><summary>Physical setup and excitation request</summary><label>Assembly EM request JSON<textarea aria-label="Assembly EM request JSON" value={text} disabled={busy||lockedRequest} onChange={event=>{setText(event.target.value);setPrepared(false);}} style={{width:"100%",minHeight:180,fontFamily:"monospace"}}/></label></details>
  {result&&<>{result.material_sampling?.unused_conductive_primitive_count>0&&<p role="alert">Diagnostic result: the native grid did not sample {result.material_sampling.unused_conductive_primitive_count} conductive solids. Refine the mesh and verify copper connectivity before using this result for design decisions.</p>}<h3>Executed port response</h3><p>Frequency in GHz; magnitude is 20 log₁₀|S| in dB. This is the response column for excited port {String(result.excited_port_id)}, not a complete multiport matrix.</p>
    <InteractivePlot title="Assembly EM port response" revision={String(result.run_id)} data={columns.map(column=>({type:"scatter",mode:"lines",name:`${column.port_id} ← ${result.excited_port_id}`,x:frequencies.map(f=>f/1e9),y:column.real.map((r:number,i:number)=>{const a=Math.hypot(r,column.imag[i]);return a>0?20*Math.log10(a):null;})}))} layout={{xaxis:{title:"Frequency (GHz)"},yaxis:{title:"Power-wave magnitude (dB)"},height:330}}/>
    <p>Mesh cells: {String(result.mesh?.actual_grid?.cell_count)} · energy-decay status: {result.termination?.did_reach_end_criteria===false?"Requested decay was not reached":"Inspect native solver log; decay not certified"}.</p>
    <ul>{(result.limitations??[]).map((value:string,i:number)=><li key={i}>{value}</li>)}</ul>
    <p>Saved samples can be activated with one click. Geometry and material placement remain visible behind the volume overlay. Use the EM result manager for electric/magnetic fields, phasor components and linked probes.</p>
  </>}
  </div></div></div>;
}
