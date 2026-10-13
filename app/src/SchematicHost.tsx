// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import { openSchematicWindow, closeSchematicWindow, updateSchematicWindow } from "./schematicWindow";
import type { SchematicSnapshot, SchematicAction } from "./kicadSchematicModel";
export default function SchematicHost({open,snapshot,onAction,onError}:{open:boolean;snapshot:SchematicSnapshot;onAction:(a:SchematicAction)=>void|Promise<void>;onError:(error:string)=>void}){
 const delivered=useRef<SchematicSnapshot | null>(null);
 const latest=useRef({snapshot,onAction,onError});latest.current={snapshot,onAction,onError};
 useEffect(()=>{if(!open)return;let disposed=false;const starting=openSchematicWindow(latest.current.snapshot,a=>latest.current.onAction(a));void starting.catch(e=>{if(!disposed)latest.current.onError(String(e));});return()=>{disposed=true;void starting.then(result=>closeSchematicWindow(result.lease)).catch(()=>{});};},[open]);
 useEffect(()=>{if(!open)return; const prev=delivered.current;
   if(prev && prev.document===snapshot.document && prev.linked===snapshot.linked && prev.boardName===snapshot.boardName && prev.busy===snapshot.busy && prev.status===snapshot.status && prev.selected.reference===snapshot.selected.reference && prev.selected.netCode===snapshot.selected.netCode)return;
   delivered.current=snapshot; void updateSchematicWindow(snapshot).catch(e=>latest.current.onError(String(e)));},[open,snapshot]);return null;
}
