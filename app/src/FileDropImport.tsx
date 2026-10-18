// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { subscribeNativeImportDrops } from "./workerBridge";
import { Upload, FileBox, X } from "./icons";
import { browserDropItems, mergeDroppedImports, nativeDropItems, type DroppedImport } from "./dropImportModel";
import "./buttonStandard.css";
import "./fileDropImport.css";
const labels:Record<string,string>={"odb++":"ODB++ job",kicad:"KiCad board",mcad:"Mechanical model",normalized:"Design snapshot",project:"SPIKE project",results:"Saved results",ipc2581:"IPC-2581",harness:"Harness connections",unknown:"Inspect format"};
export default function FileDropImport({desktop,blocked,onReview,onError}:{desktop:boolean;blocked:boolean;onReview:(item:DroppedImport)=>Promise<void>;onError:(message:string)=>void}) {
  const [dragging,setDragging]=useState(false),[queue,setQueue]=useState<DroppedImport[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const queued=useRef(queue);queued.current=queue;
  const current=useRef({blocked,onReview,onError});current.current={blocked:blocked||busy,onReview,onError};
  const dismiss=useRef<HTMLButtonElement>(null),wasReviewing=useRef(false);
  useEffect(()=>{if(queue.length&&!blocked){wasReviewing.current=true;dismiss.current?.focus();}else if(wasReviewing.current&&!queue.length){wasReviewing.current=false;document.getElementById("focus-menu-toggle")?.focus();}},[queue.length,blocked]);
  useEffect(()=>{
    let alive=true,depth=0;const listeners:(()=>void)[]=[];
    const fail=(cause:unknown)=>{const message=cause instanceof Error?cause.message:String(cause);setError(message);current.current.onError(message);};
    const add=(items:DroppedImport[],rejected:string[]=[])=>{
      setDragging(false);
      if(current.current.blocked){fail("Close the active dialog or finish the running operation, then drop the files again.");return;}
      if(rejected.length)fail(rejected.join("\n"));else setError("");
      try{const merged=mergeDroppedImports(queued.current,items);queued.current=merged;setQueue(merged);}catch(cause){fail(cause);}
    };
    if(desktop){
      const bind=async()=>{
        const stop=await subscribeNativeImportDrops(payload=>{if(alive)try{const data=nativeDropItems(payload);add(data.items,data.rejected);}catch(cause){fail(cause);}},active=>{if(alive)setDragging(active);});
        if(alive)listeners.push(stop);else stop();
      };void bind().catch(cause=>{if(alive)fail(cause);});
    }
    const isFiles=(event:DragEvent)=>Array.from(event.dataTransfer?.types??[]).includes("Files");
    const enter=(event:DragEvent)=>{if(desktop||!isFiles(event))return;event.preventDefault();depth++;setDragging(true);};
    const over=(event:DragEvent)=>{if(desktop||!isFiles(event))return;event.preventDefault();if(event.dataTransfer)event.dataTransfer.dropEffect="copy";setDragging(true);};
    const leave=(event:DragEvent)=>{if(desktop||!isFiles(event))return;depth=Math.max(0,depth-1);if(!depth||!event.relatedTarget)setDragging(false);};
    const drop=(event:DragEvent)=>{if(desktop||!isFiles(event))return;event.preventDefault();depth=0;setDragging(false);try{add(browserDropItems(Array.from(event.dataTransfer?.files??[])));}catch(cause){fail(cause);}};
    document.addEventListener("dragenter",enter);document.addEventListener("dragover",over);document.addEventListener("dragleave",leave);document.addEventListener("drop",drop);
    return()=>{alive=false;listeners.forEach(unlisten=>unlisten());document.removeEventListener("dragenter",enter);document.removeEventListener("dragover",over);document.removeEventListener("dragleave",leave);document.removeEventListener("drop",drop);};
  },[desktop]);
  const review=async(item:DroppedImport)=>{if(item.reason||busy||blocked)return;setBusy(true);setError("");try{await current.current.onReview(item);setQueue(previous=>previous.filter(entry=>entry.id!==item.id));}catch(cause){const message=String(cause instanceof Error?cause.message:cause);setError(message);current.current.onError(message);}finally{setBusy(false);}};
  return <>
    {dragging&&<div className="file-drop-hint" role="status"><Upload size={24}/><strong>Drop to review import</strong><span>KiCad boards · ODB++ jobs and archives · STEP / GLB / glTF models</span></div>}
    {!!queue.length&&!blocked&&<div className="file-drop-shade" onKeyDown={event=>{event.stopPropagation();if(event.key==="Escape"&&!busy)setQueue([]);if(event.key==="Tab"){const controls=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));const first=controls[0],last=controls[controls.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}}}>
      <section className="file-drop-review" role="dialog" aria-modal="true" aria-labelledby="file-drop-title">
        <header><h2 id="file-drop-title"><Upload size={17}/>Dropped sources</h2><button ref={dismiss} type="button" className="spike-control--icon" aria-label="Close dropped files" title="Close import queue" disabled={busy} onClick={()=>setQueue([])}><X size={15}/></button></header>
        <p>Review each source before applying it. Boards open through import review; mechanical models open the assembly attachment tool.</p>
        {error&&<p role="alert">{error}</p>}
        <ul>{queue.map(item=><li key={item.id}><FileBox size={18}/><div><strong title={item.fileName}>{item.fileName}</strong><small>{item.reason??labels[item.kind]}</small></div><button type="button" className="spike-control--compact" disabled={busy||Boolean(item.reason)} aria-label={`Review ${item.fileName}`} onClick={()=>void review(item)}>Review</button><button type="button" className="spike-control--icon" disabled={busy} aria-label={`Remove ${item.fileName}`} onClick={()=>setQueue(previous=>previous.filter(entry=>entry.id!==item.id))}><X size={14}/></button></li>)}</ul>
        {busy&&<p role="status">Opening import review…</p>}
      </section>
    </div>}
  </>;
}
