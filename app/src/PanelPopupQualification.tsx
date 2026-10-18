import * as desktopBridge from "./workerBridge";
import { setPanelUiScale, countLinkedPanelWindows } from "./panelWindowBridge";
// SPDX-License-Identifier: Apache-2.0
/** Bounded native runtime diagnostic: no project import, worker request or solver dispatch. */
import { useEffect, useRef, useState } from "react";
import FloatingPanel, { FloatingPanelControls, useFloatingPanel } from "./FloatingPanel";
import { usePanelPresentation } from "./panelPresentation";
function Proof({phase,setPhase,mounts,baseline,fail}:{phase:string;setPhase:(value:string)=>void;mounts:{current:number};baseline:{current:number};fail:(message:string)=>void}) {
  const floating=useFloatingPanel(),presentation=usePanelPresentation();
  const [draft,setDraft]=useState("initial"),[clicks,setClicks]=useState(0);
  useEffect(()=>{mounts.current++;},[]);
  useEffect(()=>{
    const timer=window.setTimeout(async()=>{
      try {
        const doc=presentation.ownerDocument;
        if(!doc || !floating)throw new Error("Missing panel presentation");
        if(phase==="edit"){doc.querySelector<HTMLButtonElement>("#proof-edit")?.click();setPhase("edited");}
        else if(phase==="edited"){if(draft!=="retained draft")throw new Error("Draft edit missing");baseline.current=mounts.current;floating.detach();}
        else if(phase==="detached"){
          if(!floating.detached || doc===document)throw new Error("Native popup document was not linked");
          if(draft!=="retained draft" || mounts.current!==baseline.current)throw new Error("Detach remounted the editor or lost its draft");
          const heading=doc.querySelector<HTMLElement>(".focus-tool-heading"),frame=doc.querySelector<HTMLElement>(".floating-panel-frame");
          if(!heading || presentation.ownerWindow?.getComputedStyle(heading).display!=="flex")throw new Error("Detached styles did not load");
          if(!frame || frame.getBoundingClientRect().height<(presentation.ownerWindow?.innerHeight ?? 0)*.8)throw new Error("Detached content does not fill its window");
          doc.querySelector<HTMLButtonElement>("#proof-action")?.click();setPhase("clicked");
        } else if(phase==="clicked"){
          if(clicks!==1)throw new Error("Detached button did not call its original React handler");
          floating.dock();
        } else if(phase==="returned"){
          if(floating.detached || doc!==document || draft!=="retained draft" || mounts.current!==baseline.current)throw new Error("Redocking lost draft or mount identity");
          setPhase("detach-close");floating.detach();
        } else if(phase==="close-detached"){
          if(!floating.detached)throw new Error("Second native detachment failed");
          setPhase("closing");presentation.ownerWindow?.close();
        } else if(phase==="closed-returned"){
          if(floating.detached || doc!==document || draft!=="retained draft" || clicks!==1 || mounts.current!==baseline.current)throw new Error("Native close failed to return the same editor");
          if(await countLinkedPanelWindows()!==0)throw new Error("Closed native popup frames were not retired");
          document.title="SPIKE PANEL QUALIFICATION PASS - native portal, draft, action, redock, close and zero leftover frames";
        }
      } catch(error){fail(error instanceof Error?error.message:String(error));}
    },phase==="closed-returned"?500:200);
    return()=>window.clearTimeout(timer);
  },[phase,draft,clicks,presentation.ownerDocument,floating?.detached]);
  return <section className="focus-tool-deck"><header className="focus-tool-heading" onPointerDown={floating?.onHeaderPointerDown}><h2>Panel qualification</h2><FloatingPanelControls/></header><div className="focus-tool-content"><label>Draft<input id="proof-draft" value={draft} onChange={event=>setDraft(event.target.value)}/></label><button id="proof-edit" onClick={()=>setDraft("retained draft")}>Edit draft</button><button id="proof-action" onClick={()=>setClicks(value=>value+1)}>Retained callback {clicks}</button><p>{phase}</p></div></section>;
}
export default function PanelPopupQualification() {
  const [phase,setPhase]=useState("scale"),[error,setError]=useState("");
  const mounts=useRef(0),baseline=useRef(0),cycle=useRef(0),latest=useRef(phase);latest.current=phase;
  const fail=(message:string)=>{setError(message);document.title=`SPIKE PANEL QUALIFICATION FAIL - ${message}`;};
  useEffect(()=>{let disposed=false,unlisten:(()=>void)|undefined;void desktopBridge.subscribeDesktopCloseRequested(()=>undefined).then(listener=>{if(disposed)listener();else unlisten=listener;}).catch(error=>{if(!disposed)fail(`Close protocol: ${String(error)}`);});return()=>{disposed=true;unlisten?.();};},[]);
  useEffect(()=>{document.title="SPIKE PANEL QUALIFICATION RUNNING";void setPanelUiScale(1.25).then(()=>setPhase("edit")).catch(error=>fail(String(error)));const deadline=window.setTimeout(()=>{if(latest.current!=="pass")fail(`Timed out in ${latest.current}`);},20000);return()=>window.clearTimeout(deadline);},[]);
  useEffect(()=>{if(phase==="closed-returned")setTimeout(()=>setPhase("pass"),1000);},[phase]);
  return <div className="app-shell focus-shell" style={{height:"100vh"}}><p role="status">{error||phase}</p><FloatingPanel id="native-qualification" title="Native qualification" active={true} onDetached={()=>setPhase(++cycle.current===1?"detached":"close-detached")} onDocked={()=>setPhase(cycle.current===2?"closed-returned":"returned")} onError={fail}><Proof phase={phase} setPhase={setPhase} mounts={mounts} baseline={baseline} fail={fail}/></FloatingPanel></div>;
}
