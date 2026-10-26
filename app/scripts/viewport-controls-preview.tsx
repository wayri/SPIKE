// SPDX-License-Identifier: Apache-2.0
import {useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import ViewportEssentialTools from "../src/ViewportEssentialTools";
import MainFieldControls from "../src/MainFieldControls";
import ToolbarMenu from "../src/ToolbarMenu";
import BoardViewport,{type BoardObject} from "../src/BoardViewport";
import {parseKicadBoard,type ParsedBoard} from "../src/boardParser";
import {defaultResultVisualization} from "../src/analysisResults";
import {Settings2} from "../src/icons";
import "../src/styles.css";
import "../src/WorkbenchChrome.css";
import "../src/buttonStandard.css";
function Preview(){
 const [board,setBoard]=useState<ParsedBoard|null>(null),[mode,setMode]=useState<"2D"|"3D">("2D"),[nav,setNav]=useState<"orbit"|"pan">("orbit"),[filter,setFilter]=useState<"all"|"part"|"net">("all"),[camera,setCamera]=useState("");
 const [selected,setSelected]=useState<BoardObject|null>(null),[translucent,setTranslucent]=useState(false),[opacity,setOpacity]=useState(.18),[open,setOpen]=useState(false),[notice,setNotice]=useState("");
 useEffect(()=>{void fetch("/demo/ebrake1.kicad_pcb").then(r=>r.text()).then(source=>setBoard(parseKicadBoard(source)));},[]);
 return <main style={{height:"100vh",display:"flex",flexDirection:"column"}}><header style={{padding:12}}><strong>SPIKE · Viewport controls</strong><p style={{margin:"4px 0",fontSize:12}}>Retained EBrake geometry · development browser acceptance · no solver run or native model loading claimed</p></header>
 <div className="canvas-toolbar" style={{display:"flex",flexWrap:"wrap",gap:10,padding:8,borderBlock:"1px solid var(--spike-table-border)"}}>
 <ViewportEssentialTools viewMode={mode} navigationMode={nav} selectionFilter={filter} onMode={setMode} onNavigation={setNav} onFilter={setFilter} onCamera={value=>setCamera(`${value}-${Date.now()}`)} translucent={translucent} onTranslucent={()=>setTranslucent(v=>!v)} hasGeometry={Boolean(board)}/>
 <ToolbarMenu label="Viewport tools" icon={Settings2} actions={[{label:"Reset view",run:()=>setCamera(`reset-view-${Date.now()}`)},{label:"Display settings",run:()=>setNotice("Display action routed")}]}/>
 <MainFieldControls view={null} open={open} onOpen={setOpen} onPresent={()=>{}} onOptions={()=>{}} onVisible={()=>{}} onClear={()=>{}} onManageAll={()=>setNotice("Result manager action routed")}
 layers={[{id:"analysis",label:"PI / SI analysis overlay",available:false,visible:false,onVisible:()=>{}},{id:"em",label:"EM field overlay",available:false,visible:false,onVisible:()=>{}},{id:"thermal",label:"Thermal result field",available:false,visible:false,onVisible:()=>{}},{id:"board",label:"Translucent board context",available:Boolean(board),visible:translucent,onVisible:setTranslucent,opacity,onOpacity:setOpacity}]}/>
 <button type="button" onClick={()=>{const track=board?.tracks[0];if(track)setSelected({id:track.id,type:"trace",name:track.net||"Trace",net:track.net});}}>Select example trace</button>
 </div><section style={{position:"relative",flex:1,minHeight:0}}>{board&&<BoardViewport board={board} viewMode={mode} visibleLayers={{}} layerOpacity={{}} layerSeparation={0} showVias showModels={false} showSmdModels={false} showThtModels={false} navigationMode={nav} navigationInertia={false} cameraCommand={camera} selectionFilter={filter} selectedId={selected?.id??null} selectedNet={selected?.net} onSelect={setSelected} onCamera={()=>{}} resultVisualization={{...defaultResultVisualization(),sceneMode:translucent?"translucent":"opaque",translucentScene:translucent,boardOpacity:opacity}}/>}</section>
 <output id="controls-state" style={{padding:8,fontSize:12}}>{JSON.stringify({mode,translucent,opacity,selected:selected?.net??null,notice})}</output><output id="qualification"/>
 </main>;
}
createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("narrow") ? <iframe title="Narrow viewport controls" src="./viewport-controls-preview.html" style={{width:560,height:700,border:0,display:"block"}}/> : <Preview/>);
if(new URLSearchParams(location.search).has("qualify"))void(async()=>{
 const tick=(ms=80)=>new Promise(r=>setTimeout(r,ms));
 const get=(label:string)=>{const node=document.querySelector<HTMLElement>(`[aria-label="${label}"]`);if(!node)throw Error(`Missing ${label}`);return node;};
 const check=(value:unknown,message:string)=>{if(!value)throw Error(message);};
 const enter=(el:HTMLElement)=>el.dispatchEvent(new MouseEvent("mouseover",{bubbles:true,relatedTarget:document.body}));
 const leave=(el:HTMLElement)=>el.dispatchEvent(new MouseEvent("mouseout",{bubbles:true,relatedTarget:document.body}));
 try{
 await tick(300);get("3D view").click();await tick();
 for(const [trigger,title] of [["Camera view","Camera view context menu"],["Viewport tools","Viewport tools context menu"]]){
 const button=get(trigger);enter(button);await tick();check(document.querySelector(`[aria-label="${title}"]`),`${trigger} hover opens`);
 leave(button);await tick(160);check(!document.querySelector(`[aria-label="${title}"]`),`${trigger} hover dismisses`);
 enter(button);await tick();button.click();await tick();leave(button);await tick(160);check(document.querySelector(`[aria-label="${title}"]`),`${trigger} click pins`);
 document.body.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true}));await tick();check(!document.querySelector(`[aria-label="${title}"]`),`${trigger} outside closes`);
 }
 const fields=get("Result layers and fields");enter(fields);await tick();check(document.querySelector(".main-field-popover"),"Fields hover opens");leave(fields);await tick(160);check(!document.querySelector(".main-field-popover"),"Fields hover dismisses");
 fields.click();await tick();leave(fields);await tick(160);check(document.querySelector(".main-field-popover"),"Fields click pins");get("Close field controls").click();await tick();
 get("2D view").click();await tick();check(get("Camera view").hasAttribute("disabled"),"2D camera restrictions retained");
 document.querySelector("#qualification")!.textContent="PASS: actual React hover previews dismiss, click pins, outside closes; Fields boundary; 2D restrictions";
 }catch(e){document.querySelector("#qualification")!.textContent=`FAIL: ${String(e)}`;}
})();
