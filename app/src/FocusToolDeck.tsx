import { panelCloseState, panelDismissControl } from "./panelDismiss";
import PanelNavigation, { type PanelNavigationController } from "./PanelNavigation";
import FloatingPanel, { FloatingPanelControls, useFloatingPanel } from "./FloatingPanel";
// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useEffect, useLayoutEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { ExternalLink, EyeOff, GripVertical, Maximize2, Minimize2, Minus, PanelRightClose, X } from "./icons";
import { CloseControlIcon, HideControlIcon } from "./navigationIcons";
import { PanelHeaderActionsContext, usePanelHeaderMenu } from "./PanelHeaderMenu";
import { type ContextAction } from "./ActionContextMenu";
import { minimizeTool, removeMinimizedTool } from "./minimizedTools";

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
  presentation?: "panel" | "document";
  onClose?: () => void;
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

/** Only duplicate surface dismissal is replaced; domain actions keep their controls. */
export function isRedundantPanelDismiss(label: string, text: string, title: string, headerCloseIcon = false): boolean {
  const name=label.trim().toLowerCase(), copy=text.trim().toLowerCase();
  return name==="close" || name==="close panel" || name===`close ${title.trim().toLowerCase()}`
    || (!name && (copy==="close" || headerCloseIcon));
}

