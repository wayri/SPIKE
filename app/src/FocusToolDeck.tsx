// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useEffect, useLayoutEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import { Maximize2, Minimize2, PanelRightClose } from "./icons";

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

export default function FocusToolDeck({ panels, activeId, commandsOpen, onActivate }: {
  panels: readonly FocusToolPanel[];
  activeId: string | null;
  commandsOpen: boolean;
  onActivate: Dispatch<SetStateAction<string | null>>;
}) {
  const active = commandsOpen ? undefined : activeFocusPanel(panels, activeId);
  const [expanded, setExpanded] = useState(false);
  const container = useRef<HTMLElement>(null);
  const width = useRef(360);
  useFocusLayoutEffect(() => {
    const root = container.current;
    if (!root) return;
    // Legacy tool dialogs are nonmodal in the reserved slot. Nested confirmations
    // keep their modality; lazy-loaded dialogs are adapted when they arrive.
    const adapt = () => root.querySelectorAll<HTMLElement>('[aria-modal="true"]').forEach(dialog => {
      const owner = dialog.closest(".focus-tool-content");
      const ancestor = dialog.parentElement?.closest('[role="dialog"]');
      if (owner && (!ancestor || !owner.contains(ancestor))) dialog.setAttribute("aria-modal", "false");
    });
    adapt();
    const observer = new MutationObserver(adapt);
    observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ["aria-modal"] });
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    try { const saved = Number(localStorage.getItem("spike.focus.panel.width")); if (Number.isFinite(saved) && saved >= 280 && saved <= 640) width.current = saved; } catch { /* Optional preference. */ }
    container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-panel-width", `${width.current}px`);
  }, []);
  useEffect(() => { setExpanded(false); }, [active?.id]);
  useEffect(() => {
    const workspace = container.current?.closest<HTMLElement>(".workspace");
    workspace?.classList.toggle("focus-panel-expanded", expanded && Boolean(active));
    return () => { workspace?.classList.remove("focus-panel-expanded"); };
  }, [expanded, active?.id]);
  const hide = () => { onActivate(null); document.getElementById("focus-menu-toggle")?.focus(); };
  const resize = (next: number) => {
    width.current = Math.max(280, Math.min(640, next));
    container.current?.closest<HTMLElement>(".workspace")?.style.setProperty("--focus-panel-width", `${width.current}px`);
    try { localStorage.setItem("spike.focus.panel.width", String(width.current)); } catch { /* Optional preference. */ }
  };
  return <aside ref={container} className="focus-tool-deck" hidden={!active} aria-label={active?.title ?? "Tool panel"}>
    <header className="focus-tool-heading"><h2>{active?.title}</h2><button type="button" className="spike-control--compact" onClick={() => setExpanded(value => !value)} aria-pressed={expanded} title={expanded ? "Restore viewport beside this tool" : "Expand tool to workspace"}>{expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}<span>{expanded ? "Restore" : "Expand"}</span></button><button type="button" className="spike-control--compact" onClick={hide} title="Hide panel and keep its current inputs"><PanelRightClose size={14} /><span>Hide</span></button></header>
    <FocusDockContext.Provider value={{ embedded: true, hide }}>
      {panels.filter(panel => panel.open).map(panel => <section key={panel.id} className="focus-tool-content" hidden={panel.id !== active?.id} aria-label={panel.title}>
        {panel.content}
      </section>)}
    </FocusDockContext.Provider>
    <button type="button" className="focus-panel-resizer spike-control--bare" aria-label="Resize tool panel" title="Drag to resize; arrow keys change width" onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); resize(width.current + (event.key === "ArrowLeft" ? 20 : -20)); } }} onPointerDown={event => {
      event.preventDefault(); const target = event.currentTarget, start = event.clientX, initial = width.current;
      target.setPointerCapture(event.pointerId);
      const move = (pointer: PointerEvent) => resize(initial + start - pointer.clientX);
      const stop = () => { target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", stop); target.removeEventListener("pointercancel", stop); };
      target.addEventListener("pointermove", move); target.addEventListener("pointerup", stop); target.addEventListener("pointercancel", stop);
    }} />
  </aside>;
}
