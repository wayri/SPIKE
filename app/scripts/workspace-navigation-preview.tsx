// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import { Boxes, CircuitBoard, Wind, Activity, Settings2 } from "../src/icons";
import UniversalSearch from "../src/UniversalSearch";
import WorkspaceToolbar from "../src/WorkspaceToolbar";
import ViewportLayerSelector from "../src/ViewportLayerSelector";
import "../src/styles.css";
import "../src/buttonStandard.css";
const names=["Home","Mesh","Solve","PI","HF / SI","EM","Thermal","Probes","Results","Reports","Extensions","Settings"];
function Preview(){
  const [searchOpen,setSearchOpen]=useState(new URLSearchParams(location.search).has("search"));
  const [workspace,setWorkspace]=useState("Home"),[selection,setSelection]=useState(["A"]),[notice,setNotice]=useState("");
  const [layers,setLayers]=useState<Record<string,Record<string,boolean>>>({A:{"F.Cu":true,"In1.Cu":true,"In2.Cu":false,"B.Cu":true},B:{"F.Cu":false,"In1.Cu":true,"In2.Cu":true,"B.Cu":true}});
  const [netNames,setNetNames]=useState<Record<string,boolean>>({A:false,B:false});
  const id=selection.length===1?selection[0]:null;
  return <main style={{padding:16,color:"var(--spike-table-text)",background:"var(--spike-table-surface)",minHeight:"100vh",boxSizing:"border-box"}}>
    <UniversalSearch open={searchOpen} onClose={()=>setSearchOpen(false)} items={Array.from({length:30},(_,i)=>({id:`result-${i}`,label:`${names[i%names.length]} analysis for Board A with a long occurrence name`,category:"Assembly / simulation setup",description:"Review retained sources, loads, layer visibility, mesh and solver prerequisites before running this study.",run:()=>setSearchOpen(false)}))}/>
    <h1 style={{fontSize:18}}>SPIKE workspace navigation</h1><p>Interactive interface fixture. No solver results or native rendering claimed.</p>
    <div style={{display:"flex",alignItems:"center",gap:8,borderBlock:"1px solid var(--spike-table-border)",padding:"8px 0"}}>
      <WorkspaceToolbar activeWorkspace={workspace} onWorkspace={setWorkspace} workspaces={names.map(name=>({name,icon:name==="Thermal"?Wind:CircuitBoard}))}
        actions={[{id:"setup",label:`${workspace} setup`,icon:Settings2,children:[{id:"review",label:"Review inputs",icon:Activity,run:()=>setNotice("Inputs opened")}]},{id:"run",label:"Run",icon:Activity,disabled:true,run:()=>{}}]}/>
      <span>{workspace}</span><Boxes size={15}/><span>Main assembly</span>

    </div><section data-layer-viewport style={{position:"relative",height:180,marginTop:12,border:"1px solid var(--spike-table-border)",background:"var(--spike-table-field)"}}>
      <p style={{margin:0,padding:"16px 40px",color:"var(--spike-table-muted)"}}>Viewport area · layers reveal from the upper-left edge</p>
      <ViewportLayerSelector board={id?{id,name:`Board ${id} with a long occurrence name`,layers:Object.keys(layers[id]),visibility:layers[id]}:null} selectedBoardIds={selection} showNetNames={id ? netNames[id] : false} onShowNetNames={(boardId,visible)=>setNetNames(current=>({...current,[boardId]:visible}))}
        onToggle={(boardId,layer)=>setLayers(current=>({...current,[boardId]:{...current[boardId],[layer]:!current[boardId][layer]}}))}
        onShowAll={boardId=>setLayers(current=>({...current,[boardId]:Object.fromEntries(Object.keys(current[boardId]).map(layer=>[layer,true]))}))} onManage={()=>setNotice("Layer manager")}/></section><section style={{marginTop:16,display:"flex",gap:8,flexWrap:"wrap"}}>
      <button data-select="A" onClick={()=>setSelection(["A"])}>Select board A</button><button data-select="B" onClick={()=>setSelection(["B"])}>Select board B</button>
      <button data-select="both" onClick={()=>setSelection(["A","B"])}>Select both boards</button><button data-select="none" onClick={()=>setSelection([])}>Clear selection</button>
    </section><p>{notice}</p><output id="acceptance"/><pre id="layer-state">{JSON.stringify(layers)}</pre><output id="net-name-state">{JSON.stringify(netNames)}</output>
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);
if(new URLSearchParams(location.search).has("qualify")) void(async()=>{
 const tick=()=>new Promise(resolve=>setTimeout(resolve,40));await tick();
 const get=(selector:string)=>{const node=document.querySelector<HTMLElement>(selector);if(!node)throw new Error(`Missing ${selector}`);return node;};
 const check=(value:unknown,label:string)=>{if(!value)throw new Error(label);};
 try{
  if(!new URLSearchParams(location.search).has("layerOnly")){
  const hover=(event:string)=>get(".workspace-toolbar").dispatchEvent(new MouseEvent(event,{bubbles:true,relatedTarget:document.body}));
  hover("mouseover");await tick();check(document.querySelector(".workspace-toolbar-flyout"),"hover opens");
  const scroller=get(".workspace-toolbar-workspaces .command-strip-viewport");
  const buttons=[...document.querySelectorAll<HTMLElement>(".workspace-toolbar-workspace")];
  const bounds=scroller.getBoundingClientRect();
  const direct=buttons.filter(button=>{const box=button.getBoundingClientRect();return box.left>=bounds.left-1&&box.right<=bounds.right+1;});
  check(new Set(buttons.map(button=>Math.round(button.getBoundingClientRect().top))).size===2,"controls use two compact rows");
  check(direct.length===names.length,"all twelve workspace controls directly visible at supported widths");
  get('[aria-label="Home workspace"]').focus();get('[aria-label="Home workspace"]').dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowDown",bubbles:true}));
  check(document.activeElement===get('[aria-label="Mesh workspace"]'),"down moves within the grid column");
  get('[aria-label="Home workspace"]').dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowRight",bubbles:true}));
  check(document.activeElement===get('[aria-label="Solve workspace"]'),"right moves to the next grid column");
  const overflowElements=[...document.querySelectorAll<HTMLElement>("*")].filter(node=>/auto|scroll/.test(getComputedStyle(node).overflowX+getComputedStyle(node).overflowY));
  check(overflowElements.every(node=>getComputedStyle(node).scrollbarWidth==="none"&&getComputedStyle(node,"::-webkit-scrollbar").display==="none"),"all native UI scrollbars hidden");
  const rect=get(".workspace-toolbar-flyout").getBoundingClientRect();check(rect.left>=0&&rect.right<=innerWidth,"flyout stays inside viewport");
  hover("mouseout");await tick();check(!document.querySelector(".workspace-toolbar-flyout"),"hover leave closes");
  get(".workspace-toolbar-trigger").click();await tick();hover("mouseout");await tick();check(document.querySelector(".workspace-toolbar-flyout"),"pinned survives leave");
  get('[aria-label="Thermal workspace"]').click();await tick();check(get('[aria-label="Thermal workspace"]').getAttribute("aria-pressed")==="true","workspace selected");
  get('[aria-label="Thermal setup"]').click();await tick();get('[aria-label="Review inputs"]').click();await tick();check(document.body.textContent?.includes("Inputs opened"),"submenu routes existing handler");
  document.body.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true}));await tick();check(!document.querySelector(".workspace-toolbar-flyout"),"outside closes pinned");
  get(".workspace-toolbar-trigger").click();await tick();document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));await tick();check(!document.querySelector(".workspace-toolbar-flyout"),"Escape closes");
  }
  const revealLayers=async()=>{get(".viewport-layer-selector").dispatchEvent(new MouseEvent("mouseover",{bubbles:true,relatedTarget:document.body}));await tick();};
  const layerRoot=get(".viewport-layer-selector"),viewport=get("[data-layer-viewport]");
  check(!document.querySelector(".viewport-layer-choices"),"edge selector rests collapsed");
  check(Number(getComputedStyle(layerRoot).opacity)<.5,"resting pull is semi-transparent");
  check(Math.abs(layerRoot.getBoundingClientRect().left-viewport.getBoundingClientRect().left)<3,"pull is attached to viewport left edge");
  await revealLayers();check(document.querySelector(".viewport-layer-choices"),"hover reveals layer array");
  get(".viewport-layer-selector").dispatchEvent(new MouseEvent("mouseout",{bubbles:true,relatedTarget:document.body}));await tick();
  check(!document.querySelector(".viewport-layer-choices"),"pointer leaving the full control bounds collapses layers");
  await revealLayers();
  get('[aria-label^="F.Cu on Board A"]').click();await tick();check(JSON.parse(get("#layer-state").textContent!).A["F.Cu"]===false,"A layer changed");
  get('[data-select="B"]').click();await tick();await revealLayers();get('[aria-label^="F.Cu on Board B"]').click();await tick();const state=JSON.parse(get("#layer-state").textContent!);check(!state.A["F.Cu"]&&state.B["F.Cu"],"occurrences isolated");
  get('[data-select="both"]').click();await tick();check(!document.querySelector(".viewport-layer-selector"),"multi-selection hides layers");
  get('[data-select="none"]').click();await tick();check(!document.querySelector(".viewport-layer-selector"),"no-selection hides layers");
  get('[data-select="A"]').click();await tick();await revealLayers();check(get('[aria-label^="F.Cu on Board A"]').getAttribute("aria-pressed")==="false","A preferences retained");
  const section=get(".viewport-layer-net-names") as HTMLDetailsElement;
  check(!section.open,"net names collapsed initially");
  get(".viewport-layer-net-names summary").click();await tick();check(section.open,"net names expand downwards");
  const toggle=get('[aria-label^="Net names on Board A"]');
  check(toggle.getBoundingClientRect().top>=get(".viewport-layer-choices .command-strip").getBoundingClientRect().bottom,"net options below layer chips");
  toggle.click();await tick();check(JSON.parse(get("#net-name-state").textContent!).A===true&&!JSON.parse(get("#net-name-state").textContent!).B,"net visibility scoped to A");
  get("#acceptance").textContent="PASS: downward net-name expansion and occurrence toggle; viewport edge pull/reveal/collapse, retained layer scope, two-row workspaces, grid keyboard, no native scrollbars, hover, pin, outside, Escape, workspace/submenu routing, bounds, layer scope and retention";
  if(new URLSearchParams(location.search).has("layerOnly"))get("#acceptance").textContent="PASS: layer pull/reveal/collapse, scope retention, downward net-name expansion and selected occurrence toggle";
  get(".viewport-layer-selector").dispatchEvent(new MouseEvent("mouseout",{bubbles:true,relatedTarget:document.body}));await tick();
  if(new URLSearchParams(location.search).has("layers")){await revealLayers();get(".viewport-layer-net-names summary").click();await tick();}
 }catch(error){get("#acceptance").textContent=`FAIL: ${String(error)}`;}
})();
