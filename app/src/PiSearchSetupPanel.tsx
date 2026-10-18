// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { CircuitBoard, Plus, Trash2 } from "./icons";
import type { ParsedBoard } from "./boardParser";
import type { PiSetupIntentSuggestion } from "./piSearchIntent";
import { eligibleComponentSupplyPads, type PiComponentLoadSelection } from "./piPinLoads";
import { PiComponentLoadPanel } from "./PiComponentLoadPanel";
import { parseSpiceNumber } from "./transientWaveform";
import "./buttonStandard.css";
import "./PiSearchSetupPanel.css";

export type PiSearchSetupSelection = { netId:string; netName:string; sourcePadId:string; voltageV:number; sourceCapacityA?:number; sources?:{padId:string;voltageV:number;capacityA?:number}[]; loads:PiComponentLoadSelection[]; returnMode:"implicit"|"explicit"; run?:boolean };
export default function PiSearchSetupPanel({suggestion,board,staleReason,onApply,onClose,canRun=false}:{suggestion:PiSetupIntentSuggestion;board:ParsedBoard;staleReason:string;onApply:(selection:PiSearchSetupSelection)=>void;onClose:()=>void;canRun?:boolean}) {
 const draft=suggestion.draft;
 const [netId,setNetId]=useState(draft.netId ?? "");
 const [sourceRef,setSourceRef]=useState(draft.source?.ref ?? "");
 const [sourcePadId,setSourcePadId]=useState(draft.source?.padIds.length===1?draft.source.padIds[0]:"");
 const [voltage,setVoltage]=useState(draft.voltageV===undefined?"":String(draft.voltageV));
 const [capacity,setCapacity]=useState(draft.sourceCurrentA===undefined?"":String(draft.sourceCurrentA));
 const [unlimited,setUnlimited]=useState(false);
 const [extraSources,setExtraSources]=useState(()=>Array.from({length:Math.max(draft.sources?.length ?? 1,draft.sourceInputs?.length ?? 1)-1},(_,i)=>({ref:draft.sources?.[i+1]?.ref ?? "",padId:draft.sources?.[i+1]?.padIds.length===1?draft.sources[i+1].padIds[0]:"",voltage:"",capacity:"",unlimited:false})));
 const editExtraSource=(index:number,patch:Partial<typeof extraSources[number]>)=>setExtraSources(current=>current.map((row,i)=>i===index?{...row,...patch}:row));
 const extraPad=(row:typeof extraSources[number])=>{const pads=eligibleComponentSupplyPads(board,row.ref,netName);return pads.some(pad=>pad.id===row.padId)?row.padId:pads.length===1?pads[0].id:"";};
 const [returnMode,setReturnMode]=useState<""|"implicit"|"explicit">("");
 const [sinkRefs,setSinkRefs]=useState<string[]>(draft.sinkInputs?.length?draft.sinkInputs.map(input=>draft.sinks.find(row=>row.ref.toLowerCase()===input.toLowerCase())?.ref ?? ""):draft.sinks.length?draft.sinks.map(row=>row.ref):[""]);
 const [allocations,setAllocations]=useState<Record<number,PiComponentLoadSelection>>({});
 const [error,setError]=useState("");
 const [overrideSentenceTotal,setOverrideSentenceTotal]=useState(false);
 const netName=board.nets[netId] ?? "";
 const sourcePads=eligibleComponentSupplyPads(board,sourceRef,netName);
 const refs=board.components.map(part=>part.ref).filter((ref,i,all)=>all.indexOf(ref)===i).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
 const effectiveSourcePad=sourcePadId || (sourcePads.length===1?sourcePads[0].id:"");
 const total=Object.values(allocations).reduce((sum,row)=>sum+row.totalCurrentA,0);
 const totalMismatch=draft.sinkCurrentA!==undefined&&sinkRefs.length>1&&Object.keys(allocations).length===sinkRefs.length&&Math.abs(total-draft.sinkCurrentA)>1e-12*Math.max(1,draft.sinkCurrentA);
 const invalid=Boolean(totalMismatch&&!overrideSentenceTotal) || staleReason || extraSources.some(row=>!row.ref || !extraPad(row)) || !netName || !sourcePads.some(pad=>pad.id===effectiveSourcePad) || !returnMode || sinkRefs.some((ref,i)=>!ref || !allocations[i] || allocations[i].componentRef!==ref) || new Set(sinkRefs).size!==sinkRefs.length;
 const missing=[!netName&&"rail",!sourceRef&&"source component",!effectiveSourcePad&&"source pad",!voltage.trim()&&"Vsup",!unlimited&&!capacity.trim()&&"Isup capacity or unlimited source",!returnMode&&"return model",sinkRefs.some((_,i)=>!allocations[i])&&"Isink allocation for each sink",extraSources.some(row=>!row.voltage.trim()||(!row.unlimited&&!row.capacity.trim()))&&"Vsup/Isup for each additional source"].filter(Boolean);

 const changeContext=()=>{setAllocations({});setOverrideSentenceTotal(false);setError("");};
 const apply=(run=false)=>{ try {
  if(invalid) throw new Error(staleReason || "Choose the rail, source pad, return model and apply a load allocation for every sink.");
  const voltageV=parseSpiceNumber(voltage,"Vsup"), sourceCapacityA=unlimited?undefined:parseSpiceNumber(capacity,"Isup capacity");
  if(!voltage.trim() || !(voltageV>0) || !Number.isFinite(voltageV)) throw new Error("Enter positive Vsup in volts.");
  if(!unlimited && (!capacity.trim() || !(sourceCapacityA!>0) || !Number.isFinite(sourceCapacityA))) throw new Error("Enter positive Isup capacity or explicitly choose an unlimited ideal source.");
  const sources=[{padId:effectiveSourcePad,voltageV,capacityA:sourceCapacityA},...extraSources.map((row,index)=>{
   const v=parseSpiceNumber(row.voltage,`Source ${index+2} Vsup`),c=row.unlimited?undefined:parseSpiceNumber(row.capacity,`Source ${index+2} Isup`);
   if(!row.voltage.trim()||!Number.isFinite(v)||v<=0||(!row.unlimited&&(!row.capacity.trim()||!Number.isFinite(c)||c!<=0)))throw new Error(`Enter valid Vsup and Isup capacity for source ${index+2}.`);
   return {padId:extraPad(row),voltageV:v,capacityA:c};
  })];
  if(new Set(sources.map(row=>row.padId)).size!==sources.length)throw new Error("Each source needs a distinct pad.");
  const loads=sinkRefs.map((_,i)=>allocations[i]);
  onApply({netId,netName,sourcePadId:effectiveSourcePad,voltageV,sourceCapacityA,sources,loads,returnMode:returnMode as "implicit"|"explicit",run});
 }catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
 return <section className="pi-search-setup" aria-label="Review sentence PI setup"><header><h2><CircuitBoard size={16}/>PI setup from search</h2><button type="button" onClick={onClose}>Close</button></header>
 <p>Resolve the endpoints, supply and loads below. Choose setup review or run after filling the missing details. Every run uses the existing PI preflight.</p>
 {staleReason&&<p role="alert">{staleReason}</p>}
 {!!draft.ambiguities.length&&<details open><summary>Names needing review</summary>{draft.ambiguities.map((item,i)=><p key={i}>{item.field}: {item.input} — {item.candidates.length?item.candidates.map(candidate=>candidate.name).join(", "):"no matching object; choose below"}</p>)}</details>}
 <div className="pi-search-fields"><label>Rail / net<select aria-label="PI intent net" value={netId} onChange={event=>{setNetId(event.target.value);setSourcePadId("");changeContext();}}><option value="">Choose net</option>{Object.entries(board.nets).filter(([id,name])=>id!=="0"&&name).map(([id,name])=><option key={id} value={id}>{name} ({id})</option>)}</select></label>
 <label>Source component<select value={sourceRef} onChange={event=>{setSourceRef(event.target.value);setSourcePadId("");setError("");}}><option value="">Choose source</option>{refs.map(ref=><option key={ref}>{ref}</option>)}</select></label>
 <label>Source pad<select value={effectiveSourcePad} onChange={event=>setSourcePadId(event.target.value)}><option value="">Choose exact source pad</option>{sourcePads.map(pad=><option key={pad.id} value={pad.id}>{pad.ref}.{pad.name} · {pad.layer}</option>)}</select></label>
 <label>Vsup (V)<input aria-label="PI intent supply voltage" placeholder="e.g. 3.3" value={voltage} onChange={event=>setVoltage(event.target.value)}/></label>
 <label>Isup capacity (A)<input aria-label="PI intent source capacity" placeholder="e.g. 2 or 500m" disabled={unlimited} value={capacity} onChange={event=>setCapacity(event.target.value)}/></label>
 <label className="pi-search-check"><input type="checkbox" checked={unlimited} onChange={event=>setUnlimited(event.target.checked)}/>Unlimited ideal source</label>
 <label>Return model<select value={returnMode} onChange={event=>setReturnMode(event.target.value as typeof returnMode)}><option value="">Choose return treatment</option><option value="implicit">Ideal implicit return · forward copper only</option><option value="explicit">Set up explicit return copper next</option></select></label></div>
 {extraSources.map((row,index)=><section className="pi-search-sink" key={index}><div className="pi-search-sink-heading"><h3>Additional source {index+2}</h3><button type="button" aria-label={`Remove source ${index+2}`} onClick={()=>setExtraSources(current=>current.filter((_,i)=>i!==index))}><Trash2 size={14}/></button></div><div className="pi-search-fields"><label>Component<select value={row.ref} onChange={event=>editExtraSource(index,{ref:event.target.value,padId:""})}><option value="">Choose source</option>{refs.map(ref=><option key={ref}>{ref}</option>)}</select></label><label>Pad<select value={extraPad(row)} onChange={event=>editExtraSource(index,{padId:event.target.value})}><option value="">Choose source pad</option>{eligibleComponentSupplyPads(board,row.ref,netName).map(pad=><option key={pad.id} value={pad.id}>{pad.ref}.{pad.name}</option>)}</select></label><label>Vsup (V)<input value={row.voltage} onChange={event=>editExtraSource(index,{voltage:event.target.value})}/></label><label>Isup capacity (A)<input disabled={row.unlimited} value={row.capacity} onChange={event=>editExtraSource(index,{capacity:event.target.value})}/></label><label className="pi-search-check"><input type="checkbox" checked={row.unlimited} onChange={event=>editExtraSource(index,{unlimited:event.target.checked})}/>Unlimited ideal source</label></div></section>)}
 <button type="button" disabled={extraSources.length>=11} onClick={()=>setExtraSources(current=>[...current,{ref:"",padId:"",voltage:"",capacity:"",unlimited:false}])}><Plus size={14}/>Add supply source</button>
 {!!missing.length&&<p role="status">Missing: {missing.join(", ")}.</p>}
 <p className="pi-search-note">Isup is the source current capacity, not a forced operating current. The solver determines source demand from the loads. A capacitor endpoint identifies the supply location; it does not create a DC supply model.</p>
 <h3>Sink components and input-pin sharing</h3>
 {draft.sinkCurrentA!==undefined&&draft.sinks.length>1&&<p>Requested total Isink: {draft.sinkCurrentA} A. Assign each component explicitly below; allocated total: {total} A.</p>}
 {sinkRefs.map((ref,index)=><section key={index} className="pi-search-sink"><div className="pi-search-sink-heading"><label>Sink {index+1}<select aria-label={`PI sink ${index+1} component`} value={ref} onChange={event=>{setSinkRefs(current=>current.map((value,i)=>i===index?event.target.value:value));setAllocations(current=>{const next={...current};delete next[index];return next;});}}><option value="">Choose sink</option>{refs.map(value=><option key={value}>{value}</option>)}</select></label><button type="button" aria-label={`Remove sink ${index+1}`} disabled={sinkRefs.length===1} onClick={()=>{setSinkRefs(current=>current.filter((_,i)=>i!==index));setAllocations({});}}><Trash2 size={14}/></button></div>
 {ref&&<PiComponentLoadPanel key={`${index}:${ref}:${netId}`} board={board} net={netName} initialRef={ref} fixedRef initialTotalCurrentA={sinkRefs.length===1?draft.sinkCurrentA:undefined} busy={Boolean(staleReason)} onDraftChange={()=>{setOverrideSentenceTotal(false);setAllocations(current=>{const next={...current};delete next[index];return next;});}} onApply={value=>setAllocations(current=>({...current,[index]:value}))}/>}
 {allocations[index]&&<p role="status">Applied {allocations[index].totalCurrentA} A across {allocations[index].pins.length} pads. Apply the allocation again after editing its draft.</p>}</section>)}
 {totalMismatch&&<label className="pi-search-check"><input type="checkbox" checked={overrideSentenceTotal} onChange={event=>setOverrideSentenceTotal(event.target.checked)}/>Use the edited per-component total ({total} A) instead of the sentence total ({draft.sinkCurrentA} A)</label>}
 <button type="button" disabled={sinkRefs.length>=12} onClick={()=>{setSinkRefs(current=>[...current,""]);setAllocations({});}}><Plus size={14}/>Add sink component</button>
 <details><summary>Interpretation and assumptions</summary>{draft.assumptions.map((item,i)=><p key={i}>{item}</p>)}<p>Only same-rail copper pads are candidates. Equal sharing is a prescribed input assumption; it is not inferred IC internal current flow. You can edit each resulting pad current in PI setup.</p></details>
 {error&&<p role="alert">{error}</p>}
 <footer><span>Applied sink current: {total.toPrecision(6)} A</span><button type="button" disabled={Boolean(invalid)} onClick={()=>apply()}>Review in PI setup</button><button type="button" disabled={Boolean(invalid)||!canRun||returnMode!=="implicit"} title={returnMode==="explicit"?"Configure explicit return terminals in PI setup before running":!canRun?"Desktop worker required":"Validate and run the reviewed setup"} onClick={()=>apply(true)}>Run PI</button></footer>
 </section>;
}
