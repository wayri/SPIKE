// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import ActionContextMenu from "./ActionContextMenu";
import { ShowControlIcon, CloseControlIcon } from "./navigationIcons";
import { closeMinimizedTool, minimizedToolSnapshot, restoreMinimizedTool, subscribeMinimizedTools, type MinimizedToolItem } from "./minimizedTools";

/** A single icon restores hidden controls even when Clean mode hides the taskbar. */
export default function HiddenToolsMenu({items = [], onError}: {items?:readonly MinimizedToolItem[];onError:(message:string)=>void}) {
  const [registered,setRegistered]=useState(minimizedToolSnapshot);
  const [anchor,setAnchor]=useState<{x:number;y:number}|null>(null);
  useEffect(()=>subscribeMinimizedTools(setRegistered),[]);
  const merged=new Map(items.map(item=>[item.id,item]));
  registered.forEach(item=>merged.set(item.id,item));
  const invoke=async(item:MinimizedToolItem,close=false)=>{
    try {
      if(registered.some(entry=>entry.id===item.id)) {
        if(close) await closeMinimizedTool(item.id); else await restoreMinimizedTool(item.id);
      } else if(close) await item.close?.(); else await item.restore();
    } catch(error) {onError(`Could not ${close?"close":"show"} ${item.label}: ${String(error)}. Retry from Show hidden tools.`);}
  };
  return <>
    <button type="button" className="spike-control--icon" aria-label="Show hidden tools" title="Show hidden tools and controls" aria-haspopup="menu" aria-expanded={Boolean(anchor)} disabled={!merged.size} onClick={event=>{const bounds=event.currentTarget.getBoundingClientRect();setAnchor(anchor?null:{x:bounds.left,y:bounds.bottom+4});}}><ShowControlIcon size={15}/></button>
    {anchor&&<ActionContextMenu {...anchor} title="Hidden tools" onClose={()=>setAnchor(null)} actions={[...merged.values()].flatMap(item=>[
      {label:`Show ${item.label}`,icon:ShowControlIcon,run:()=>void invoke(item)},
      ...(item.close?[{label:`Close ${item.label}`,icon:CloseControlIcon,run:()=>void invoke(item,true)}]:[]),
    ])}/>}
  </>;
}
