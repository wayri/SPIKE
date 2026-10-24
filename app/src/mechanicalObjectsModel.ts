// SPDX-License-Identifier: Apache-2.0
import {partVisualSettings,resolveFrameToAssembly,type AssemblyIr,type AssemblyPart,type AssemblyPartVisual} from "./mcadAssembly";
export type MechanicalVisuals=Record<string,AssemblyPartVisual>;
export function normalizeMechanicalVisuals(value:unknown):MechanicalVisuals{
 if(!value||typeof value!=="object")return {};
 if(Array.isArray(value))return normalizeMechanicalVisuals(Object.fromEntries(value.flatMap(item=>item&&typeof item==="object"&&typeof item.id==="string"?[[item.id,item]]:[])));
 return Object.fromEntries(Object.entries(value).flatMap(([id,item])=>{
 if(!item||typeof item!=="object"||Array.isArray(item))return [];
 const raw=item as Record<string,unknown>;
 return typeof raw.visible==="boolean"&&typeof raw.opacity==="number"&&Number.isFinite(raw.opacity)?[[id,{visible:raw.visible,opacity:Math.max(0,Math.min(1,raw.opacity))}]]:[];
 }));
}
export function mechanicalVisual(part:AssemblyPart,overrides:MechanicalVisuals):AssemblyPartVisual{return overrides[part.id]??partVisualSettings(part);}
/** The selected occurrence origin is an anchor, not a picked surface or bounding-box dimension. */
export function mechanicalOrigin(assembly:AssemblyIr,part:AssemblyPart):[number,number,number]|undefined{
 const matrix=resolveFrameToAssembly(assembly,part.frame);
 return matrix&&[matrix[3],matrix[7],matrix[11]].every(Number.isFinite)?[matrix[3],matrix[7],matrix[11]]:undefined;
}
