// SPDX-License-Identifier: Apache-2.0
import { duplicateBoardInstance, removeBoardInstance, type BoardInstance } from "./assemblyBoardLifecycle";
import type { AssemblyPackageShapesIndex } from "./assemblyPackageShapes";
import type { AssemblyDesigns, AssemblyIr, AssemblyPart } from "./mcadAssembly";
export type OccurrenceTarget = { boardId: string } | { partId: string };
export type OccurrenceClipboard = { assemblyId: string; kind: "board"; row: BoardInstance } | { assemblyId: string; kind: "part"; row: AssemblyPart };
const identity = () => [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1];
function freeze<T>(value:T):T { if(value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; }
export function seedActiveBoard(design: Record<string, unknown> | null, name: string, existing: AssemblyIr | null = null) {
  if(design?.contract !== "spike/design-ir/v2" || typeof design.design_id !== "string") throw new Error("Reimport this board through the desktop importer to retain its canonical source before creating instances.");
  const assembly:AssemblyIr=existing ?? {contract:"spike/assembly-ir/v1",assembly_id:crypto.randomUUID(),name:"Assembly",harnesses:[],connector_mappings:[],rigid_flex_links:[],extensions:{},metadata:{},frame:{frame_id:"assembly",parent_frame_id:"",units:"mm",handedness:"right",transform:identity()},boards:[],parts:[]};
  const id=`board-${crypto.randomUUID()}`;
  const row:BoardInstance={id,name,source_id:"",extensions:{},design_id:design.design_id,frame:{frame_id:`${id}-frame`,parent_frame_id:assembly.frame?.frame_id || "assembly",...{units:"mm",handedness:"right"},transform:identity()}};
  const designs:AssemblyDesigns={contract:"spike/assembly-designs/v1",active_design_id:design.design_id,designs:[structuredClone(design) as AssemblyDesigns["designs"][number]]};
  return {assembly:{...assembly,boards:[...assembly.boards,row]},designs,target:{boardId:id} as OccurrenceTarget};
}
export function captureOccurrence(assembly:AssemblyIr,target:OccurrenceTarget):OccurrenceClipboard {
  if("boardId" in target) {
    const row=assembly.boards.find(row=>row.id===target.boardId) as BoardInstance|undefined;
    if(!row?.frame || !row.design_id) throw new Error("Select an existing board instance.");
    return freeze({assemblyId:assembly.assembly_id,kind:"board",row:structuredClone(row)});
  }
  const row=assembly.parts.find(row=>row.id===target.partId);
  if(!row) throw new Error("Select an existing mechanical object.");
  return freeze({assemblyId:assembly.assembly_id,kind:"part",row:structuredClone(row)});
}
export function pasteOccurrence(assembly:AssemblyIr,designs:AssemblyDesigns|null,payload:OccurrenceClipboard,id:string,mode:"instance"|"copy"="instance") {
  if(payload.assemblyId!==assembly.assembly_id) throw new Error("Copy an occurrence from this project first.");
  if(!id || id.includes(":") || [...assembly.boards,...assembly.parts].some(row=>row.id===id || (row.frame as {frame_id?:string})?.frame_id===`${id}-frame`)) throw new Error("A unique occurrence and frame identity is required.");
  const frames=new Set([assembly.frame?.frame_id || "assembly",...assembly.boards.map(row=>(row.frame as {frame_id?:string})?.frame_id),...assembly.parts.map(row=>row.frame.frame_id)]);
  if(!frames.has(payload.row.frame.parent_frame_id)) throw new Error("The original parent frame is gone. Restore it before pasting this occurrence.");
  if(payload.kind==="board") {
    const source=designs?.designs.find(row=>row.design_id===payload.row.design_id);
    if(!source) throw new Error("The retained source design is unavailable.");
    let nextDesigns=designs!;
    let row=duplicateBoardInstance(assembly,designs,payload.row,id);
    // New occurrences inherit geometry identity, not old simulation/contact/display bindings.
    row={id:row.id,name:row.name,source_id:String(payload.row.source_id??""),extensions:{},design_id:row.design_id,frame:row.frame};
    if(mode==="copy") {
      if(nextDesigns.designs.length>=30) throw new Error("A project supports up to 30 retained designs.");
      const designId=`design-${id}`;
      if(nextDesigns.designs.some(item=>item.design_id===designId)) throw new Error("The copy design identity already exists.");
      nextDesigns={...nextDesigns,designs:[...nextDesigns.designs,{...structuredClone(source),design_id:designId,name:`${source.name || "Board"} copy`}]};
      row={...row,design_id:designId};
    }
    return {assembly:{...assembly,boards:[...assembly.boards,row]},designs:nextDesigns,occurrenceId:id,kind:"board" as const};
  }
  if(assembly.parts.length>=100) throw new Error("This assembly has reached the mechanical object limit.");
  const source=payload.row;
  const used=new Set(assembly.parts.map(row=>row.name)); let name=`${source.name} copy`,suffix=2;
  while(used.has(name)) name=`${source.name} copy ${suffix++}`;
  const transform=[...source.frame.transform];
  transform[3]+=30*(assembly.parts.filter(row=>row.frame.parent_frame_id===source.frame.parent_frame_id).length+1);
  const row:AssemblyPart={id,name,source_id:source.source_id,part_type:source.part_type,model_id:source.model_id,material_id:source.material_id,frame:{...structuredClone(source.frame),frame_id:`${id}-frame`,transform},extensions:source.extensions?.["spike.mcad.tessellation"]?{"spike.mcad.tessellation":structuredClone(source.extensions["spike.mcad.tessellation"])}:{}};
  return {assembly:{...assembly,parts:[...assembly.parts,row]},designs,occurrenceId:id,kind:"part" as const};
}
export function removeOccurrence(assembly:AssemblyIr,target:OccurrenceTarget) {
  const row="boardId" in target ? assembly.boards.find(row=>row.id===target.boardId) : assembly.parts.find(row=>row.id===target.partId);
  if(!row) throw new Error("The selected occurrence no longer exists.");
  if("boardId" in target && assembly.boards.length<=1) throw new Error("Keep at least one board instance; hide it instead, or create another instance first.");
  const frame=(row.frame as {frame_id:string}).frame_id;
  // Unknown assembly relationships are not silently broken by an object delete.
  const refers=(value:unknown):boolean => typeof value==="string" ? value===row.id || value===frame || value.startsWith(`${row.id}::`) : Array.isArray(value) ? value.some(refers) : Boolean(value && typeof value==="object" && Object.values(value).some(refers));
  for(const [key,value] of Object.entries(assembly)) {
    if(["boards","parts","harnesses","connector_mappings","rigid_flex_links","thermal_contacts","electrical_bonds"].includes(key)) continue;
    if(refers(value)) throw new Error(`Review assembly ${key} references before removing this occurrence.`);
  }
  if("partId" in target && [assembly.harnesses,assembly.connector_mappings,assembly.rigid_flex_links].some(refers)) throw new Error("Review assembly links referencing this mechanical object before removing it.");
  if([...assembly.parts,...assembly.boards].some(item=>(item.frame as {parent_frame_id?:string})?.parent_frame_id===frame)) throw new Error("Reparent this occurrence's child objects before removing it.");
  if((assembly.thermal_contacts?.length ?? 0) || (assembly.electrical_bonds?.length ?? 0)) throw new Error("Review and remove thermal contacts and electrical bonds in the assembly editor before deleting occurrences.");
  if("boardId" in target) return removeBoardInstance(assembly,target.boardId);
  return {assembly:{...assembly,parts:assembly.parts.filter(part=>part.id!==target.partId)},removedLinks:0};
}

/** Reconcile occurrence-owned exact shape setup atomically with a deletion.
 * New visual instances deliberately do not inherit occurrence-bound topology/contacts.
 */
export function reconcileOccurrenceShapes(index:AssemblyPackageShapesIndex|null,assembly:AssemblyIr):AssemblyPackageShapesIndex|null {
  if(!index) return null;
  if(index.assembly_id!==assembly.assembly_id) throw new Error("Package shapes belong to a different assembly.");
  const parts=new Set(assembly.parts.map(part=>part.id));
  const removed=new Set(index.shapes.filter(shape=>!parts.has(shape.part_id)).map(shape=>shape.part_id));
  if(!removed.size)return index;
  return {...index,shapes:index.shapes.filter(shape=>parts.has(shape.part_id)),constraints:index.constraints.filter(row=>!row.references.some(ref=>removed.has(ref.part_id))),thermal_contact_bindings:index.thermal_contact_bindings.filter(row=>!removed.has(row.endpoint_a.part_id)&&!removed.has(row.endpoint_b.part_id)),electrical_bond_bindings:index.electrical_bond_bindings.filter(row=>!removed.has(row.endpoint_a.part_id)&&!removed.has(row.endpoint_b.part_id))};
}
