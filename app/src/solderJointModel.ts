// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard, ParsedPad } from "./boardParser";
import type { BondRecord } from "./BondManager";
export type SolderJointVisual = { visible:boolean; style:"smd-fillet"|"through-hole"|"terminal"; heightMm:number; spreadMm:number; opacity:number };
export const DEFAULT_SOLDER_JOINT_VISUAL: SolderJointVisual = {visible:true,style:"smd-fillet",heightMm:.25,spreadMm:.15,opacity:1};
export const MAX_SOLDER_JOINTS = 2000;
export function normalizeSolderJointVisual(value:unknown):SolderJointVisual|null {
  if(!value||typeof value!=="object"||Array.isArray(value))return null;
  const row=value as Record<string,unknown>;
  if(typeof row.visible!=="boolean"||!["smd-fillet","through-hole","terminal"].includes(String(row.style)))return null;
  if(typeof row.heightMm!=="number"||!Number.isFinite(row.heightMm)||row.heightMm<.01||row.heightMm>20)return null;
  if(typeof row.spreadMm!=="number"||!Number.isFinite(row.spreadMm)||row.spreadMm<0||row.spreadMm>20)return null;
  if(typeof row.opacity!=="number"||!Number.isFinite(row.opacity)||row.opacity<.05||row.opacity>1)return null;
  return {visible:row.visible,style:row.style as SolderJointVisual["style"],heightMm:row.heightMm,spreadMm:row.spreadMm,opacity:row.opacity};
}
export type ResolvedSolderJoint={id:string;pad:ParsedPad;layer:string;side:1|-1;visual:SolderJointVisual};
/** No nearest-neighbor or cross-net inference. Legacy records are single-board only. */
export function resolveSolderJoints(board:ParsedBoard,bonds:readonly BondRecord[],occurrenceId?:string,multiBoard=false):{joints:ResolvedSolderJoint[];issues:string[]} {
  const joints:ResolvedSolderJoint[]=[],issues:string[]=[];
  const padsById=new Map<string,ParsedPad[]>();
  for(const pad of board.pads){const matches=padsById.get(pad.id)??[];matches.push(pad);padsById.set(pad.id,matches);}
  for(const bond of bonds) {
    if(!bond.enabled||bond.status==="disabled"||!bond.solderVisual)continue;
    if(bond.boardInstanceId?bond.boardInstanceId!==occurrenceId:multiBoard)continue;
    const visual=normalizeSolderJointVisual(bond.solderVisual);
    if(!visual){issues.push(`${bond.id}: invalid solder dimensions or opacity`);continue;}
    if(!visual.visible)continue;
    const candidates=bond.padId?padsById.get(bond.padId)??[]:board.pads.filter(pad=>pad.ref===bond.reference&&pad.name===bond.pad);
    const pad=candidates.length===1?candidates[0]:null;
    if(!pad||pad.ref!==bond.reference||pad.name!==bond.pad||(pad.net??"")!==bond.net){issues.push(`${bond.id}: an unambiguous owned pad on the declared net is required`);continue;}
    if(![...pad.at,pad.width,pad.height,pad.rotation,pad.drill].every(Number.isFinite)||pad.width<=0||pad.height<=0||pad.width>1000||pad.height>1000){issues.push(`${bond.id}: invalid pad geometry`);continue;}
    const drillX=pad.drill_size?.[0]??pad.drill,drillY=pad.drill_size?.[1]??pad.drill;
    if(![drillX,drillY].every(Number.isFinite)||drillX<0||drillY<0||(pad.drill>0&&(drillX+.08>pad.width+2*visual.spreadMm||drillY+.08>pad.height+2*visual.spreadMm))){issues.push(`${bond.id}: drill dimensions leave no supported solder collar`);continue;}
    if(visual.style==="through-hole"&&(!(pad.drill>0)||pad.plated===false||pad.type==="np_thru_hole"||pad.pad_kind==="np_thru_hole")){issues.push(`${bond.id}: through-hole solder requires a plated drilled pad`);continue;}
    const copper=(Array.isArray(bond.connectedLayers)&&bond.connectedLayers.length?bond.connectedLayers:pad.layers).filter(layer=>layer==="F.Cu"||layer==="B.Cu");
    const declared=pad.layers.includes("*.Cu")?["F.Cu","B.Cu"]:pad.layers;
    const surfaces=[...new Set(copper)].filter(layer=>declared.includes(layer));
    if(!surfaces.length){issues.push(`${bond.id}: no matching exposed copper surface`);continue;}
    for(const layer of surfaces){if(joints.length>=MAX_SOLDER_JOINTS){issues.push(`Solder display budget reached (${MAX_SOLDER_JOINTS}); remaining joints omitted`);return {joints,issues};}joints.push({id:`${bond.id}:${layer}`,pad,layer,side:layer==="B.Cu"?-1:1,visual});}
  }
  return {joints,issues};
}
