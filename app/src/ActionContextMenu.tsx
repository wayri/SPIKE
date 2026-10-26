import { CloseControlIcon } from "./navigationIcons";
// SPDX-License-Identifier: Apache-2.0
import { optionMatchesQuery } from "./optionSearch";
import { useEffect, useRef, useState, type PointerEventHandler } from "react";
import { createPortal } from "react-dom";
import { Check, type LucideIcon, Atom, ClipboardPaste, Code2, Copy, Hash, IndentDecrease, IndentIncrease, Layers3, MousePointer2, Pencil, Scissors, TextSelect } from "./icons";
import { usePanelPresentation } from "./panelPresentation";
import "./ActionContextMenu.css";

export type ContextAction = { label: string; description?: string; disabled?: boolean; icon?: LucideIcon; accent?: string; checked?: boolean; radio?: boolean; section?: string; run: () => void };
export default function ActionContextMenu({ x, y, title, actions, onClose, id, preview=false, onPointerEnter, onPointerLeave, anchorElement }: {preview?:boolean;onPointerEnter?:PointerEventHandler<HTMLDivElement>;onPointerLeave?:PointerEventHandler<HTMLDivElement>;anchorElement?:HTMLElement|null; x: number; y: number; title: string; actions: ContextAction[]; onClose: () => void; id?: string }) {
  const { ownerDocument, ownerWindow } = usePanelPresentation();
  const [query, setQuery] = useState("");
  const filtered = actions.filter(action => optionMatchesQuery(`${action.label} ${action.description ?? ""} ${action.section ?? ""}`, query));
  const menu = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose); closeRef.current = onClose;
  const returnFocus = useRef<HTMLElement | null>((ownerDocument?.activeElement as HTMLElement | null) ?? null);
  const close = () => { onClose(); if (!preview && returnFocus.current?.isConnected) returnFocus.current.focus({ preventScroll: true }); };
  useEffect(() => {
    const element = menu.current, doc = ownerDocument, view = ownerWindow; if (!element || !doc || !view) return;
    const bounds = element.getBoundingClientRect();
    element.style.left = `${Math.max(8, Math.min(x, view.innerWidth - bounds.width - 8))}px`;
    element.style.top = `${Math.max(8, Math.min(y, view.innerHeight - bounds.height - 8))}px`;
    if(!preview)element.querySelector<HTMLElement>("input, button:not(:disabled)")?.focus({ preventScroll: true });
    const dismiss = (event: PointerEvent) => { if (!element.contains(event.target as Node) && !anchorElement?.contains(event.target as Node)) closeRef.current(); };
    const escape = () => closeRef.current();
    const scroll = (event: Event) => { const node = event.target as Node | null; if (node && typeof node.nodeType === "number" && element.contains(node)) return; closeRef.current(); };
    doc.addEventListener("pointerdown", dismiss); view.addEventListener("resize", escape); view.addEventListener("scroll", scroll, true);
    return () => { doc.removeEventListener("pointerdown", dismiss); view.removeEventListener("resize", escape); view.removeEventListener("scroll", scroll, true); };
  }, [ownerDocument, ownerWindow, x, y, preview, anchorElement]);
  if (!ownerDocument?.body) return null;
  return createPortal(<div id={id} ref={menu} className="spike-action-context-menu" data-preview={preview||undefined} onPointerEnter={onPointerEnter} onPointerLeave={onPointerLeave} role="menu" aria-label={`${title} context menu`} style={{ left: x, top: y }}
    onContextMenu={event => event.preventDefault()} onKeyDown={event => {
      event.stopPropagation();
      if (event.key === "Escape" || event.key === "Tab") { event.preventDefault(); close(); return; }
      if ((event.target as Element).tagName === "INPUT" && !["ArrowDown", "ArrowUp"].includes(event.key)) return;
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")], current = items.indexOf(ownerDocument.activeElement as HTMLButtonElement);
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (current + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length]?.focus();
    }}><header className="action-menu-heading"><strong>{title}</strong><button type="button" className="spike-control--icon" title={`Close ${title}`} aria-label={`Close ${title}`} onClick={close}><CloseControlIcon size={14}/></button></header><input className="action-menu-search" type="search" aria-label={`Search ${title} actions`} placeholder="Search actions · * or ?" maxLength={128} value={query} onChange={event => setQuery(event.target.value)}/>{filtered.map((action, index) => { const Icon = action.icon ?? ( /^cut$/i.test(action.label) ? Scissors : /^paste$/i.test(action.label) ? ClipboardPaste : /^select all$/i.test(action.label) ? TextSelect : /^dedent$/i.test(action.label) ? IndentDecrease : /^indent$/i.test(action.label) ? IndentIncrease : /comment/i.test(action.label) ? Hash : /script/i.test(action.label) ? Code2 : /copy|duplicate/i.test(action.label) ? Copy : /material/i.test(action.label) ? Atom : /layer/i.test(action.label) ? Layers3 : /edit/i.test(action.label) ? Pencil : MousePointer2);
      return <div className="action-menu-row" key={action.label}>
        {action.section && action.section !== filtered[index - 1]?.section && <div className="action-menu-section" role="presentation">{action.section}</div>}
        <button type="button" role={action.checked === undefined ? "menuitem" : action.radio ? "menuitemradio" : "menuitemcheckbox"} aria-checked={action.checked}
          title={action.description ? `${action.label} · ${action.description}` : action.label} disabled={action.disabled} onClick={() => { close(); action.run(); }}>
          <Icon size={16} aria-hidden="true" data-workspace={action.accent}/><span className="action-menu-copy"><span>{action.label}</span>{action.description && <small>{action.description}</small>}</span>
          {action.checked !== undefined && <span className="action-menu-check">{action.checked && <Check size={14} aria-hidden="true" />}</span>}
        </button></div>; })}{!filtered.length && <p role="status">No matching actions.</p>}</div>, ownerDocument.body);
}
