// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import WorkspaceHeader from "../src/WorkspaceHeader";
import FocusToolDeck from "../src/FocusToolDeck";
import { ListTree, Settings2 } from "../src/icons";
import "../src/styles.css";
import "../src/WorkbenchChrome.css";
import "../src/FocusWorkspace.css";
import "../src/PanelResponsive.css";
import "../src/WorkspaceHeader.css";
import "../src/buttonStandard.css";
function Preview() {
  const [open,setOpen]=useState(true),[active,setActive]=useState<string|null>("review"),[notice,setNotice]=useState("");
  const [draft,setDraft]=useState("Retained investigation draft");
  const [busy,setBusy]=useState(false);
  const restore=()=>{setOpen(true);setActive("review");};
  return <div className="app-shell focus-shell interface-clean ribbon-hidden bottom-closed" style={{display:"flex",flexDirection:"column",height:"100vh"}}>
    <WorkspaceHeader projectName="Assembly controller investigation.spike" fileActions={[{label:"Project manager",run:restore}]} onFilesOpen={()=>{}} workspaces={[]} activeWorkspace="Home" onWorkspace={()=>{}} showWorkspaceBar={false} workspaceSwitcher={null} menuOpen={false} onMenu={restore} searchOpen={false} onSearch={()=>setNotice("Search opened")}
      studyActions={[{label:"Studies and simulations manager",icon:ListTree,run:()=>setNotice("Study manager action")},{label:"Results workspace",icon:Settings2,run:()=>setNotice("Results action")},{label:"Stop active analysis",disabled:true,run:()=>{}}]} utilities={<button type="button" onClick={restore}>Restore</button>}/>
    <main className="workspace focus-workspace workspace-document-open focus-panel-open" style={{flex:1,minHeight:0,display:"block",position:"relative"}}>
      <FocusToolDeck panels={[{id:"review",title:"Study investigation with a realistic long title",presentation:"document",open,onClose:()=>{setOpen(false);setActive(null);setNotice("Closed through owner");},content:<section style={{padding:20}}><h3>Study review</h3><p>Actual shared interface components. No solver output is claimed.</p><label style={{display:"grid",gap:6}}>Draft<input id="retained-draft" value={draft} onChange={event=>setDraft(event.target.value)}/></label><button type="button" aria-pressed={busy} onClick={()=>setBusy(value=>!value)}>Toggle active operation fixture</button><footer><button type="button" disabled={busy} onClick={()=>setOpen(false)}>Close</button></footer></section>}]} activeId={active} commandsOpen={false} onActivate={setActive}/>
      {!active&&<p style={{padding:24}}>Board viewport · Restore returns to the retained editor.</p>}
    </main><output style={{padding:8}}>{notice || "Header: right-click or Shift+F10 for window actions."}</output>
  </div>;
}
createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("narrow")
  ? <iframe title="Narrow SPIKE header fixture" src="./panel-header-preview.html" style={{display:"block",width:560,height:700,border:0}}/>
  : <Preview/>);
