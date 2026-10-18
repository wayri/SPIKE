// SPDX-License-Identifier: Apache-2.0
import { classifyOpenSource, type OpenSourceKind } from "./importSourceRouting";
export const MAX_DROP_FILES = 32;
export const MAX_BROWSER_DROP_BYTES = 64 * 1024 * 1024;
export type NativeDropFile = {path:string;fileName:string;isDirectory:boolean};
export type DroppedImport = {id:string;fileName:string;kind:OpenSourceKind;native?:NativeDropFile;file?:File;reason?:string};
export function nativeDropItems(payload:unknown): {items:DroppedImport[];rejected:string[]} {
  if(!payload || typeof payload!=="object")throw Error("Invalid desktop drop event.");
  const data=payload as {files?:unknown;rejected?:unknown};
  if(!Array.isArray(data.files)||data.files.length>MAX_DROP_FILES)throw Error(`Drop at most ${MAX_DROP_FILES} sources at once.`);
  const items:DroppedImport[]=data.files.map(value=>{
    const file=value as NativeDropFile;
    if(!file||typeof file.path!=="string"||!file.path||typeof file.fileName!=="string"||!file.fileName||typeof file.isDirectory!=="boolean")throw Error("Invalid dropped source metadata.");
    const kind=file.isDirectory?"odb++":classifyOpenSource(file.fileName);
    return {id:file.path,fileName:file.fileName,kind,native:file,...(kind==="unknown"&&!file.fileName.toLowerCase().endsWith(".json")?{reason:"Unsupported source. Drop a KiCad board, ODB++ job, STEP, GLB or glTF model."}:{})};
  });
  return {items,rejected:Array.isArray(data.rejected)?data.rejected.filter((value):value is string=>typeof value==="string"):[]};
}
export function browserDropItems(files:readonly File[]):DroppedImport[] {
  if(files.length>MAX_DROP_FILES)throw Error(`Drop at most ${MAX_DROP_FILES} sources at once.`);
  return files.map(file=>{
    const kind=classifyOpenSource(file.name);
    const supported=["kicad","normalized","project","results"].includes(kind)||(kind==="unknown"&&file.name.toLowerCase().endsWith(".json"));
    const reason=file.size>MAX_BROWSER_DROP_BYTES?"Browser import is limited to 64 MiB per file. Use the desktop app for larger sources.":!supported?(["odb++","mcad","ipc2581","harness"].includes(kind)?"Open this source in the SPIKE desktop app to inspect and import it.":"Unsupported file or folder. Drop a KiCad .kicad_pcb board or SPIKE project."):undefined;
    return {id:`browser:${file.name}:${file.size}:${file.lastModified}`,fileName:file.name,kind,file,reason};
  });
}
export function mergeDroppedImports(current:readonly DroppedImport[],incoming:readonly DroppedImport[]):DroppedImport[] {
  const merged=new Map(current.map(item=>[item.id,item]));incoming.forEach(item=>merged.set(item.id,item));
  if(merged.size>MAX_DROP_FILES)throw Error(`The review queue is full. Review or remove files before dropping more (limit ${MAX_DROP_FILES}).`);
  return [...merged.values()];
}
