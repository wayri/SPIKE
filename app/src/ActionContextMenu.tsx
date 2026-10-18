// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { Check, type LucideIcon, Atom, ClipboardPaste, Code2, Copy, Hash, IndentDecrease, IndentIncrease, Layers3, MousePointer2, Pencil, Scissors, TextSelect } from "./icons";
import { usePanelPresentation } from "./panelPresentation";
import "./ActionContextMenu.css";

export type ContextAction = { label: string; description?: string; disabled?: boolean; icon?: LucideIcon; accent?: string; checked?: boolean; radio?: boolean; section?: string; run: () => void };
export default function ActionContextMenu({ x, y, title, actions, onClose, id }: { x: number; y: number; title: string; actions: ContextAction[]; onClose: () => void; id?: string }) {
  const { ownerDocument, ownerWindow } = usePanelPresentation();
  const menu = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose); closeRef.current = onClose;
  const returnFocus = useRef<HTMLElement | null>((ownerDocument?.activeElement as HTMLElement | null) ?? null);
  const close = () => { onClose(); if (returnFocus.current?.isConnected) returnFocus.current.focus({ preventScroll: true }); };
  useEffect(() => {
    const element = menu.current, doc = ownerDocument, view = ownerWindow; if (!element || !doc || !view) return;
    const bounds = element.getBoundingClientRect();
    element.style.left = `${Math.max(8, Math.min(x, view.innerWidth - bounds.width - 8))}px`;
    element.style.top = `${Math.max(8, Math.min(y, view.innerHeight - bounds.height - 8))}px`;
    element.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus({ preventScroll: true });
    const dismiss = (event: PointerEvent) => { if (!element.contains(event.target as Node)) closeRef.current(); };
    const escape = () => closeRef.current();
    doc.addEventListener("pointerdown", dismiss); view.addEventListener("resize", escape); view.addEventListener("scroll", escape, true);
    return () => { doc.removeEventListener("pointerdown", dismiss); view.removeEventListener("resize", escape); view.removeEventListener("scroll", escape, true); };
  }, [ownerDocument, ownerWindow, x, y]);
  if (!ownerDocument?.body) return null;
  return createPortal(<div id={id} ref={menu} className="spike-action-context-menu" role="menu" aria-label={`${title} context menu`} style={{ left: x, top: y }}
    onContextMenu={event => event.preventDefault()} onKeyDown={event => {
      event.stopPropagation();
      if (event.key === "Escape" || event.key === "Tab") { event.preventDefault(); close(); return; }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")], current = items.indexOf(ownerDocument.activeElement as HTMLButtonElement);
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length]?.focus();
    }}><strong>{title}</strong>{actions.map((action, index) => { const Icon = action.icon ?? ( /^cut$/i.test(action.label) ? Scissors : /^paste$/i.test(action.label) ? ClipboardPaste : /^select all$/i.test(action.label) ? TextSelect : /^dedent$/i.test(action.label) ? IndentDecrease : /^indent$/i.test(action.label) ? IndentIncrease : /comment/i.test(action.label) ? Hash : /script/i.test(action.label) ? Code2 : /copy|duplicate/i.test(action.label) ? Copy : /material/i.test(action.label) ? Atom : /layer/i.test(action.label) ? Layers3 : /edit/i.test(action.label) ? Pencil : MousePointer2);
      return <div className="action-menu-row" key={action.label}>
        {action.section && action.section !== actions[index - 1]?.section && <div className="action-menu-section" role="presentation">{action.section}</div>}
        <button type="button" role={action.checked === undefined ? "menuitem" : action.radio ? "menuitemradio" : "menuitemcheckbox"} aria-checked={action.checked}
          title={action.description ? `${action.label} · ${action.description}` : action.label} disabled={action.disabled} onClick={() => { close(); action.run(); }}>
          <Icon size={16} aria-hidden="true" data-workspace={action.accent}/><span className="action-menu-copy"><span>{action.label}</span>{action.description && <small>{action.description}</small>}</span>
          {action.checked !== undefined && <span className="action-menu-check">{action.checked && <Check size={14} aria-hidden="true" />}</span>}
        </button></div>; })}</div>, ownerDocument.body);
}
