// SPDX-License-Identifier: Apache-2.0
import type {ParsedBoard} from "./boardParser";
import type {BoardObject} from "./BoardViewport";
import type {SolverResultBundle} from "./analysisResults";
import {availableViewportResultModes} from "./viewportContext";
export function viewportSmartContext(input:{object:BoardObject|null;board:ParsedBoard|null;boardName:string;workspace:string;mode:string;solver:string;activeDesignId:string|null;occurrences:readonly {id?:unknown;designId?:unknown}[];result:SolverResultBundle|null}) {
 const {object,board,result}=input;
 const occurrence=object?.occurrenceId?input.occurrences.find(item=>item.id===object.occurrenceId):null;
 const sameDesign=Boolean(board&&(!object?.occurrenceId||occurrence?.designId===input.activeDesignId));
 const inventory=board&&object?object.type==="trace"?board.tracks:object.type==="pad"?board.pads:object.type==="via"?board.vias:object.type==="zone"?board.zones:object.type==="component"?board.components:[]:[];
 const knownObject=Boolean(object&&(object.type==="terminal"||inventory.some(item=>item.id===object.id))&&!object.assemblyPartId);
 const ownsObject=Boolean(sameDesign&&(!object||knownObject));
 const hasNet=Boolean(ownsObject&&object?.net&&Object.values(board!.nets).includes(object.net));
 const resultScoped=Boolean(result&&ownsObject&&(input.occurrences.length<=1||object?.occurrenceId&&result.provenance.board_occurrence_id===object.occurrenceId));
 const summary=[`${input.workspace} / ${input.mode}`,`Board: ${object?.occurrenceId??input.boardName}`];
 if(object)summary.push(`${object.type}${object.ref?` / ${object.ref}`:""}${object.layer?` / ${object.layer}`:""}`);
 if(object?.net)summary.push(`Net: ${object.net}`);
 if(hasNet&&board){const tracks=board.tracks.filter(track=>track.net===object!.net);const length=tracks.reduce((sum,track)=>sum+Math.hypot(track.end[0]-track.start[0],track.end[1]-track.start[1]),0);summary.push(`${tracks.length} tracks / ${length.toFixed(2)} mm / ${board.pads.filter(p=>p.net===object!.net).length} pads / ${board.vias.filter(v=>v.net===object!.net).length} vias`);}
 summary.push(resultScoped?`Result: ${result!.mode} / ${result!.status} / ${result!.model_status}`:result?"Result not bound to this board occurrence":"No saved simulation result");
 if(resultScoped&&result?.time_series?.frames?.length)summary.push(`${result.time_series.frames.length} saved transient frames (s)`);
 summary.push(`Solver selection: ${input.solver}`);
 return {summary,ownsObject,hasNet,resultScoped,modes:resultScoped?availableViewportResultModes(result):[],boardReason:!board?"Load a board first":!sameDesign?"Activate the clicked board design before configuring its analysis":!ownsObject?"This object is not in the active board source":undefined,netReason:!hasNet?"A net with verified identity on the active board is required":undefined,resultReason:!result?"Run or load a saved result first":!resultScoped?"The result is not bound to the clicked board occurrence":undefined};
}

/** Bounded object facts and exact saved samples, evaluated only on an explicit export. */
export function viewportObjectSnapshot(object:BoardObject|null,board:ParsedBoard|null,result:SolverResultBundle|null,admitted:boolean) {
 if(!object||!board||!admitted)return {geometry:null,saved_base_samples:[]};
 const track=object.type==="trace"?board.tracks.find(item=>item.id===object.id):null;
 const pad=object.type==="pad"?board.pads.find(item=>item.id===object.id):null;
 const via=object.type==="via"?board.vias.find(item=>item.id===object.id):null;
 const component=object.type==="component"?board.components.find(item=>item.id===object.id):null;
 const zone=object.type==="zone"?board.zones.find(item=>item.id===object.id):null;
 const geometry=track?{units:"mm",start:track.start,end:track.end,width:track.width,length:Math.hypot(track.end[0]-track.start[0],track.end[1]-track.start[1])}:pad?{units:"mm",position:pad.at,pin:pad.name,ref:pad.ref,width:pad.width,height:pad.height,drill:pad.drill,layers:pad.layers}:via?{units:"mm",position:via.at,size:via.size,drill:via.drill,layers:via.layers}:component?{units:"mm",position:component.at,ref:component.ref,value:component.value,library:component.library,width:component.width,height:component.height,rotation_deg:component.rotation,model_paths:component.modelPaths??(component.modelPath?[component.modelPath]:[])}:zone?{units:"mm",vertices:zone.points.length,holes:zone.holes?.length??0}:null;
 const units:Record<string,string>={voltage_v:"V",voltage_drop_v:"V",current_a:"A",current_density_a_mm2:"A/mm2",power_loss_w:"W",via_current_density_a_mm2:"A/mm2",operating_point_impedance_ohm:"ohm"};
 const saved_base_samples=Object.entries(result?.scalar_fields??{}).flatMap(([field,samples])=>{const sample=samples.find(item=>item.element_id===object.id&&(!object.layer||item.layer===object.layer)&&(!object.net||item.net===object.net)&&Number.isFinite(item.value));return sample?[{quantity:field,value:sample.value,unit:units[field],position_mm:[sample.x_mm,sample.y_mm,sample.z_mm??null],sampling:"Exact saved base-field element; not a playback-frame interpolation"}]:[];});
 return {geometry,saved_base_samples};
}
