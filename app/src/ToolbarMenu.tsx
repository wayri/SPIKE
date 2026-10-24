// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, type LucideIcon } from "./icons";
import ActionContextMenu, { type ContextAction } from "./ActionContextMenu";
/** Hover previews dismiss on boundary exit; click/keyboard explicitly pins. */
export default function ToolbarMenu({ label, icon: Icon, actions }: { label: string; icon: LucideIcon; actions: ContextAction[] }) {
 const [anchor,setAnchor]=useState<{x:number;y:number;pinned:boolean}|null>(null);
 const trigger=useRef<HTMLButtonElement>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null),latest=useRef(anchor);latest.current=anchor;
 const id=useId();
 const cancel=()=>{if(timer.current!==null)clearTimeout(timer.current);timer.current=null;};
 const dismiss=()=>{cancel();setAnchor(null);};
 const leave=()=>{cancel();if(!latest.current?.pinned)timer.current=setTimeout(()=>{if(!latest.current?.pinned)setAnchor(null);},120);};
 const open=(button:HTMLButtonElement,pinned:boolean)=>{cancel();const bounds=button.getBoundingClientRect();setAnchor(current=>current?.pinned&&!pinned?current:{x:bounds.left,y:bounds.bottom+4,pinned});};
 useEffect(()=>cancel,[]);
 return <><button ref={trigger} type="button" className="plain-btn toolbar-menu-trigger" aria-label={label} title={label} aria-haspopup="menu" aria-expanded={Boolean(anchor)} aria-controls={anchor?id:undefined}
 onMouseEnter={event=>open(event.currentTarget,false)} onMouseLeave={leave} onClick={event=>anchor?.pinned?dismiss():open(event.currentTarget,true)}
 onKeyDown={event=>{if(event.key==="ArrowDown"){event.preventDefault();event.stopPropagation();open(event.currentTarget,true);}}}><Icon size={15} aria-hidden="true"/><span>{label}</span><ChevronDown size={12} aria-hidden="true"/></button>
 {anchor&&<ActionContextMenu id={id} {...anchor} preview={!anchor.pinned} anchorElement={trigger.current} onPointerEnter={cancel} onPointerLeave={leave} title={label} actions={actions} onClose={dismiss}/>}</>;
}
