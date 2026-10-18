// SPDX-License-Identifier: Apache-2.0
/** Browser regression of the actual viewport; synthetic geometry, no capacity claim. */
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import AssemblyLayoutViewport from "../src/AssemblyLayoutViewport";
import type { ParsedBoard } from "../src/boardParser";
import type { VirtualBoardVisual } from "../src/harnessVisualization";
import "../src/buttonStandard.css";

const query = new URLSearchParams(location.search);
const count = Math.min(20, Math.max(1, Number(query.get("boards") || 20)));
const useBaseline = query.has("baseline");
// Optional ignored baseline captured by the validation procedure before editing.
const baselineModule = "../.tmp/AssemblyLayoutViewport.before.tsx";
const Viewport: typeof AssemblyLayoutViewport = useBaseline
  ? (await import(/* @vite-ignore */ baselineModule)).default : AssemblyLayoutViewport;
let coordinateReads = 0;
const source = {
  bounds:{minX:0,minY:0,maxX:80,maxY:50}, width:80,height:50,
  layers:["F.Cu","B.Cu"], layerDefinitions:[], layoutLayerUrls:{}, nets:{"1":"VCC","2":"GND"},
  tracks:Array.from({length:1200},(_,i)=>({id:`T${i}`,layer:i%2?"F.Cu":"B.Cu",net:i%2?"VCC":"GND",width:.18,
    get start(){coordinateReads++;return [2+i%75,2+Math.floor(i/75)*2.5] as [number,number];},end:[3+i%75,2+Math.floor(i/75)*2.5]})),
  pads:Array.from({length:80},(_,i)=>({id:`P${i}`,layers:["F.Cu"],net:"VCC",at:[3+i%20*3,2+Math.floor(i/20)*10],width:1,height:1,rotation:0})),
  components:[],drawings:[],vias:[],zones:[],outlineLoops:[],stackup:[],
} as unknown as ParsedBoard;
const boards = Array.from({length:count},(_,i)=>({id:`B${i}`,designId:"source",name:`Board ${i} with a realistic long occurrence name`,active:i===0,
  widthMm:80,heightMm:50,thicknessMm:1.6,localCenterMm:[40,25,0],
  netIdsByName:{VCC:`B${i}:power`,GND:`B${i}:return`},netNamesById:{[`B${i}:power`]:"VCC",[`B${i}:return`]:"GND"},
  transform:[1,0,0,i%5*90,0,1,0,Math.floor(i/5)*60,0,0,1,0,0,0,0,1]})) as VirtualBoardVisual[];
const designs={source}, layers={"F.Cu":true,"B.Cu":true}, empty={}, noHarnesses:[]=[];
const frame=()=>new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));

function Preview(){
  const [message,setMessage]=useState("Ready"),[selected,setSelected]=useState<string|null>(null),[linked,setLinked]=useState<Record<string,string[]>>({});
  const [hidden,setHidden]=useState(false);
  const [selection,setSelection]=useState("none");
  const onBoardSelect=React.useCallback((board:VirtualBoardVisual)=>setSelected(board.id),[]);
  const onNetSelect=React.useCallback((id:string,net:string)=>{setLinked({[id]:[net]});setSelection(`${id} ${net}`);},[]);
  const visibility=React.useMemo(()=>{
    const next:Record<string,Record<string,boolean>>={};
    if(hidden)next.B0={"F.Cu":false,"B.Cu":false};
    return next;
  },[hidden]);
  const run=async()=>{
    try{
      await frame();await frame();
      const svg=document.querySelector<SVGSVGElement>(".assembly-layout-drawing")!;
      const before=svg.getAttribute("viewBox"), nodes=svg.querySelectorAll("[data-canonical-net-id]");
      let viewChanged=false;
      coordinateReads=0;
      const durations:number[]=[];
      for(let i=0;i<30;i++){
        const rect=svg.getBoundingClientRect(),started=performance.now();
        svg.dispatchEvent(new WheelEvent("wheel",{bubbles:true,cancelable:true,clientX:rect.left+rect.width/2,clientY:rect.top+rect.height/2,deltaY:i%2?-12:12}));
        await frame();await frame();durations.push(performance.now()-started);
        viewChanged ||= svg.getAttribute("viewBox")!==before;
      }
      const afterNodes=svg.querySelectorAll("[data-canonical-net-id]");
      if(!viewChanged)throw Error("Zoom did not update");
      if(nodes.length!==afterNodes.length||!Array.from(nodes).every((node,i)=>node===afterNodes[i]))throw Error("Geometry or hit targets were replaced");
      if(!useBaseline&&coordinateReads!==0)throw Error(`Camera movement rescanned ${coordinateReads} source coordinates`);
      durations.sort((a,b)=>a-b);
      setMessage(JSON.stringify({status:"passed",baseline:useBaseline,boards:count,tracksPerBoard:1200,gestures:30,coordinateReads,retainedHitTargets:nodes.length,p50GestureTwoRafMs:durations[15],p95GestureTwoRafMs:durations[28]}));
    }catch(error){setMessage(`FAILED ${error}`);}
  };
  return <main style={{height:"100vh",display:"flex",flexDirection:"column",background:"#101820",color:"#eef4f6",fontFamily:"sans-serif"}}>
    <header style={{padding:12,display:"flex",gap:12,alignItems:"center"}}><button onClick={()=>void run()}>Run zoom regression</button><button onClick={()=>setHidden(value=>!value)}>Toggle B0 layers</button><span>{selection}</span></header>
    <output id="result" style={{padding:12,overflowWrap:"anywhere"}}>{message}</output>
    <div style={{flex:1,minHeight:0,position:"relative"}}><Viewport designs={designs} boards={boards} harnesses={noHarnesses} selectedBoardId={selected} linkedNets={linked} visibleLayers={layers} assemblyLayerVisibility={visibility} layerOpacity={empty} showVias onBoardSelect={onBoardSelect} onShowAllBoards={()=>setSelected(null)} onNetSelect={onNetSelect}/></div>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
