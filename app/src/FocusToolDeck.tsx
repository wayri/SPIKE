import FloatingPanel, { FloatingPanelControls, useFloatingPanel } from "./FloatingPanel";
// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useEffect, useLayoutEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { GripVertical, Maximize2, Minimize2, PanelRightClose } from "./icons";

export const FocusDockContext = createContext<{ embedded: boolean; hide: () => void } | null>(null);
const useFocusLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/** Opening a tool activates its presentation without discarding another tool's draft. */
export function useFocusToolState<T>(id: string, initial: T | (() => T), activate: Dispatch<SetStateAction<string | null>>) {
  const [value, setValue] = useState<T>(initial);
  const update = useCallback((next: SetStateAction<T>) => {
    setValue(next);
    if (typeof next === "function" || Boolean(next)) activate(id);
  }, [activate, id]);
  return [value, update] as const;
}

export type FocusToolPanel = {
  id: string;
  aliases?: readonly string[];
  title: string;
  open: boolean;
  content: ReactNode;
};

export function activeFocusPanel(panels: readonly FocusToolPanel[], id: string | null): FocusToolPanel | undefined {
  return panels.find(panel => panel.open && (panel.id === id || panel.aliases?.includes(id ?? "")));
}

export const FOCUS_PANEL_DEFAULT_WIDTH = 360;
export const FOCUS_PANEL_MIN_WIDTH = 280;
export const FOCUS_PANEL_MAX_WIDTH = 720;
export function normalizeFocusPanelWidth(value: unknown): number {
  const width = typeof value === "number" ? value : Number(value);
  return Number.isFinite(width)
    ? Math.round(Math.max(FOCUS_PANEL_MIN_WIDTH, Math.min(FOCUS_PANEL_MAX_WIDTH, width)))
    : FOCUS_PANEL_DEFAULT_WIDTH;
}

