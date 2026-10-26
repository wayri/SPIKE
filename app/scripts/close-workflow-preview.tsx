// SPDX-License-Identifier: Apache-2.0
import {useState} from "react";
import {createRoot} from "react-dom/client";
import FocusToolDeck from "../src/FocusToolDeck";
import "../src/styles.css";
import "../src/FocusWorkspace.css";
import "../src/buttonStandard.css";
function Preview(){
 const [open,setOpen]=useState(true),[active,setActive]=useState<string|null>("draft"),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false),[notice,setNotice]=useState("Draft retained"),[draft,setDraft]=useState("Unsaved engineering notes");
 const finish=()=>{setNotice("Closed through original confirmation workflow");setOpen(false);setActive(null);};
 return <div className="app-shell focus-shell" style={{display:"flex",flexDirection:"column",height:"100vh"}}><header style={{padding:8,display:"flex",gap:8}}><button type="button" onClick={()=>setBusy(value=>!value)}>Toggle busy</button><button type="button" onClick={()=>{setOpen(true);setActive("draft");setConfirm(false);}}>Reopen</button></header><main className="workspace" style={{flex:1,display:"block",minHeight:0}}><FocusToolDeck panels={[{id:"draft",title:"Draft editor",open,presentation:"document",onClose:()=>setNotice("ERROR: owner fallback bypassed original workflow"),content:<section style={{padding:16}} role="dialog" aria-label="Draft editor"><header><h3>Draft editor</h3><button type="button" aria-label="Close draft editor" disabled={busy} onClick={()=>setConfirm(true)}>Close</button></header><label>Notes<input aria-label="Notes" value={draft} onChange={event=>setDraft(event.target.value)}/></label><section hidden><footer><button disabled>Cancel</button><button disabled>Close</button></footer></section><section role="dialog" aria-label="Nested tool"><button type="button" disabled aria-label="Close nested tool">Close nested tool</button></section>{confirm&&<section role="alertdialog" aria-label="Unsaved changes"><p>Keep or discard this test draft?</p><button type="button" onClick={()=>setConfirm(false)}>Keep editing</button><button type="button" onClick={finish}>Discard test draft and close</button></section>}</section>}]} activeId={active} onActivate={setActive} commandsOpen={false}/></main><output id="close-receipt" style={{padding:12}}>{notice}</output></div>;
}
createRoot(document.getElementById("root")!).render(<Preview/>);

if(new URLSearchParams(location.search).has("qualify"))void(async()=>{
 const tick=()=>new Promise(resolve=>setTimeout(resolve,80));
 const button=(label:string)=>document.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;
 const textButton=(label:string)=>Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(node=>node.textContent===label)!;
 const check=(value:unknown,message:string)=>{if(!value)throw Error(message);};
 try{
  await tick();check(!button("Close Draft editor").disabled,"hidden Cancel and nested disabled Close must not block owner");
  button("Close Draft editor").click();await tick();check(document.querySelector('[role="alertdialog"]'),"original editor confirmation opened");
  check(button("Close Draft editor").disabled,"open confirmation blocks repeated Close");
  textButton("Keep editing").click();await tick();check(document.querySelector<HTMLInputElement>('[aria-label="Notes"]')?.value==="Unsaved engineering notes","cancelling retains draft");
  textButton("Toggle busy").click();await tick();check(button("Close Draft editor").disabled,"actual busy owner blocks Close");
  textButton("Toggle busy").click();await tick();check(!button("Close Draft editor").disabled,"Close recovers when operation finishes");
  button("Close Draft editor").click();await tick();textButton("Discard test draft and close").click();await tick();
  check(document.querySelector("#close-receipt")?.textContent==="Closed through original confirmation workflow","original close handler completed");
  check(!document.querySelector(".focus-tool-deck"),"panel dismissed");
  document.querySelector("#close-receipt")!.textContent="PASS: hidden/nested controls, busy recovery, unsaved confirmation, cancellation, original Close and final dismissal";
 }catch(error){document.querySelector("#close-receipt")!.textContent=`FAIL: ${String(error)}`;}
})();
