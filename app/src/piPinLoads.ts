// SPDX-License-Identifier: Apache-2.0
import type { ParsedBoard, ParsedPad } from "./boardParser";

export type PiPinLoadPolicy = "equal" | "weights";
export type PiPinLoad = { padId: string; currentA: number };
export type PiComponentLoadSelection = {
  componentRef: string;
  totalCurrentA: number;
  pins: PiPinLoad[];
  policy: PiPinLoadPolicy;
};

type PadIndex = { pads: ParsedBoard["pads"]; components: ParsedBoard["components"]; nets: ParsedBoard["nets"]; names:Set<string>; byRef:Map<string,Map<string,ParsedPad[]>> };
const padIndexes=new WeakMap<ParsedBoard,PadIndex>();
/** Parsed board arrays are immutable workspace snapshots; index each snapshot once. */
function padIndex(board:ParsedBoard):PadIndex {
 const cached=padIndexes.get(board);
 if(cached?.pads===board.pads&&cached.components===board.components&&cached.nets===board.nets)return cached;
 const names=new Set(Object.values(board.nets));
 const refs=new Set(board.components.map(component=>component.ref));
 const byRef=new Map<string,Map<string,ParsedPad[]>>();
 for(const pad of board.pads){
  if(!pad.ref||!refs.has(pad.ref)||!pad.net||[pad.type,pad.pad_kind].some(kind=>["np_thru_hole","npth"].includes(kind?.toLowerCase() ?? ""))||!(pad.layers.length?pad.layers:[pad.layer]).some(layer=>layer.endsWith(".Cu")))continue;
  const rail=names.has(pad.net)?pad.net:board.nets[pad.net] ?? pad.net;
  const rails=byRef.get(pad.ref) ?? new Map<string,ParsedPad[]>();
  if(!byRef.has(pad.ref))byRef.set(pad.ref,rails);
  const pads=rails.get(rail) ?? [];pads.push(pad);rails.set(rail,pads);
 }
 const index={pads:board.pads,components:board.components,nets:board.nets,names,byRef};padIndexes.set(board,index);return index;
}
/** Connectivity candidates only: PCB data cannot establish IC pin functions. */
export function eligibleComponentSupplyPads(board: ParsedBoard, ref: string, net: string): ParsedPad[] {
 if(!net||!ref)return [];
 const index=padIndex(board),rail=index.names.has(net)?net:board.nets[net] ?? net;
 return index.byRef.get(ref)?.get(rail)?.slice() ?? [];
}

/** Editable input allocation, not a prediction of internal IC current sharing. */
export function allocatePiPinLoads(
  totalCurrentA: number,
  pins: { padId: string; weight?: number }[],
  policy: PiPinLoadPolicy = "equal",
): PiPinLoad[] {
  if (!Number.isFinite(totalCurrentA) || totalCurrentA < 0) throw new Error("Total current must be finite and nonnegative.");
  if (policy !== "equal" && policy !== "weights") throw new Error("Unknown pin allocation policy.");
  if (!pins.length) throw new Error("Enable at least one supply pin.");
  const seen = new Set<string>();
  const weights = pins.map(pin => {
    if (!pin.padId || seen.has(pin.padId)) throw new Error("Supply pad IDs must be nonempty and unique.");
    seen.add(pin.padId);
    const weight = policy === "equal" ? 1 : pin.weight;
    if (weight === undefined || !Number.isFinite(weight) || weight < 0) throw new Error("Pin weights must be finite and nonnegative.");
    return weight;
  });
  const sum = weights.reduce((value, weight) => value + weight, 0);
  if (!Number.isFinite(sum)) throw new Error("The sum of pin weights exceeds the supported numeric range.");
  if (!(sum > 0)) throw new Error("At least one pin weight must be positive.");
  let lastPositive = weights.length - 1;
  while (weights[lastPositive] === 0) lastPositive -= 1;
  let assigned = 0;
  return pins.map((pin, index) => {
    const remaining = Math.max(0, totalCurrentA - assigned);
    const currentA = index === lastPositive ? remaining : Math.min(remaining, totalCurrentA * (weights[index] / sum));
    assigned += currentA;
    return { padId: pin.padId, currentA };
  });
}

