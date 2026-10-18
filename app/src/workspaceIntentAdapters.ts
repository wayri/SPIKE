// SPDX-License-Identifier: Apache-2.0
import type {ParsedBoard} from "./boardParser";
import {componentThermalElements,normalizeThermalElements} from "./thermalAssembly";
import type {WorkspaceReviewedIntent} from "./workspaceIntentModel";
/** Translate a reviewed board-local identity only through a unique exact name. */
export function canonicalIntentNet(id:string, board:ParsedBoard, nets:readonly {id:string;name:string}[]):string {
 const name=board.nets[id]; if(!name)throw new Error("The reviewed net no longer exists.");
 const matches=nets.filter(net=>net.name===name);
 if(matches.length!==1)throw new Error(`Canonical net ${name} is missing or ambiguous. Review the active design.`);
 return matches[0].id;
}
/** Patch explicit heat inputs, preserve materials/contacts, and invalidate old outcomes. */
export function thermalIntentScenario(board:ParsedBoard,previous:Record<string,unknown>|null,request:WorkspaceReviewedIntent):Record<string,unknown>{
 const {parameters,bindings}=request.draft;
 if(!Number.isFinite(parameters.powerW)||parameters.powerW<0||!Number.isFinite(parameters.ambientC)||parameters.ambientC<=-273.15)throw new Error("Review total heat and ambient temperature.");
 const ids=new Set(bindings.componentIds);for(const id of ids)if(!board.components.some(row=>row.id===id))throw new Error("A reviewed thermal component no longer exists.");
 const saved=normalizeThermalElements(previous?.thermal_elements);
 const generated=componentThermalElements(board).map(row=>saved.find(old=>old.object_id===row.object_id) ?? row);
 const other=saved.filter(row=>row.kind!=="pcb_component");
 const powers=ids.size===1?{[[...ids][0]]:parameters.powerW}:request.choices.componentPowersW;
 if(ids.size){const sum=[...ids].reduce((total,id)=>{const power=powers[id];if(!Number.isFinite(power)||power<0)throw new Error("Review each component heat input.");return total+power;},0);if(Math.abs(sum-parameters.powerW)>1e-9*Math.max(1,parameters.powerW))throw new Error("Component heat must conserve the supplied total.");}
 const boardSource=Array.isArray(previous?.heat_sources)?previous.heat_sources.find((row:Record<string,unknown>)=>row.source_type==="board"||row.id==="board-total"):undefined;
 const next={...(previous ?? {}),contract:"spike/thermal/v1",ambient_temperature_c:parameters.ambientC,board_fallback_power_w:ids.size?0:parameters.powerW,
 thermal_elements:[...generated.map(row=>({...row,...(row.object_id&&ids.has(row.object_id)?{enabled:true}:{}),power_w:row.object_id&&ids.has(row.object_id)?powers[row.object_id]:0})),...other.map(row=>({...row,power_w:0}))],heat_sources:boardSource?[{...boardSource,power_w:ids.size?0:parameters.powerW}]:[],
 mode:parameters.durationS!==undefined?"transient":"steady_state",run:{...((previous?.run as Record<string,unknown>) ?? {}),...(parameters.durationS!==undefined?{end_time_s:parameters.durationS}:{})}} as Record<string,unknown>;
 for(const key of ["result","field_result","board_thermal_result","board_thermal_request","component_result","solver","thermal_screening"])delete next[key];
 return next;
}

/** Convert only reviewed temperature/time; thermal model values remain explicit. */
export function studioIntentFeedback(previous:import("./studioFeedback").StudioFeedbackSetup,parameters:Record<string,number>,steady:boolean):import("./studioFeedback").StudioFeedbackSetup{
 if(parameters.ambientC!==undefined&&(!Number.isFinite(parameters.ambientC)||parameters.ambientC<=-273.15))throw new Error("Review ambient temperature.");
 if(parameters.durationS!==undefined&&(!Number.isFinite(parameters.durationS)||parameters.durationS<=0))throw new Error("Review coupling duration.");
 return {...previous,...(parameters.ambientC!==undefined?{ambient:String(parameters.ambientC+273.15)}:{}),...(parameters.durationS!==undefined?{stopTime:String(parameters.durationS),mode:"transient" as const}:steady?{mode:"steady_state" as const}:{}),bindings:previous.bindings.map(row=>({...row,confirmed:false,confirmation:undefined}))};
}