function ToolPresentation({panel,active,expanded,setExpanded,hide}: {panel:FocusToolPanel;active:boolean;expanded:boolean;setExpanded:Dispatch<SetStateAction<boolean>>;hide:()=>void}) {
  const floating=useFloatingPanel();
  const container=useRef<HTMLElement>(null);
  useFocusLayoutEffect(()=>{
    const root=container.current;if(!root)return;
    const adapt=()=>{
      root.querySelectorAll<HTMLElement>('[aria-modal="true"]').forEach(dialog=>{const ancestor=dialog.parentElement?.closest('[role="dialog"]');if(!ancestor || !root.contains(ancestor))dialog.setAttribute("aria-modal","false");});
      root.querySelectorAll<HTMLElement>('.focus-tool-content header > button').forEach(button=>{
        const dialog=button.closest('[role="dialog"]'),outer=dialog?.parentElement?.closest('[role="dialog"]');
        if(outer && root.contains(outer))return;
        const heading=button.parentElement?.querySelector<HTMLElement>('h1,h2,h3,strong,b');
        if(heading?.textContent?.trim().toLowerCase()===panel.title.trim().toLowerCase())heading.dataset.spikeDuplicateTitle="true";
        const label=button.getAttribute("aria-label")??button.getAttribute("title")??"";
        if(/^close\b/i.test(label) || button.querySelector('svg.lucide-x,svg.lucide-circle-x'))button.dataset.spikeInnerDismiss="true";
      });
    };
    adapt();const observer=new MutationObserver(adapt);observer.observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:["aria-modal"]});return()=>observer.disconnect();
  },[]);
  return <section ref={container} className="focus-tool-deck" aria-label={panel.title}>
    <header className="focus-tool-heading" onPointerDown={floating?.onHeaderPointerDown} title="Drag this header outside the main window to detach"><h2>{panel.title}</h2><FloatingPanelControls/>{!floating?.detached&&<><button type="button" className="spike-control--compact" onClick={()=>setExpanded(value=>!value)} aria-label={expanded?"Restore tool panel":"Expand tool panel"} aria-pressed={expanded} title={expanded?"Restore viewport beside this tool":"Expand tool to workspace"}>{expanded?<Minimize2 size={14}/>:<Maximize2 size={14}/>}<span>{expanded?"Restore":"Expand"}</span></button><button type="button" className="spike-control--compact" onClick={hide} aria-label="Hide panel" title="Hide panel and keep its current inputs"><PanelRightClose size={14}/><span>Hide</span></button></>}</header>
    <FocusDockContext.Provider value={{embedded:true,hide}}><div className="focus-tool-content" style={{zoom:floating?.scale ?? 1}}>{panel.content}</div></FocusDockContext.Provider>
  </section>;
}
export default function FocusToolDeck({panels,activeId,commandsOpen,onActivate}: {panels:readonly FocusToolPanel[];activeId:string|null;commandsOpen:boolean;onActivate:Dispatch<SetStateAction<string|null>>}) {
  const active=commandsOpen?undefined:activeFocusPanel(panels,activeId);
  const [expanded,setExpanded]=useState(false),[notice,setNotice]=useState("");
  const container=useRef<HTMLElement>(null),width=useRef(FOCUS_PANEL_DEFAULT_WIDTH);
  useEffect(()=>{try{const saved=localStorage.getItem("spike.focus.panel.width");if(saved!==null)width.current=normalizeFocusPanelWidth(saved);}catch{/* Optional preference. */}container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-panel-width",`${width.current}px`);},[]);
  useEffect(()=>{setExpanded(false);},[active?.id]);
  useEffect(()=>{const workspace=container.current?.closest<HTMLElement>(".workspace");workspace?.classList.toggle("focus-panel-expanded",expanded&&Boolean(active));return()=>workspace?.classList.remove("focus-panel-expanded");},[expanded,active?.id]);
  const hide=()=>{onActivate(null);document.getElementById("focus-menu-toggle")?.focus();};
  const resize=(next:number)=>{width.current=normalizeFocusPanelWidth(next);container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-panel-width",`${width.current}px`);try{localStorage.setItem("spike.focus.panel.width",String(width.current));}catch{/* Optional preference. */}};
  return <aside ref={container} className="focus-tool-deck-host" hidden={!active} aria-label={active?.title??"Tool panel"}>
    {notice&&<p role="alert">{notice}</p>}
    {panels.filter(panel=>panel.open).map(panel=><FloatingPanel key={panel.id} id={panel.id} title={panel.title} active={panel.id===active?.id} onDetached={()=>{onActivate(current=>current===panel.id||panel.aliases?.includes(current??"")?null:current);}} onDocked={()=>onActivate(panel.id)} onError={setNotice}><ToolPresentation panel={panel} active={panel.id===active?.id} expanded={expanded} setExpanded={setExpanded} hide={hide}/></FloatingPanel>)}
    <button type="button" className="focus-panel-resizer spike-control--bare" aria-label="Resize tool panel" title="Drag or use arrow keys to resize; double-click to reset" onDoubleClick={()=>resize(FOCUS_PANEL_DEFAULT_WIDTH)} onKeyDown={event=>{const next=event.key==="Home"?FOCUS_PANEL_MAX_WIDTH:event.key==="End"?FOCUS_PANEL_MIN_WIDTH:event.key==="ArrowLeft"?width.current+20:event.key==="ArrowRight"?width.current-20:null;if(next!==null){event.preventDefault();resize(next);}}} onPointerDown={event=>{if(event.button!==0||!event.isPrimary)return;event.preventDefault();const target=event.currentTarget,start=event.clientX,initial=width.current;target.setPointerCapture(event.pointerId);const move=(pointer:PointerEvent)=>resize(initial+start-pointer.clientX);const stop=(pointer:PointerEvent)=>{if(target.hasPointerCapture(pointer.pointerId))target.releasePointerCapture(pointer.pointerId);target.removeEventListener("pointermove",move);target.removeEventListener("pointerup",stop);target.removeEventListener("pointercancel",stop);target.removeEventListener("lostpointercapture",stop);};target.addEventListener("pointermove",move);target.addEventListener("pointerup",stop);target.addEventListener("pointercancel",stop);target.addEventListener("lostpointercapture",stop);}}><GripVertical size={14} aria-hidden="true"/></button>
  </aside>;
}
