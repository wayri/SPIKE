// SPDX-License-Identifier: Apache-2.0
import {useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import EMergeGerberImport from "../src/EMergeGerberImport";
import HelpCenter from "../src/HelpCenter";
import {OPEN_HELP_SECTION_EVENT,admitHelpSectionLocation,type HelpSectionLocation} from "../src/SectionHelpButton";
import "../src/styles.css";
import "../src/WorkbenchChrome.css";
import "../src/FocusWorkspace.css";
import "../src/PanelResponsive.css";
import "../src/buttonStandard.css";
function Preview(){
 const [location,setLocation]=useState<(HelpSectionLocation&{request:number})|null>(null),[notice,setNotice]=useState("");
 useEffect(()=>{const open=(event:Event)=>{const request=admitHelpSectionLocation((event as CustomEvent).detail);if(request)setLocation({...request,request:Date.now()});};window.addEventListener(OPEN_HELP_SECTION_EVENT,open);return()=>window.removeEventListener(OPEN_HELP_SECTION_EVENT,open);},[]);
 return <main className="app-shell focus-shell" style={{display:"flex",flexDirection:"column",height:"100vh"}}><header style={{padding:8,fontSize:12}}>SPIKE · bounded setup and contextual help · development UI fixture · no import or solver run</header><div className="focus-tool-content"><EMergeGerberImport onClose={()=>setNotice("Setup close routed")} onImport={async()=>{throw Error("Preview only: no design import.");}}/></div><output style={{padding:6,fontSize:11}}>{notice}</output>
 {location&&<HelpCenter initialTopic={location.topic} initialAnchor={location.anchor} navigationRequest={location.request} onClose={()=>setLocation(null)}/>}</main>;
}
createRoot(document.getElementById("root")!).render(new URLSearchParams(location.search).has("narrow")?<iframe title="Narrow setup layout" src="./setup-layout-preview.html" style={{display:"block",width:560,height:850,border:0}}/>:<Preview/>);
