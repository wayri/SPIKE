// SPDX-License-Identifier: Apache-2.0
import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import BoardViewport, { type BoardObject, type ViewportContextRequest } from "../src/BoardViewport";
import { parseDesignSourceOffThread } from "../src/boardImport";
import type { ParsedBoard } from "../src/boardParser";
import ThermalHistoryPopup from "../src/ThermalHistoryPopup";
import { thermalProbeHistory, type ThermalProbeHistoryResult } from "../src/thermalProbeHistory";
import "../src/styles.css";
import "../src/buttonStandard.css";
const noop = () => {}, empty = {};
function Preview() {
 const [board,setBoard] = useState<ParsedBoard|null>(null), [error,setError] = useState("");
 const [selected,setSelected] = useState<BoardObject|null>(null),[context,setContext] = useState<ViewportContextRequest|null>(null);
 const [history,setHistory] = useState<ThermalProbeHistoryResult|null>(null),[camera,setCamera]=useState("fit:0");
 const [pointerInfo,setPointerInfo]=useState("");
 const [filter,setFilter]=useState<"all"|"part"|"net">("all");
 useEffect(()=>{let cancelled=false;void(async()=>{try{
  const response=await fetch("../.tmp/assembly-performance/source.json");if(!response.ok)throw new Error("Retained verification source unavailable");
  const parsed=await parseDesignSourceOffThread("retained.spike-design.json",await response.text(),"spike-normalized");
  if(!cancelled)setBoard({...parsed,boardModelUrl:new URL("../.tmp/assembly-performance/board.glb",location.href).href,
   componentModelUrl:new URL("../.tmp/assembly-performance/components.glb",location.href).href});
 }catch(error){setError(String(error));}})();return()=>{cancelled=true;};},[]);
 const layers=useMemo(()=>Object.fromEntries(board?.layers.map(layer=>[layer,true])??[]),[board]);
 const scenario=useMemo(()=>{if(!board)return null;const nx=8,ny=6,values=Array.from({length:nx*ny},(_,i)=>35+i*.5);
  return {board_thermal_result:{contract:"spike/board-thermal-result/v1",status:"completed",model_status:"synthetic interaction fixture",
   grid:{shape:[nx,ny],origin_mm:[board.bounds.minX,board.bounds.minY],spacing_mm:[board.width/nx,board.height/ny],order:"x-fast",temperatures_c:values},
   layer_grids:[{name:"F.Cu",thickness_mm:.035,temperatures_c:values},{name:"B.Cu",thickness_mm:.035,temperatures_c:values}],
   transient:[0,5,10].map(time_s=>({time_s,layer_temperatures_c:[values.map(v=>25+(v-25)*time_s/10),values.map(v=>25+(v-25)*time_s/10)]}))},
   component_result:{nodes:board.components.map(c=>({id:c.id,component_ref:c.ref})),transient:[0,5,10].map(time_s=>({time_s,temperatures_c:Object.fromEntries(board.components.map(c=>[c.id,25+time_s*3]))}))}};
 },[board]);
 return <main style={{height:"100vh",display:"flex",flexDirection:"column"}}>
  <header style={{padding:8,display:"flex",gap:10,flexWrap:"wrap"}}><b>Thermal selection verification</b>
   <button onClick={()=>setCamera("view-top:"+Date.now())}>Top view</button><button onClick={()=>setCamera("fit:"+Date.now())}>Fit board</button>
   <label>Selection filter<select value={filter} onChange={e=>setFilter(e.target.value as typeof filter)}><option value="all">All</option><option value="part">Parts</option><option value="net">Nets</option></select></label>
  </header><p style={{margin:8}}>Synthetic temperature histories on a retained real board: interaction evidence only, not a physical simulation. {error}</p>
  <output style={{margin:8}}>{pointerInfo} {selected?`Selected ${selected.type}: ${selected.name}`:"No selection"}</output>
  <div onPointerUp={e=>setPointerInfo(`Pointer ${e.clientX.toFixed(0)}, ${e.clientY.toFixed(0)}`)} className="board-canvas is-3d" style={{flex:1,minHeight:0,position:"relative"}}>{board&&<BoardViewport board={board} viewMode="3D"
   visibleLayers={layers} layerOpacity={empty} layerSeparation={0}
   showVias showModels showSmdModels showThtModels navigationMode="orbit" navigationInertia cameraCommand={camera}
   selectionFilter={filter} selectedId={selected?.id??null} onSelect={setSelected} onCamera={noop}
   thermalScenario={scenario} thermalVisibility={{volume:false,heatSources:false,airflow:false,hardware:false,field:true}} onContextMenu={setContext}/>}</div>
  {context&&<div role="menu" aria-label="Thermal verification context menu" style={{position:"fixed",left:context.clientX,top:context.clientY,zIndex:1000}}>
   <button role="menuitem" onClick={()=>{setHistory(thermalProbeHistory(scenario,context.thermalTarget??{}));setContext(null);}}>Plot temperature vs time</button>
   <button role="menuitem" onClick={()=>setContext(null)}>Dismiss</button></div>}
  {history&&<ThermalHistoryPopup history={history} onClose={()=>setHistory(null)}/>}
 </main>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
