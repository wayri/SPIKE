// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import KicadSchematicViewer from "./KicadSchematicViewer";
import { connectSchematicChild } from "./schematicWindow";
import type { SchematicSnapshot, SchematicAction } from "./kicadSchematicModel";
export default function SchematicWindowRoot(){
 const [snapshot,setSnapshot]=useState<SchematicSnapshot>({document:null,linked:false,boardName:"",selected:{},busy:false,status:"Connecting to SPIKE…"});const [error,setError]=useState("");const [act,setAct]=useState<(a:SchematicAction)=>void>(()=>()=>{});
 useEffect(()=>{let cancelled=false;let stop:(()=>void)|undefined;void connectSchematicChild(setSnapshot).then(c=>{if(cancelled)c.stop();else{const closed=()=>{void c.act({type:"closed"});}; window.addEventListener("pagehide",closed); stop=()=>{window.removeEventListener("pagehide",closed);c.stop();};setAct(()=>(a:SchematicAction)=>{void c.act(a).catch(e=>setError(String(e)));});}}).catch(e=>setError(String(e)));return()=>{cancelled=true;stop?.();};},[]);
 return <KicadSchematicViewer snapshot={error?{...snapshot,status:error}:snapshot} act={act} nativeWindow={"__TAURI_INTERNALS__" in window}/>;
}
