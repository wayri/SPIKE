// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import ViewportLayerSelector from "../src/ViewportLayerSelector";
import LayoutViewport from "../src/LayoutViewport";
import { parseKicadBoard, type ParsedBoard } from "../src/boardParser";
import type { ZoneDisplayMode } from "../src/zoneDisplay";
import "../src/styles.css";
import "../src/WorkbenchChrome.css";
import "../src/FocusWorkspace.css";
import "../src/buttonStandard.css";
function Preview() {
  const [board,setBoard]=useState<ParsedBoard|null>(null),[error,setError]=useState("");
  const [visibility,setVisibility]=useState<Record<string,boolean>>({}),[opacity,setOpacity]=useState<Record<string,number>>({});
  const [mode,setMode]=useState<ZoneDisplayMode>("filled"),[netNames,setNetNames]=useState(false),[camera,setCamera]=useState("");
  useEffect(()=>{let live=true;void fetch("/demo/ebrake1.kicad_pcb").then(response=>{if(!response.ok)throw Error("Demo board unavailable");return response.text();}).then(source=>{if(live)setBoard(parseKicadBoard(source));}).catch(cause=>setError(String(cause)));return()=>{live=false;};},[]);
  const layers=board?["Board body",...new Set(board.layerDefinitions.map(layer=>layer.name))]:[];
  return <main style={{height:"100vh",display:"flex",flexDirection:"column",background:"var(--spike-table-surface)",color:"var(--spike-table-text)",font:"13px 'Segoe UI Variable Text',system-ui,sans-serif"}}>
    <header style={{padding:"10px 16px",borderBottom:"1px solid var(--spike-table-border)"}}><strong>SPIKE · Layer display</strong><p style={{margin:"4px 0",fontSize:11}}>Retained EBrake example · development browser preview · no solver run</p></header>
    <section style={{position:"relative",flex:1,minHeight:0}}>
      {board?<LayoutViewport board={board} visibleLayers={visibility} layerOpacity={opacity} zoneDisplay={mode} showNetNames={netNames} selectedId={null} cameraCommand={camera} selectionFilter="all" onSelect={()=>{}}/>:<p>{error||"Loading retained geometry…"}</p>}
      <ViewportLayerSelector board={board?{id:"example",name:"ebrake1.kicad_pcb",layers,visibility,opacity}:null} selectedBoardIds={board?["example"]:[]} showNetNames={netNames} onShowNetNames={(_,value)=>setNetNames(value)}
        onToggle={(_,layer)=>setVisibility(current=>({...current,[layer]:current[layer]===false}))} onShowAll={()=>setVisibility({})}
        onOpacity={(_,layer,value)=>setOpacity(current=>({...current,[layer]:value}))} onAllOpacity={(_,value)=>setOpacity(Object.fromEntries(layers.map(layer=>[layer,value])))}
        zoneDisplay={mode} onZoneDisplay={(_,value)=>setMode(value)} onResetView={()=>{setVisibility({});setOpacity({});setMode("filled");setCamera(`reset-view-${Date.now()}`);}}
        onManage={()=>setError("Wheel on a layer to adjust opacity; wheel All to apply a common opacity.")}/>
    </section><output id="layer-preview-state" style={{fontSize:11,padding:8,overflowWrap:"anywhere"}}>{JSON.stringify({mode,opacity,netNames})}</output><output id="qualification"/>{error}
  </main>;
}
if(new URLSearchParams(location.search).has("light"))document.documentElement.dataset.theme="light";
createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("narrow")
  ? <iframe title="Narrow layer display" src="./layer-style-preview.html" style={{width:560,height:700,display:"block",border:0}}/>
  : <Preview/>);
if(new URLSearchParams(location.search).has("qualify"))void(async()=>{
  const tick=(ms=80)=>new Promise(resolve=>setTimeout(resolve,ms));
  const get=(selector:string)=>{const node=document.querySelector<HTMLElement>(selector);if(!node)throw Error(`Missing ${selector}`);return node;};
  const check=(condition:unknown,message:string)=>{if(!condition)throw Error(message);};
  const state=()=>JSON.parse(get("#layer-preview-state").textContent!);
  try {
    for(let i=0;i<200&&!document.querySelector(".viewport-layer-pull");i++)await tick();
    await tick(200);get(".viewport-layer-pull").focus();get(".viewport-layer-pull").click();await tick();
    const layer=get('[data-layer-name="F.Cu"]'),all=get('[data-layer-opacity="all"]');
    const viewBox=get(".layout-viewport > svg").getAttribute("viewBox");
    const wheel=(target:HTMLElement,deltaY:number)=>target.dispatchEvent(new WheelEvent("wheel",{deltaY,bubbles:true,cancelable:true}));
    check(!wheel(layer,100),"wheel canceled before viewport zoom");await tick();
    check(state().opacity["F.Cu"]===.95&&layer.querySelector(".viewport-layer-percent")?.textContent==="95","numeric opacity feedback");
    await tick(400);wheel(layer,100);await tick(850);
    check(layer.querySelector(".viewport-layer-percent")?.textContent==="90","feedback delay restarts after final wheel");
    await tick(250);check(!layer.querySelector(".viewport-layer-percent"),"normal layer name returns after idle");
    check(get(".layout-viewport > svg").getAttribute("viewBox")===viewBox,"opacity gesture leaves camera unchanged");
    wheel(all,-100);await tick();check(Object.values(state().opacity).every(value=>value===1),"All resets every layer to master opacity");
    get(".viewport-layer-zone-mode").click();await tick();check(state().mode==="transparent","transparent mode");
    get(".viewport-layer-zone-mode").click();await tick();check(state().mode==="outline","outline mode");
    get('[aria-label^="Reset view for"]').click();await tick();check(state().mode==="filled"&&Object.keys(state().opacity).length===0,"reset camera/display defaults");
    get("#qualification").textContent="PASS: real-board wheel feedback, 1s idle restoration, camera isolation, All reset, three zone modes and view defaults";
  } catch(error) {get("#qualification").textContent=`FAIL: ${String(error)}`;}
})();
