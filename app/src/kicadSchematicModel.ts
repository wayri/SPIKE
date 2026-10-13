// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard } from "./boardParser";
export type SchematicPickBox = {x:number;y:number;width:number;height:number;quality:string;units?:string};
export type SchematicSymbol = { id: string; reference: string; value: string; page_id: string; source_uuid: string; sheet_path: string; source_file: string; position_mm?: {x:number;y:number}; hit_box_mm?: SchematicPickBox; position?: {x:number;y:number;units:string}; hit_box?: SchematicPickBox; nets: string[]; pins: {number:string;uuid:string}[] };
export type SchematicNet = {code:string;name:string;nodes:{reference:string;pin:string;symbol_ids?:string[]}[]};
export type SchematicDocument = {contract:"spike/kicad-schematic-view/v1";source:{file_name:string;sha256:string;format:string;units:string;presentation?:"original_schematic"|"generated_connectivity"};pages:{id:string;name:string;sheet_path:string;source_file:string;view_box:number[];svg:string}[];symbols:SchematicSymbol[];nets:SchematicNet[];source_files:unknown[];diagnostics:string[];limitations:string[]};
export type SchematicBinding = { boardSha256:string;boardName:string;designId:string|null;occurrenceId?:string|null };
export type SchematicSelection = {reference?:string;netCode?:string};
export type SchematicSnapshot = {document:SchematicDocument|null;linked:boolean;boardName:string;selected:SchematicSelection;busy:boolean;status:string};
export type SchematicAction = {type:"ready"|"closed"|"close"|"import"|"bind"|"cancel"|"select";sourceSha256?:string;symbolId?:string;netCode?:string;inputFormat?:"schematic"|"netlist"|"odb++";directory?:boolean;step?:string};
const record=(value:unknown):value is Record<string,any> => Boolean(value && typeof value === "object" && !Array.isArray(value));
const text=(value:unknown)=>typeof value==="string" && value.length<=2048;
export function normalizeSchematicDocument(value:unknown):SchematicDocument {
  if (!record(value)||value.contract!=="spike/kicad-schematic-view/v1"||!record(value.source)||!text(value.source.file_name)||!/^[a-f0-9]{64}$/.test(value.source.sha256)) throw new Error("Invalid saved schematic identity.");
  if (!Array.isArray(value.pages)||!value.pages.length||value.pages.length>128||!Array.isArray(value.symbols)||value.symbols.length>100000||!Array.isArray(value.nets)||value.nets.length>500000) throw new Error("Invalid schematic inventory.");
  let bytes=0;const pages=new Set<string>();
  for (const page of value.pages) {
    if(!record(page)||!text(page.id)||pages.has(page.id)||!text(page.name)||typeof page.svg!=="string"||!Array.isArray(page.view_box)||page.view_box.length!==4||!page.view_box.every(Number.isFinite)||page.view_box[2]<=0||page.view_box[3]<=0) throw new Error("Invalid schematic page.");
    bytes+=page.svg.length;pages.add(page.id);
    if(bytes>80*1024*1024||/<!\s*(?:DOCTYPE|ENTITY)|<(?:[\w-]+:)?(?:script|foreignObject|iframe|object|embed|image|a)\b|\bon[a-z]+\s*=|(?:href|xlink:href)\s*=\s*["'](?!#)|url\s*\(\s*(?!#)/i.test(page.svg)) throw new Error("Schematic SVG contains unsupported active or external content.");
  }
  const ids=new Set<string>();
  for(const symbol of value.symbols) {
    const generated=value.source.presentation==="generated_connectivity";
    const b=generated?symbol.hit_box:symbol.hit_box_mm,p=generated?symbol.position:symbol.position_mm;
    if(generated && (value.source.units!=="diagram" || p?.units!=="diagram" || b?.units!=="diagram")) throw new Error("Invalid connectivity diagram coordinates.");
    if(!text(symbol.id)||ids.has(symbol.id)||!text(symbol.reference)||!text(symbol.value)||!pages.has(symbol.page_id)||!record(p)||![p.x,p.y].every(Number.isFinite)||!record(b)||![b.x,b.y,b.width,b.height].every(Number.isFinite)||b.width<=0||b.height<=0||!Array.isArray(symbol.nets)||!symbol.nets.every(text)) throw new Error("Invalid schematic selection geometry.");
    ids.add(symbol.id);
  }
  const codes=new Set<string>();let nodes=0;
  for(const net of value.nets) {
    if(!text(net.code)||codes.has(net.code)||!text(net.name)||!Array.isArray(net.nodes)) throw new Error("Invalid schematic net identity.");
    codes.add(net.code);nodes+=net.nodes.length;
    if(nodes>500000||!net.nodes.every((node:any)=>record(node)&&text(node.reference)&&text(node.pin))) throw new Error("Invalid schematic pin connectivity.");
  }
  return value as SchematicDocument;
}
export function restoreSchematicWorkspace(value:unknown):{document:SchematicDocument|null;binding:SchematicBinding|null} {
  if(!record(value)) return {document:null,binding:null};
  try { const document=normalizeSchematicDocument(value.document);const b=value.binding;
    return {document,binding:record(b)&&/^[a-f0-9]{64}$/.test(b.boardSha256)&&text(b.boardName)&&(b.designId===null||text(b.designId))&&(b.occurrenceId===undefined||b.occurrenceId===null||text(b.occurrenceId))?b as SchematicBinding:null};
  } catch { return {document:null,binding:null}; }
}
/** Resolve a compiled schematic net through explicit component pin identities, never just a net label. */
export function boardNetForSchematic(net:SchematicNet,board:ParsedBoard):string|null {
  const found=new Set<string>(); const pins=new Map<string,Set<string>>();
  for(const pad of board.pads) if(pad.ref&&pad.net){const key=`${pad.ref}\0${pad.name}`;const values=pins.get(key)??new Set<string>();values.add(pad.net);pins.set(key,values);}
  for(const node of net.nodes) for(const name of pins.get(`${node.reference}\0${node.pin}`)??[]) found.add(name);
  return found.size===1?[...found][0]:null;
}
export function schematicSelectionForBoard(document:SchematicDocument,board:ParsedBoard,object:{ref?:string;net?:string}|null):SchematicSelection {
  if(!object)return {};
  const nets=object.net?document.nets.filter(net=>boardNetForSchematic(net,board)===object.net):[];
  return {reference:object.ref,netCode:nets.length===1?nets[0].code:undefined};
}
export async function schematicBoardDigest(source:string):Promise<string> {
  const bytes=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(source));return Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,"0")).join("");
}

export function schematicPickBox(document:SchematicDocument,symbol:SchematicSymbol):SchematicPickBox {return (document.source.presentation==="generated_connectivity"?symbol.hit_box:symbol.hit_box_mm)!;}
