// SPDX-License-Identifier: Apache-2.0
import {useState} from "react";
import ActionContextMenu from "./ActionContextMenu";
import { Boxes, Eye, Layers3, Link2, MoreHorizontal, Move, Network, RotateCw } from "./icons";
import "./AssemblyQuickBar.css";
import type { VirtualBoardVisual } from "./harnessVisualization";
type Props = { compact?: boolean; boards: readonly VirtualBoardVisual[]; selectedId: string | null; visibility: Record<string, boolean>; expanded: boolean; moveMode?: "translate" | "rotate" | null; onMoveMode?: (mode: "translate" | "rotate") => void;
  onSelect: (boardId: string) => void; onVisibility: (boardId: string, visible: boolean) => void; onExpand: () => void;
  onWorkspace: () => void; onLayers: () => void; onNets: () => void; onLinks: () => void };
export default function AssemblyQuickBar(props: Props) {
  const [more,setMore]=useState<{x:number;y:number}|null>(null);
  const selected = props.boards.find(board => board.id === props.selectedId);
  if(props.compact) return <section className="assembly-quick-bar assembly-quick-bar--compact" aria-label="Multi-board viewport controls">
    <Boxes size={14} aria-label={`${props.boards.length} board occurrences`}/>
    <select aria-label="Selected assembly board" title={selected?.name??"Select an assembly board"} value={selected?.id??""} onChange={event=>props.onSelect(event.target.value)}><option value="">Select board...</option>{props.boards.map(board=><option key={board.id} value={board.id}>{board.name}</option>)}</select>
    <button type="button" className="spike-control--icon" title="Move selected board" aria-label="Move selected board" disabled={!selected} aria-pressed={props.moveMode==="translate"} onClick={()=>props.onMoveMode?.("translate")}><Move size={14}/></button>
    <button type="button" className="spike-control--icon" title="Rotate selected board" aria-label="Rotate selected board" disabled={!selected} aria-pressed={props.moveMode==="rotate"} onClick={()=>props.onMoveMode?.("rotate")}><RotateCw size={14}/></button>
    <button type="button" className="spike-control--icon" title="Assembly actions" aria-label="Assembly actions" aria-haspopup="menu" aria-expanded={Boolean(more)} onClick={event=>{const rect=event.currentTarget.getBoundingClientRect();setMore(more?null:{x:rect.left,y:rect.bottom+4});}}><MoreHorizontal size={15}/></button>
    {more&&<ActionContextMenu {...more} title="Assembly actions" onClose={()=>setMore(null)} actions={[
      {label:selected&&props.visibility[selected.id]===false?"Show board":"Hide board",icon:Eye,disabled:!selected,run:()=>selected&&props.onVisibility(selected.id,props.visibility[selected.id]===false)},
      {label:"Placement settings",icon:Move,run:props.onExpand},{label:"Layers",icon:Layers3,run:props.onLayers},{label:"Nets",icon:Network,run:props.onNets},{label:"Connector links",icon:Link2,run:props.onLinks},{label:"Assembly workspace",icon:Boxes,run:props.onWorkspace}
    ]}/>}

  </section>;
  return <section className="assembly-quick-bar" aria-label="Multi-board viewport controls">
    <b title={`${props.boards.length} board occurrences`}>ASSEMBLY · {props.boards.length}</b>
    <select aria-label="Selected assembly board" value={selected?.id ?? ""} onChange={event => props.onSelect(event.target.value)}><option value="">Select a board…</option>{props.boards.map(board => <option key={board.id} value={board.id}>{board.name} · {board.id}</option>)}</select>
    <button type="button" disabled={!selected} onClick={() => selected && props.onVisibility(selected.id, props.visibility[selected.id] === false)}>{selected && props.visibility[selected.id] === false ? "Show board" : "Hide board"}</button>
    <button type="button" disabled={!selected} aria-pressed={props.moveMode === "translate"} onClick={() => props.onMoveMode?.("translate")}>Move</button>
    <button type="button" disabled={!selected} aria-pressed={props.moveMode === "rotate"} onClick={() => props.onMoveMode?.("rotate")}>Rotate</button>
    <button type="button" aria-pressed={props.expanded} onClick={props.onExpand}>Placement</button>
    <button type="button" onClick={props.onLayers}>Layers</button><button type="button" onClick={props.onNets}>Nets</button><button type="button" onClick={props.onLinks}>Links</button><button type="button" onClick={props.onWorkspace}>Workspace</button>
  </section>;
}
