import { prepareLinkedPanelClose } from "./panelWindowBridge";
// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, PanelRightClose } from "./icons";
import { PanelPresentationContext } from "./panelPresentation";
import { installWebviewGuards } from "./webviewGuards";

export function normalizePanelScale(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(.65, Math.min(1.5, value)) : 1;
}
export function panelDragLeavesWindow(point: {x:number;y:number}, viewport: {width:number;height:number}): boolean {
  return point.x < 0 || point.y < 0 || point.x > viewport.width || point.y > viewport.height;
}
const floatingWindows = new Map<string, Window>();
export function floatingPanelDocuments(): Document[] {
  return Array.from(floatingWindows.values()).flatMap(child => {
    try { return child.closed ? [] : [child.document]; } catch { return []; }
  });
}
export function focusFloatingPanel(id: string): boolean {
  const child=floatingWindows.get(id);
  if(!child || child.closed)return false;
  child.focus();return true;
}

type FloatingActions = { detached: boolean; detach: (point?: {x:number;y:number}) => void; dock: () => void; onHeaderPointerDown: (event: ReactPointerEvent<HTMLElement>) => void; scale: number; setScale: (value:number) => void };
const FloatingContext = createContext<FloatingActions | null>(null);
const usePortalLayoutEffect=typeof window === "undefined"?useEffect:useLayoutEffect;
export const useFloatingPanel = () => useContext(FloatingContext);
export function FloatingPanelControls() {
  const floating = useFloatingPanel();
  if (!floating) return null;
  return <><label className="focus-panel-scale" title="Scale this panel only (65%-150%). Choose 100% for the default size."><span className="sr-only">Panel scale</span><select aria-label="Panel scale" value={floating.scale} onChange={event => floating.setScale(Number(event.target.value))}>{[.65,.75,.9,1,1.1,1.25,1.5].map(value => <option key={value} value={value}>{Math.round(value*100)}%</option>)}</select></label><button type="button" className="spike-control--compact" aria-label={floating.detached ? "Dock back" : "Detach panel"} onClick={() => floating.detached ? floating.dock() : floating.detach()} title={floating.detached ? "Return this panel to the workspace" : "Detach into a native floating window"}>{floating.detached ? <PanelRightClose size={14}/> : <ExternalLink size={14}/>}<span>{floating.detached ? "Dock back" : "Detach"}</span></button></>;
}
/** A stable portal target is adopted, not recreated: component state stays owned by App. */
export default function FloatingPanel({id,title,active,children,onDetached,onDocked,onError}: {id:string;title:string;active:boolean;children:ReactNode;onDetached?:()=>void;onDocked?:()=>void;onError?:(message:string)=>void}) {
  const slot=useRef<HTMLDivElement>(null);
  const [host]=useState(()=>{if(typeof document === "undefined")return null;const element=document.createElement("div");element.style.cssText="height:100%;min-height:0;min-width:0;";return element;});
  const [child,setChild]=useState<Window|null>(null), [notice,setNotice]=useState("");
  const [scale,setScaleState]=useState(()=>{try {const raw=localStorage.getItem(`spike.panel.scale.${id}`);return raw===null?1:normalizePanelScale(Number(raw));}catch{return 1;}});
  const popup=useRef<Window|null>(null), cleanup=useRef<(()=>void)|null>(null), closeChild=useRef<(()=>Promise<void>)|null>(null), dragging=useRef(false), dragCleanup=useRef<(()=>void)|null>(null), dockHandler=useRef<()=>void>(()=>{});
  const callbacks=useRef({onDetached,onDocked,onError});callbacks.current={onDetached,onDocked,onError};
  usePortalLayoutEffect(()=>{if(host && slot.current && !popup.current) slot.current.appendChild(host);},[host]);
  const dock=()=>{
    const current=popup.current;floatingWindows.delete(id);popup.current=null;cleanup.current?.();cleanup.current=null;
    if(host && slot.current) slot.current.appendChild(host);
    setChild(null);setNotice(""); callbacks.current.onDocked?.();
    const close=closeChild.current;closeChild.current=null;if(close)void close().catch(error=>{const message=`Could not close floating window: ${String(error)}`;setNotice(message);callbacks.current.onError?.(message);});else if(current && !current.closed)current.close();
  };dockHandler.current=dock;
  const detach=(point?:{x:number;y:number})=>{
    if(!host)return;
    if(popup.current && !popup.current.closed){popup.current.focus();return;}
    let opened:Window|null=null, notified=false;
    try {
      const left=Math.round(point?.x ?? window.screenX+80),top=Math.round(point?.y ?? window.screenY+70);
      opened=window.open("about:blank","_blank",`popup=yes,width=920,height=720,left=${left},top=${top},resizable=yes,scrollbars=yes`);
      if(!opened)throw new Error("The floating window could not open. Retry Detach; browser previews require popup permission.");
      const doc=opened.document;closeChild.current=prepareLinkedPanelClose(opened);
      doc.title=`SPIKE | ${title}`;
      document.querySelectorAll('style,link[rel="stylesheet"]').forEach(node=>{const copy=node.cloneNode(true) as HTMLElement;if(node instanceof HTMLLinkElement)copy.setAttribute("href",node.href);doc.head.appendChild(copy);});
      doc.body.className="app-shell focus-shell focus-floating-native";
      doc.body.style.cssText="display:block;margin:0;overflow:hidden;width:100vw;height:100vh;";
      const sync=()=>{doc.documentElement.lang=document.documentElement.lang;doc.documentElement.style.zoom=document.documentElement.style.zoom;Object.assign(doc.documentElement.dataset,document.documentElement.dataset);opened?.dispatchEvent(new Event("resize"));};
      sync();doc.body.appendChild(host);
      const observer=new MutationObserver(sync);observer.observe(document.documentElement,{attributes:true});
      const removeGuards=installWebviewGuards(opened);
      // Stop ordinary links from replacing the trusted blank browsing context.
      const preventNavigation=(event:Event)=>{const target=event.target as Element|null;if(target?.closest?.('a[href]'))event.preventDefault();};
      doc.addEventListener("click",preventNavigation);
      const closing=()=>{if(popup.current===opened)dockHandler.current();};opened.addEventListener("beforeunload",closing);
      const timer=window.setInterval(()=>{if(opened?.closed && popup.current===opened)dockHandler.current();},250);
      cleanup.current=()=>{observer.disconnect();removeGuards();doc.removeEventListener("click",preventNavigation);opened?.removeEventListener("beforeunload",closing);window.clearInterval(timer);};
      popup.current=opened;floatingWindows.set(id,opened);setChild(opened);setNotice("");notified=true;callbacks.current.onDetached?.();opened.focus();
    }catch(error){floatingWindows.delete(id);popup.current=null;cleanup.current?.();cleanup.current=null;setChild(null);if(host&&slot.current)slot.current.appendChild(host);const close=closeChild.current;closeChild.current=null;if(close)void close().catch(()=>opened?.close());else try{opened?.close();}catch{/* Original draft remains docked. */}if(notified)callbacks.current.onDocked?.();const message=error instanceof Error?error.message:"Panel detachment failed.";setNotice(message);callbacks.current.onError?.(message);}
  };
  const setScale=(value:number)=>{const next=normalizePanelScale(value);setScaleState(next);try{localStorage.setItem(`spike.panel.scale.${id}`,String(next));}catch{/* Optional local preference. */}};
  const onHeaderPointerDown=(event:ReactPointerEvent<HTMLElement>)=>{
    if(event.button!==0 || !event.isPrimary || popup.current || (event.target as HTMLElement).closest("button,select,input,a"))return;
    dragCleanup.current?.();const target=event.currentTarget,start={x:event.clientX,y:event.clientY};target.setPointerCapture(event.pointerId);
    const move=(pointer:PointerEvent)=>{dragging.current=Math.hypot(pointer.clientX-start.x,pointer.clientY-start.y)>8;target.classList.toggle("panel-dragging",dragging.current);};
    const stop=(pointer:PointerEvent)=>{dragCleanup.current?.();dragCleanup.current=null;if(target.hasPointerCapture(pointer.pointerId))target.releasePointerCapture(pointer.pointerId);if(dragging.current && panelDragLeavesWindow({x:pointer.clientX,y:pointer.clientY},{width:window.innerWidth,height:window.innerHeight}))detach({x:pointer.screenX-30,y:pointer.screenY-20});dragging.current=false;};
    const cancel=(pointer:PointerEvent)=>{dragging.current=false;stop(pointer);};
    dragCleanup.current=()=>{target.removeEventListener("pointermove",move);target.removeEventListener("pointerup",stop);target.removeEventListener("pointercancel",cancel);target.removeEventListener("lostpointercapture",cancel);target.classList.remove("panel-dragging");};target.addEventListener("pointermove",move);target.addEventListener("pointerup",stop);target.addEventListener("pointercancel",cancel);target.addEventListener("lostpointercapture",cancel);
  };
  useEffect(()=>{if(active && child && !child.closed)child.focus();},[active,child]);
  useEffect(()=>()=>{dragCleanup.current?.();cleanup.current?.();floatingWindows.delete(id);const close=closeChild.current;closeChild.current=null;if(close)void close().catch(error=>callbacks.current.onError?.(`Could not retire floating window: ${String(error)}`));else popup.current?.close();popup.current=null;},[]);
  const contents=<FloatingContext.Provider value={{detached:Boolean(child),detach,dock,onHeaderPointerDown,scale,setScale}}><PanelPresentationContext.Provider value={{ownerDocument:child?.document ?? (typeof document!=="undefined"?document:undefined),ownerWindow:child ?? (typeof window!=="undefined"?window:undefined),detached:Boolean(child)}}><div className="floating-panel-frame" hidden={!active && !child} style={{height:"100%"}}>{notice&&<p className="floating-panel-notice" role="alert">{notice}</p>}{children}</div></PanelPresentationContext.Provider></FloatingContext.Provider>;
  return <div ref={slot} className="focus-floating-slot" hidden={!active || Boolean(child)} data-panel-id={id} aria-label={title}>{host?createPortal(contents,host,id):contents}</div>;
}
