// SPDX-License-Identifier: Apache-2.0
import {useEffect,useRef,useState} from "react";
import {Box,Eye,EyeOff,Blend,Focus,X,Settings2} from "./icons";
import type {AssemblyIr,AssemblyPart,AssemblyPartVisual,AssemblySection} from "./mcadAssembly";
import {mechanicalOrigin,mechanicalVisual,type MechanicalVisuals} from "./mechanicalObjectsModel";
import {optionMatchesQuery} from "./optionSearch";
import MechanicalSectionControls from "./MechanicalSectionControls";
import {MechanicalMeasurementControls} from "./MechanicalMeasurementControls";
import type {MechanicalMeasurementPoints} from "./mechanicalMeasurement";
import "./buttonStandard.css";
import "./MechanicalObjectControls.css";
type Props={onMeasurement?:(points:MechanicalMeasurementPoints|null)=>void;assembly:AssemblyIr;visuals:MechanicalVisuals;selectedId:string|null;isolatedId:string|null;section:AssemblySection;viewMode:"2D"|"3D";on3D:()=>void;onBeginVisual?:()=>void;onVisual:(id:string,visual:AssemblyPartVisual,record?:boolean)=>void;onAll:(mode:"show"|"hide"|"translucent"|"reset")=>void;onSelect:(part:AssemblyPart)=>void;onIsolate:(id:string|null)=>void;onSection:(section:AssemblySection)=>void;onManage:(id?:string)=>void};
export default function MechanicalObjectControls(props:Props){
 const [open,setOpen]=useState(false),[pinned,setPinned]=useState(false),[query,setQuery]=useState("");
 const [tab,setTab]=useState("objects");
 const root=useRef<HTMLElement>(null),trigger=useRef<HTMLButtonElement>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const cancel=()=>{if(timer.current!==null)clearTimeout(timer.current);timer.current=null;};
 const close=()=>{cancel();setOpen(false);setPinned(false);};
 useEffect(()=>()=>cancel(),[]);
 useEffect(()=>{close();setQuery("");},[props.assembly.assembly_id]);
 useEffect(()=>{if(!open)return;const outside=(e:PointerEvent)=>{if(!root.current?.contains(e.target as Node))close();};const key=(e:KeyboardEvent)=>{if(e.key==="Escape"){close();trigger.current?.focus();}};document.addEventListener("pointerdown",outside);document.addEventListener("keydown",key);return()=>{document.removeEventListener("pointerdown",outside);document.removeEventListener("keydown",key);};},[open]);
 const selected=props.assembly.parts.find(part=>part.id===props.selectedId);
 const rows=props.assembly.parts.filter(part=>optionMatchesQuery(`${part.name} ${part.id} ${part.part_type}`,query));
 return <aside ref={root} className="mechanical-object-controls" data-open={open||undefined} aria-label="Mechanical objects" onPointerDown={event=>event.stopPropagation()} onWheel={event=>event.stopPropagation()} onMouseEnter={()=>{cancel();setOpen(true);}} onMouseLeave={()=>{cancel();if(!pinned)timer.current=setTimeout(()=>setOpen(false),120);}}>
 <button ref={trigger} type="button" className="spike-control--icon mechanical-object-pull" title="Mechanical objects, sections and dimensions" aria-label="Mechanical objects, sections and dimensions" aria-expanded={open} onClick={()=>{cancel();if(pinned)close();else{setPinned(true);setOpen(true);}}}><Box size={16}/></button>
 <div className="mechanical-object-panel" hidden={!open} onPointerDown={()=>{cancel();setPinned(true);}}><header><strong>Mechanical objects</strong><button type="button" className="spike-control--icon" aria-label="Close mechanical controls" onClick={close}><X size={15}/></button></header>
 {props.viewMode==="2D"&&<button type="button" onClick={props.on3D}>View mechanical geometry in 3D</button>}
 <div className="mechanical-object-tabs" role="tablist" aria-label="Mechanical tools">{[["objects","Objects"],["section","Section"],["measure","Measure"]].map(([id,label])=><button key={id} type="button" role="tab" aria-selected={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>
 <div className="mechanical-object-page" hidden={tab!=="objects"}>
 <input type="search" aria-label="Find mechanical objects" placeholder="Find object · * or ?" value={query} onChange={e=>setQuery(e.target.value)}/>
 <div className="mechanical-object-actions"><button type="button" onClick={()=>props.onAll("show")}><Eye size={13}/>Show all</button><button type="button" onClick={()=>props.onAll("hide")}><EyeOff size={13}/>Hide all</button><button type="button" onClick={()=>props.onAll("translucent")}><Blend size={13}/>Translucent</button><button type="button" onClick={()=>props.onAll("reset")}>Reset display</button></div>
 <div className="mechanical-object-list">{rows.map(part=>{const visual=mechanicalVisual(part,props.visuals);return <section className="mechanical-object-row" key={part.id} data-selected={part.id===props.selectedId||undefined}>
 <button type="button" className="mechanical-object-name" aria-pressed={part.id===props.selectedId} title={`${part.name} · ${part.id}`} onClick={()=>props.onSelect(part)}><Box size={13}/><span>{part.name||part.id}</span></button>
 <button type="button" className="spike-control--icon" aria-label={`${visual.visible?"Hide":"Show"} ${part.name}`} aria-pressed={visual.visible} onClick={()=>props.onVisual(part.id,{...visual,visible:!visual.visible})}>{visual.visible?<Eye size={14}/>:<EyeOff size={14}/>}</button>
 <button type="button" className="spike-control--icon" aria-label={`Translucent ${part.name}`} aria-pressed={visual.opacity<1} onClick={()=>props.onVisual(part.id,{...visual,opacity:visual.opacity<1?1:.2})}><Blend size={14}/></button>
 <button type="button" className="spike-control--icon" aria-label={`Isolate ${part.name}`} aria-pressed={props.isolatedId===part.id} onClick={()=>props.onIsolate(props.isolatedId===part.id?null:part.id)}><Focus size={14}/></button>
 <label className="mechanical-object-opacity">Opacity<input type="range" min="0" max="1" step=".01" aria-label={`${part.name} object opacity`} value={visual.opacity} onPointerDown={()=>props.onBeginVisual?.()} onKeyDown={e=>{if(!e.repeat&&["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","Home","End","PageUp","PageDown"].includes(e.key))props.onBeginVisual?.();}} onChange={e=>props.onVisual(part.id,{...visual,opacity:Number(e.target.value)},false)}/><output>{Math.round(visual.opacity*100)}%</output></label>
 </section>;})}{!rows.length&&<p>No matching mechanical objects.</p>}</div>
 {props.isolatedId&&<button type="button" onClick={()=>props.onIsolate(null)}>Restore complete assembly</button>}
 </div><div className="mechanical-object-page" hidden={tab!=="section"}><MechanicalSectionControls expanded anchorPoint={selected?mechanicalOrigin(props.assembly,selected):undefined} section={props.section} onChange={props.onSection} onManage={()=>{close();props.onManage(selected?.id);}}/></div>
 <div className="mechanical-object-page" hidden={tab!=="measure"}><MechanicalMeasurementControls onMeasure={props.onMeasurement} selectedPoint={selected?mechanicalOrigin(props.assembly,selected):undefined} selectedLabel={selected?`${selected.name} occurrence origin`:undefined}/></div>
 <button type="button" onClick={()=>{close();props.onManage(selected?.id);}}><Settings2 size={14}/>Placement, hierarchy and materials</button>
 <small>Display changes keep source geometry and placement unchanged. STEP objects need a prepared visual model.</small>
 </div>
 </aside>;
}
