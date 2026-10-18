// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { Activity, Box, CircuitBoard, ClipboardCheck, Eye, Focus, FolderOpen, GripVertical, Layers3, Magnet, MoreHorizontal, Network, Pause, Play, Search, SlidersHorizontal, Square, Target, Thermometer, Unplug, Upload, Waves, type LucideIcon } from "./icons";
import ViewportActionMenu, { type ContextMenuGroup } from "./ViewportActionMenu";
import { quickToolActions, quickToolPosition, runQuickTool, type QuickToolContext } from "./quickToolModel";
import "./buttonStandard.css";
import "./ViewportQuickTools.css";

const labels: Record<string,[string,LucideIcon]> = {
  fit:["Fit",Focus], "layer-manager":["Layers",Layers3], "inspect-object":["Inspect",Search], "isolate-net":["Isolate",Eye],
  "pi-DC IR Drop":["PI setup",Activity], "si-channel":["Channel",Waves], "si-eye":["Eye / mask",Eye], "si-crosstalk":["Crosstalk",Network], "si-ports":["Ports",Unplug],
  probe:["Probe",Target], "thermal-setup":["Thermal setup",Thermometer], "thermal-history":["Temperature",Activity], "thermal-contacts":["Contacts",Network],
  "em-net":["EM domain",Magnet], engines:["Engines",SlidersHorizontal], "model-resolver":["Models",Box], schematic:["Schematic",CircuitBoard],
  "result-plots":["Results",Activity], "trace-plots":["Traces",Waves], playback:["Playback",Play], report:["Report",ClipboardCheck],
  validate:["Check",ClipboardCheck], stackup:["Stackup",Layers3], "power-tree":["Power tree",Network], stop:["Stop",Square],
  "open-project":["Open",FolderOpen], "import-board":["Import",Upload],
};

export default function ViewportQuickTools({ groups, context, selectionLabel, summary, onError }: {groups:ContextMenuGroup[];context:QuickToolContext;selectionLabel:string;summary:string[];onError:(message:string)=>void}) {
  const [more,setMore]=useState<{x:number;y:number}|null>(null),[position,setPosition]=useState(()=>{try{const value=Number(localStorage.getItem("spike.quickTools.position")??.5);return Number.isFinite(value)?Math.min(1,Math.max(0,value)):.5;}catch{return .5;}});
  const root=useRef<HTMLDivElement>(null),bar=useRef<HTMLElement>(null),[travel,setTravel]=useState(0), current=useRef(groups), dragCleanup=useRef<(()=>void)|null>(null);current.current=groups;
  useEffect(()=>()=>dragCleanup.current?.(),[]);
  useEffect(()=>{const host=root.current,tools=bar.current;if(!host||!tools)return;const measure=()=>{const style=host.ownerDocument.defaultView?.getComputedStyle(host);setTravel(Math.max(0,host.clientWidth-tools.offsetWidth-Number.parseFloat(style?.paddingLeft??"0")-Number.parseFloat(style?.paddingRight??"0")));};measure();const observer=new ResizeObserver(measure);observer.observe(host);observer.observe(tools);return()=>observer.disconnect();},[]);
  const primary=quickToolActions(groups,context);
  const rememberPosition=(next:number)=>{setPosition(next);try{localStorage.setItem("spike.quickTools.position",String(next));}catch{/* Optional preference. */}};
  return <div ref={root} className="viewport-quick-tools-slot" style={{justifyContent:"flex-start"}}>
    <nav ref={bar} className="viewport-quick-tools" role="toolbar" aria-orientation="horizontal" style={{transform:`translateX(${Math.round(travel*position)}px)`}} aria-label="Context quick tools" onKeyDown={event=>{
      if(event.defaultPrevented || !["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;
      const entries=Array.from(bar.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')??[]),at=entries.indexOf(event.target as HTMLButtonElement);
      if(at<0)return;event.preventDefault();event.stopPropagation();
      entries[event.key==="Home"?0:event.key==="End"?entries.length-1:(at+(event.key==="ArrowLeft"?-1:1)+entries.length)%entries.length]?.focus();
    }}>
      <button type="button" className="spike-control--bare quick-tools-grip" title="Drag to position; left/right moves in steps, Home/End aligns to edges" aria-label="Position quick tools" onKeyDown={event=>{if(["ArrowLeft","ArrowRight","Home","End"].includes(event.key)){event.preventDefault();event.stopPropagation();rememberPosition(event.key==="Home"?0:event.key==="End"?1:quickToolPosition(position,event.key==="ArrowLeft"?-24:24,travel));}}} onPointerDown={event=>{
        if(event.button!==0)return;event.preventDefault();event.stopPropagation();dragCleanup.current?.();const grip=event.currentTarget;grip.setPointerCapture(event.pointerId);
        const start=event.clientX,initial=position,available=travel;
        const move=(pointer:PointerEvent)=>setPosition(quickToolPosition(initial,pointer.clientX-start,available));
        const stop=(pointer:PointerEvent)=>{rememberPosition(quickToolPosition(initial,pointer.clientX-start,available));dragCleanup.current?.();dragCleanup.current=null;if(grip.hasPointerCapture(pointer.pointerId))grip.releasePointerCapture(pointer.pointerId);};
        const cancel=()=>{dragCleanup.current?.();dragCleanup.current=null;};dragCleanup.current=()=>{grip.removeEventListener("pointermove",move);grip.removeEventListener("pointerup",stop);grip.removeEventListener("pointercancel",cancel);grip.removeEventListener("lostpointercapture",cancel);};grip.addEventListener("pointermove",move);grip.addEventListener("pointerup",stop);grip.addEventListener("pointercancel",cancel);grip.addEventListener("lostpointercapture",cancel);
      }}><GripVertical size={14}/></button>
      <span className="quick-tools-context" title={`${context.workspace}: ${selectionLabel}`}>{selectionLabel!==context.workspace&&<span className="quick-tools-workspace">{context.workspace}</span>}<strong>{selectionLabel}</strong></span>
      <div className="quick-tools-actions" role="group" aria-label="Suggested actions">
        {primary.map(action=>{const [label,Icon]=labels[action.id]??[action.label,SlidersHorizontal];return <button key={action.id} type="button" className={`spike-control--compact ${action.id==="stop"?"spike-control--danger":""}`} disabled={Boolean(action.disabledReason)} title={action.disabledReason??action.description??action.label} aria-label={action.label} onClick={()=>void runQuickTool(action.id,current.current,onError)}><Icon size={15}/><span>{action.id==="isolate-net" && action.label.startsWith("Exit")?"Show all":action.id==="playback" && action.label.startsWith("Pause")?<><Pause size={12}/> Pause</>:label}</span></button>;})}
      </div>
      <button type="button" className="spike-control--compact quick-tools-more" title="All tools for the current selection and workspace" aria-haspopup="menu" aria-expanded={Boolean(more)} onClick={event=>{const bounds=event.currentTarget.getBoundingClientRect();setMore(more?null:{x:bounds.right,y:bounds.bottom+6});}}><MoreHorizontal size={16}/><span>More</span></button>
    </nav>
    {more&&<ViewportActionMenu x={more.x} y={more.y} title={selectionLabel} summary={summary} groups={groups} onClose={()=>setMore(null)}/>}
  </div>;
}

