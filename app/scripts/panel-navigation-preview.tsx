// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import FocusToolDeck, { activeFocusPanel } from "../src/FocusToolDeck";
import WorkspaceEditorTabs, { workspaceEditorPanels } from "../src/WorkspaceEditorTabs";
import PanelNavigation, { usePanelNavigation } from "../src/PanelNavigation";
import EMergeGerberImport from "../src/EMergeGerberImport";
import FocusCommandPanel from "../src/FocusCommandPanel";
import LayoutViewport from "../src/LayoutViewport";
import { parseKicadBoard, type ParsedBoard } from "../src/boardParser";
import "../src/styles.css";
import "../src/WorkbenchChrome.css";
import "../src/FocusWorkspace.css";
import "../src/WorkspaceViewTabs.css";
import "../src/PanelResponsive.css";
import "../src/buttonStandard.css";
function Preview() {
  const [board,setBoard]=useState<ParsedBoard|null>(null),[active,setActive]=useState<string|null>(null),[gerber,setGerber]=useState(false),[menu,setMenu]=useState(false);
  const [review,setReview]=useState(false),[draft,setDraft]=useState("Retained task note"),[notice,setNotice]=useState("Development browser preview; retained EBrake geometry, no solver run.");
  useEffect(()=>{void fetch("/demo/ebrake1.kicad_pcb").then(response=>response.text()).then(text=>setBoard(parseKicadBoard(text))).catch(error=>setNotice(String(error)));},[]);
  const panels=workspaceEditorPanels([
    {id:"gerber",title:"Gerber import",open:gerber,onClose:()=>{setGerber(false);setActive(null);},content:<EMergeGerberImport onClose={()=>{setGerber(false);setActive(null);}} onImport={async()=>{throw Error("Preview only: no source import or solver execution.");}}/>},
    {id:"review",title:"Study review with a realistic long title",open:review,onClose:()=>{setReview(false);setActive(null);},content:<section style={{padding:16}}><h3>Review current task</h3><label>Task note<input aria-label="Task note" value={draft} onChange={event=>setDraft(event.target.value)}/></label><p>Existing board geometry stays visible. Switching panels retains this draft.</p></section>},
  ]);
  const navigation=usePanelNavigation(panels,active,setActive);
  const openGerber=()=>{setGerber(true);setActive("gerber");},openReview=()=>{setReview(true);setActive("review");};
  return <div className="app-shell focus-shell interface-clean" style={{display:"flex",height:"100vh",flexDirection:"column"}}>
    <header style={{display:"flex",alignItems:"center",gap:8,padding:8}}><button id="focus-menu-toggle" type="button" onClick={()=>setMenu(value=>!value)}>Menu</button><strong>SPIKE · Navigation acceptance</strong><button type="button" onClick={openGerber}>Open Gerber setup</button><button type="button" onClick={openReview}>Open study review</button></header>
    <main className={`workspace focus-workspace has-editor-tabs ${activeFocusPanel(panels,active)?"workspace-document-open focus-panel-open":"focus-panel-closed"}`} style={{flex:1,minHeight:0}}>
      <div className="workspace-command-row"><WorkspaceEditorTabs panels={panels} activeId={active} onActivate={setActive} navigation={!active?<PanelNavigation panels={panels} activeId={active} onActivate={setActive} controller={navigation} noBreadcrumb/>:null}/><span style={{fontSize:11,minWidth:0}}>Main assembly · live board</span></div>
      <section id="workspace-board-content" className="canvas-area" style={{minHeight:0,position:"relative"}}>{board?<LayoutViewport board={board} visibleLayers={{}} layerOpacity={{}} showNetNames={false} cameraCommand="" selectedId={null} onSelect={()=>{}} selectionFilter="all"/>:<p>Loading retained geometry...</p>}</section>
      <FocusToolDeck panels={panels} activeId={active} commandsOpen={false} onActivate={setActive} navigation={navigation}/>
      {menu&&<aside style={{position:"absolute",left:8,top:8,width:360,height:500,zIndex:100}}><div className="floating-panel-frame"><FocusCommandPanel commands={[{id:"project",label:"Project",children:[{id:"import",label:"Import",children:[{id:"gerber-import",label:"Gerber setup",run:openGerber}]}]},{id:"studies",label:"Studies",children:[{id:"review-study",label:"Review study",run:openReview}]}]} onClose={()=>setMenu(false)}/></div></aside>}
    </main><output style={{padding:8,fontSize:11}}>{notice}</output>
  </div>;
}
createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("narrow")?<iframe title="Narrow SPIKE navigation acceptance" src="./panel-navigation-preview.html" style={{display:"block",width:new URLSearchParams(location.search).has("compact")?560:780,height:850,border:0}}/>:<Preview/>);
