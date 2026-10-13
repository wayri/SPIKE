// SPDX-License-Identifier: Apache-2.0
// Capture-only harness: real SPIKE renderer, retained geometry and solver samples.
import React, { useEffect, useMemo, useState } from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import BoardViewport from '../src/BoardViewport';
import {parseDesignSourceOffThread} from '../src/boardImport';
import type {ParsedBoard} from '../src/boardParser';
import type {ViewportRestoreCommand,Viewport3DCameraState} from '../src/workspaceState';
import '../src/styles.css';
import '../src/buttonStandard.css';
const noop=()=>{}, empty={};
const base='/@fs/C:/Users/yawar/Documents/agws/KiCAD_plugins/SPIKE/';
const thermal=new URLSearchParams(location.search).has('thermal');
const marble=new URLSearchParams(location.search).has('marble');
function Capture(){
 const [board,setBoard]=useState<ParsedBoard|null>(null);
 const [result,setResult]=useState<any>(null);
 const [restore,setRestore]=useState<ViewportRestoreCommand|null>(null);
 const visible=useMemo(()=>Object.fromEntries((board?.layers??[]).map(l=>[l,/Cu|Mask|SilkS|Edge.Cuts/.test(l)])),[board]);
 useEffect(()=>{void(async()=>{
  let next:ParsedBoard;
  if(marble){
   const root=base+'app/.tmp/product-promo-capture/marble/';
   next=await parseDesignSourceOffThread('Marble.kicad_pcb',await(await fetch(root+'Marble.kicad_pcb')).text());
   if(thermal)setResult(await(await fetch(root+'thermal-result.json')).json());
   else next={...next,boardModelUrl:root+'board.glb',componentModelUrl:root+'components.glb',boardModelIncludesCopper:false};
  }else if(thermal){
   next=await parseDesignSourceOffThread('iot-esp-eth-ind.kicad_pcb',await(await fetch(base+'app/.tmp/product-promo-capture/thermal-source.kicad_pcb')).text());
   setResult(await(await fetch(base+'app/.tmp/product-promo-capture/thermal-result.json')).json());
  }else{
   const root=base+'app/.tmp/assembly-performance/';
   next=await parseDesignSourceOffThread('retained.spike-design.json',await(await fetch(root+'source.json')).text(),'spike-normalized');
   next={...next,boardModelUrl:root+'board.glb',componentModelUrl:root+'components.glb',boardModelIncludesCopper:true};
  }
  setBoard(next);
 })();},[]);
 useEffect(()=>{
  (window as any).setCaptureFrame=(i:number,n:number)=>{
   const initial=(window as any).initialCaptureCamera as Viewport3DCameraState;
   if(!initial)throw Error('Initial camera is not ready');
   const t=i/(n-1),p=t*t*(3-2*t),a=(thermal?0.65:0.55)*p;
   const [x,y,z]=initial.position.map((v,k)=>v-initial.target[k]);
   const c=Math.cos(a),s=Math.sin(a);
   const next={...initial,position:[initial.target[0]+x*c-y*s,initial.target[1]+x*s+y*c,initial.target[2]+z] as [number,number,number]};
   flushSync(()=>setRestore({token:i+1,threeD:next}));
   return new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
  };
 },[]);
 const onCamera=(camera:Viewport3DCameraState)=>{
  (window as any).latestCaptureCamera=structuredClone(camera);
  if(!(window as any).initialCaptureCamera)(window as any).initialCaptureCamera=structuredClone(camera);
 };
 return <div className="board-canvas is-3d" style={{position:'relative',width:'100vw',height:'100vh',background:'#111c24'}}>
  {board&&<BoardViewport board={board} viewMode="3D" visibleLayers={visible} layerOpacity={empty} layerSeparation={0}
   showVias showModels={!thermal} showSmdModels showThtModels showAxes={false} selectionBlink={false}
   navigationMode="orbit" navigationInertia={false} cameraCommand="fit:initial" viewportRestore={restore}
   selectionFilter="all" selectedId={null} onSelect={noop} onCamera={onCamera}
   thermalScenario={thermal&&result?{board_thermal_result:result}:null}
   onModelStatus={status=>{(window as any).captureModelStatus=status;}}/>}
 </div>;
}
createRoot(document.getElementById('root')!).render(<Capture/>);
