// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { createRoot } from "react-dom/client";
import UniversalSearch from "../src/UniversalSearch";
import SelectSearchLayer from "../src/SelectSearchLayer";
import { SEARCH_PREFERENCES_KEY } from "../src/searchPreferences";
// Deliberately load the legacy shell after the component, reproducing the reported cascade.
import "../src/styles.css";
import "../src/WorkbenchChrome.css";
import "../src/FocusWorkspace.css";
import "../src/buttonStandard.css";
const rows = [
  ["assistant","SPIKE Assistant","Tools"],["em","EMerge Suite","EM"],
  ["pi","Configure DC voltage drop","PI analysis"],["si","Configure eye diagram","HF / SI"],
  ["thermal","Inspect temperatures","Thermal results"],["solver","Solver modules","Solver manager"],
  ["flow","CFD airflow setup","CFD"],["project","Open project","Project"],
  ["view","Fit viewport","View"],["help","Open examples","Help"],
  ["settings","Use AMOLED black viewport","Settings"],["unavailable","Unavailable solver","Solver manager"],
];
// This development fixture runs on its own localhost port. Preserve any prior test preferences.
const prior=localStorage.getItem(SEARCH_PREFERENCES_KEY);
localStorage.setItem(SEARCH_PREFERENCES_KEY,JSON.stringify({version:1,pins:[],usage:{assistant:{count:2,lastUsed:30},em:{count:8,lastUsed:20},unavailable:{count:1,lastUsed:10}}}));
window.addEventListener("pagehide",()=>prior===null?localStorage.removeItem(SEARCH_PREFERENCES_KEY):localStorage.setItem(SEARCH_PREFERENCES_KEY,prior),{once:true});
function Preview(){
 const [open,setOpen]=useState(true),[notice,setNotice]=useState("Development component acceptance. No solver runs."),[solver,setSolver]=useState("pi");
 return <div className="app-shell focus-shell" style={{padding:16,display:"block",height:"100vh"}}>
  <button type="button" onClick={()=>setOpen(true)}>Open search</button><output id="search-action-receipt" style={{display:"block",padding:12}}>{notice}</output>
  <label>Solver category<select aria-label="Solver category" value={solver} onChange={event=>setSolver(event.target.value)}><optgroup label="PI analysis"><option value="pi">DC voltage drop</option></optgroup><optgroup label="EM"><option value="em">Electromagnetic solver</option></optgroup><optgroup label="Thermal"><option value="thermal">Heat conduction</option></optgroup></select></label>
  <SelectSearchLayer/>
  <UniversalSearch open={open} onClose={()=>setOpen(false)} searchDocuments={()=>[]} items={rows.map(([id,label,category])=>({id,label,category,description:`${category} · illustrative command, no solver execution`,disabled:id==="unavailable",run:()=>setNotice(`Executed ${id}`)}))}/>
 </div>;
}
if(new URLSearchParams(location.search).has("light"))document.documentElement.dataset.theme="light";
createRoot(document.getElementById("root")!).render(<Preview/>);