function ToolPresentation({panel,active,expanded,setExpanded,hide,panels,activeId,onActivate,navigation}: {panels:readonly FocusToolPanel[];activeId:string|null;onActivate:(id:string|null)=>void;navigation?:PanelNavigationController;panel:FocusToolPanel;active:boolean;expanded:boolean;setExpanded:Dispatch<SetStateAction<boolean>>;hide:()=>void}) {
  const floating=useFloatingPanel();
  const container=useRef<HTMLElement>(null);
  const [closeReason,setCloseReason]=useState("");
  const closeBlocked=Boolean(closeReason);
  const hidePanel=()=>{if(floating?.detached)floating.dock();hide();};
  const closePanel=()=>{
    const content=container.current?.querySelector<HTMLElement>(".focus-tool-content");
    const state=content ? panelCloseState(content,panel.title) : {control:null,reason:""};
    setCloseReason(state.reason);
    if(state.reason)return;
    if(state.control)state.control.click();else panel.onClose?.();
  };
  const headerActions: ContextAction[] = [
    ...(floating?[{label:floating.detached?"Dock back":"Move to floating window",icon:floating.detached?PanelRightClose:ExternalLink,description:floating.detached?"Return to the workspace":"Detach into a movable native window",run:()=>floating.detached?floating.dock():floating.detach()}]:[]),
    ...(!floating?.detached?[{label:expanded?"Restore":"Expand",icon:expanded?Minimize2:Maximize2,run:()=>setExpanded(value=>!value)}, {label:"Resize panel",icon:GripVertical,description:"Focus the panel edge; use arrow keys to resize",run:()=>container.current?.closest(".focus-tool-deck-host")?.querySelector<HTMLElement>(".focus-panel-resizer")?.focus()}]:[]),
    {label:"Minimize",icon:Minus,description:"Hide and keep current inputs",run:hidePanel},
    {label:"Hide",icon:EyeOff,description:"Keep current inputs",run:hidePanel},
    ...(panel.onClose?[{label:"Close",icon:X,description:closeReason||"Close through this tool's existing workflow",disabled:closeBlocked,run:closePanel}]:[]),
  ];
  const headerMenu=usePanelHeaderMenu(panel.title,headerActions);
  useFocusLayoutEffect(()=>{
    const root=container.current;if(!root)return;
    const adapt=()=>{
      const content=root.querySelector<HTMLElement>(".focus-tool-content");
      const owningDismiss=content ? panelDismissControl(content,panel.title) : null;

      root.querySelectorAll<HTMLElement>('[aria-modal="true"]').forEach(dialog=>{const ancestor=dialog.parentElement?.closest('[role="dialog"]');if(!ancestor || !root.contains(ancestor))dialog.setAttribute("aria-modal","false");});
      root.querySelectorAll<HTMLElement>('.focus-tool-content button').forEach(button=>{
        const dialog=button.closest('[role="dialog"],[role="alertdialog"]'),outer=dialog?.parentElement?.closest('[role="dialog"],[role="alertdialog"]');
        if(dialog?.getAttribute("role")==="alertdialog" || (outer && root.contains(outer)))return;
        const surfaceHeader=button.closest("header,.floating-heading,.modal-heading,.floating-panel-title");
        const inHeader=Boolean(surfaceHeader);
        const heading=surfaceHeader?.querySelector<HTMLElement>('h1,h2,h3,strong,b');
        if(heading?.textContent?.trim().toLowerCase()===panel.title.trim().toLowerCase())heading.dataset.spikeDuplicateTitle="true";
        const label=button.getAttribute("aria-label")??button.getAttribute("title")??"";
        const iconClose=inHeader&&Boolean(button.querySelector('svg.lucide-x,svg.lucide-circle-x'));
        const redundant=Boolean(panel.onClose)&&(button===owningDismiss||(!inHeader&&isRedundantPanelDismiss(label,button.textContent??"",panel.title)));

        if(redundant)button.dataset.spikeInnerDismiss="true";
        else delete button.dataset.spikeInnerDismiss;
      });
      setCloseReason(content ? panelCloseState(content,panel.title).reason : "");
    };
    adapt();const observer=new MutationObserver(adapt);observer.observe(root,{childList:true,subtree:true,attributes:true,attributeFilter:["aria-modal","disabled","hidden","inert","class","style","title","aria-label"]});return()=>observer.disconnect();
  },[panel.title,Boolean(panel.onClose)]);
  return <section ref={container} className="focus-tool-deck" id={`workspace-editor-panel-${panel.id}`} role={panel.presentation==="document"?"tabpanel":undefined} aria-label={panel.title}>
    <header className="focus-tool-heading" {...headerMenu.headerProps} onPointerDown={floating?.onHeaderPointerDown} title="Drag this header outside the main window to detach"><h2 className="sr-only">{panel.title}</h2><PanelNavigation panels={panels} activeId={activeId} onActivate={onActivate} controller={navigation}/><div className="focus-tool-window-actions"><FloatingPanelControls/>{!floating?.detached&&<><button type="button" className="spike-control--compact" onClick={()=>setExpanded(value=>!value)} aria-label={expanded?"Restore tool panel":"Expand tool panel"} aria-pressed={expanded} title={expanded?"Restore viewport beside this tool":"Expand tool to workspace"}>{expanded?<Minimize2 size={14}/>:<Maximize2 size={14}/>}<span>{expanded?"Restore":"Expand"}</span></button></>}<button type="button" className="spike-control--compact" onClick={hidePanel} aria-label="Hide panel" title="Hide panel and keep its current inputs"><HideControlIcon size={14}/><span>Hide</span></button></div>{panel.onClose&&<button type="button" className="spike-control--icon" disabled={closeBlocked} onClick={closePanel} aria-label={`Close ${panel.title}`} title={closeReason||`Close ${panel.title}`}><CloseControlIcon size={14}/></button>}</header>{headerMenu.menu}
    <FocusDockContext.Provider value={{embedded:true,hide}}><div className="focus-tool-content" style={{zoom:floating?.scale ?? 1}}><PanelHeaderActionsContext.Provider value={headerActions}>{panel.content}</PanelHeaderActionsContext.Provider></div></FocusDockContext.Provider>
  </section>;
}
export default function FocusToolDeck({panels,activeId,commandsOpen,onActivate,navigation}: {navigation?:PanelNavigationController;panels:readonly FocusToolPanel[];activeId:string|null;commandsOpen:boolean;onActivate:Dispatch<SetStateAction<string|null>>}) {
  const active=commandsOpen?undefined:activeFocusPanel(panels,activeId);
  const [expandedPanels,setExpandedPanels]=useState<Record<string,boolean>>({}),[notice,setNotice]=useState("");
  const expanded = active ? expandedPanels[active.id] === true : false;
  const setExpanded: Dispatch<SetStateAction<boolean>> = next => { if(active)setExpandedPanels(current=>({...current,[active.id]:typeof next==="function"?next(current[active.id]===true):next})); };
  const container=useRef<HTMLElement>(null),width=useRef(FOCUS_PANEL_DEFAULT_WIDTH);
  useEffect(()=>{try{const saved=localStorage.getItem("spike.focus.panel.width");if(saved!==null){width.current=normalizeFocusPanelWidth(saved);container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-editor-width",`${width.current}px`);}}catch{/* Optional preference. */}container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-panel-width",`${width.current}px`);},[]);
  useEffect(()=>{const workspace=container.current?.closest<HTMLElement>(".workspace");workspace?.classList.toggle("focus-panel-expanded",expanded&&Boolean(active));return()=>workspace?.classList.remove("focus-panel-expanded");},[expanded,active?.id]);
  const hide=(panel:FocusToolPanel)=>{minimizeTool({id:`focus:${panel.id}`,label:panel.title,restore:()=>onActivate(panel.id)});onActivate(current=>current===panel.id||panel.aliases?.includes(current??"")?null:current);document.getElementById("focus-menu-toggle")?.focus();};
  useEffect(()=>{if(active)removeMinimizedTool(`focus:${active.id}`);for(const panel of panels)if(!panel.open)removeMinimizedTool(`focus:${panel.id}`);},[active?.id,panels]);
  useEffect(()=>()=>{for(const panel of panels)removeMinimizedTool(`focus:${panel.id}`);},[]);
  const resize=(next:number)=>{width.current=normalizeFocusPanelWidth(next);container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-editor-width",`${width.current}px`);container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-panel-width",`${width.current}px`);try{localStorage.setItem("spike.focus.panel.width",String(width.current));}catch{/* Optional preference. */}};
  return <aside ref={container} className="focus-tool-deck-host" data-presentation={active?.presentation??"panel"} hidden={!active} aria-label={active?.title??"Tool panel"}>
    {notice&&<p role="alert">{notice}</p>}
    {panels.filter(panel=>panel.open).map(panel=><FloatingPanel key={panel.id} id={panel.id} title={panel.title} active={panel.id===active?.id} onDetached={()=>{onActivate(current=>current===panel.id||panel.aliases?.includes(current??"")?null:current);}} onDocked={()=>onActivate(panel.id)} onError={setNotice}><ToolPresentation panels={panels} activeId={panel.id} onActivate={onActivate} navigation={navigation} panel={panel} active={panel.id===active?.id} expanded={expanded} setExpanded={setExpanded} hide={()=>hide(panel)}/></FloatingPanel>)}
    <button type="button" className="focus-panel-resizer spike-control--bare" aria-label="Resize tool panel" title="Drag or use arrow keys to resize; double-click to reset" onDoubleClick={()=>resize(FOCUS_PANEL_DEFAULT_WIDTH)} onKeyDown={event=>{const measured=container.current?.getBoundingClientRect().width||width.current;const next=event.key==="Home"?FOCUS_PANEL_MAX_WIDTH:event.key==="End"?FOCUS_PANEL_MIN_WIDTH:event.key==="ArrowLeft"?measured+20:event.key==="ArrowRight"?measured-20:null;if(next!==null){event.preventDefault();resize(next);}}} onPointerDown={event=>{if(event.button!==0||!event.isPrimary)return;event.preventDefault();const target=event.currentTarget,start=event.clientX,initial=container.current?.getBoundingClientRect().width||width.current;target.setPointerCapture(event.pointerId);const move=(pointer:PointerEvent)=>resize(initial+start-pointer.clientX);const stop=(pointer:PointerEvent)=>{if(target.hasPointerCapture(pointer.pointerId))target.releasePointerCapture(pointer.pointerId);target.removeEventListener("pointermove",move);target.removeEventListener("pointerup",stop);target.removeEventListener("pointercancel",stop);target.removeEventListener("lostpointercapture",stop);};target.addEventListener("pointermove",move);target.addEventListener("pointerup",stop);target.addEventListener("pointercancel",stop);target.addEventListener("lostpointercapture",stop);}}><GripVertical size={14} aria-hidden="true"/></button>
  </aside>;
}
