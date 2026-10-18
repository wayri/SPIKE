// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { Activity, ArrowLeft, Box, ChevronRight, CircuitBoard, ClipboardCheck, Eye, Focus, FolderOpen, Layers3, Magnet, Network, Play, Search, SlidersHorizontal, Target, Thermometer, X, type LucideIcon } from "./icons";
import { usePanelPresentation } from "./panelPresentation";
import "./buttonStandard.css";
import "./ViewportActionMenu.css";

export type ContextMenuAction = { id: string; label: string; description?: string; disabledReason?: string; run: () => void };
export type ContextMenuGroup = { id: string; label: string; actions: ContextMenuAction[] };
export type ViewportActionMenuProps = { x: number; y: number; title: string; summary: string[]; groups: ContextMenuGroup[]; onClose: () => void };

function actionIcon(id:string):LucideIcon {
  if(id.startsWith("pi-") || id.includes("power"))return Activity;
  if(id.startsWith("si-") || id.includes("trace"))return Network;
  if(id.startsWith("thermal"))return Thermometer;
  if(id.startsWith("em-"))return Magnet;
  if(id.includes("layer") || id==="stackup")return Layers3;
  if(id==="probe")return Target;
  if(id.includes("focus") || id==="fit")return Focus;
  if(id.includes("model") || id.includes("assembly"))return Box;
  if(id.includes("result") || id.includes("report") || id==="validate")return ClipboardCheck;
  if(id==="schematic")return CircuitBoard;
  if(id==="isolate-net" || id==="models")return Eye;
  if(id==="playback")return Play;
  if(id.includes("project") || id.includes("import"))return FolderOpen;
  return SlidersHorizontal;
}
function ContextActionIcon({id}:{id:string}) { const Icon=actionIcon(id);return <Icon size={15} aria-hidden="true"/>; }

/** Presentation only: the workspace owns availability, summaries, and command callbacks. */
export default function ViewportActionMenu({ x, y, title, summary, groups, onClose }: ViewportActionMenuProps) {
  const { ownerDocument, ownerWindow } = usePanelPresentation();
  const panel = useRef<HTMLDivElement>(null), menu = useRef<HTMLDivElement>(null), search = useRef<HTMLInputElement>(null);
  const originalFocus = useRef<HTMLElement | null>((ownerDocument?.activeElement as HTMLElement | null) ?? null), closeHandler = useRef(onClose);
  closeHandler.current = onClose;
  const identity = useId();
  const [groupId, setGroupId] = useState<string | null>(null), [query, setQuery] = useState("");
  const returnGroup = useRef<string | null>(null);
  const availableGroups = groups.filter(group => group.actions.length > 0);
  const activeGroup = availableGroups.find(group => group.id === groupId);
  const term = query.trim().toLocaleLowerCase();
  const matches = availableGroups.flatMap(group => group.actions.filter(action =>
    `${group.label} ${action.label} ${action.description ?? ""} ${action.disabledReason ?? ""}`.toLocaleLowerCase().includes(term)
  ).map(action => ({ group, action })));
  const items = () => Array.from(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
  const focusAt = (index: number) => {
    const entries = items(); if (!entries.length) return;
    const selected = ((index % entries.length) + entries.length) % entries.length;
    entries.forEach((entry, at) => entry.tabIndex = at === selected ? 0 : -1);
    entries[selected].focus(); entries[selected].scrollIntoView?.({ block: "nearest" });
  };
  const close = (restore = true) => { if (restore && originalFocus.current?.isConnected) originalFocus.current.focus(); closeHandler.current(); };
  const back = () => { returnGroup.current = groupId; setGroupId(null); };

  useEffect(() => {
    const doc = ownerDocument, view = ownerWindow; if (!doc || !view) return;
    const outside = (event: PointerEvent) => { if (!panel.current?.contains(event.target as Node)) close(); };
    const escape = (event: globalThis.KeyboardEvent) => { if (event.key === "Escape" && !event.isComposing) { event.preventDefault(); event.stopPropagation(); close(); } };
    const blur = () => close(false);
    doc.addEventListener("pointerdown", outside, true);
    doc.addEventListener("keydown", escape, true);
    view.addEventListener("blur", blur);
    focusAt(0);
    return () => {
      doc.removeEventListener("pointerdown", outside, true); doc.removeEventListener("keydown", escape, true); view.removeEventListener("blur", blur);
      // close() owns focus restoration. Restoring here would blur and dismiss
      // a newly mounted popup during React StrictMode's effect replay.
    };
  }, [ownerDocument, ownerWindow]);
  useLayoutEffect(() => {
    if (term) return;
    const target = returnGroup.current;
    if (target) { const entries = items(); focusAt(Math.max(0, entries.findIndex(entry => entry.dataset.group === target))); returnGroup.current = null; }
    else focusAt(0);
  }, [groupId, term]);
  useLayoutEffect(() => {
    const view = ownerWindow; if (!view) return;
    const fit = () => {
      const element = panel.current; if (!element) return;
      const rect = element.getBoundingClientRect();
      element.style.left = `${Math.max(8, Math.min(x, view.innerWidth - rect.width - 8))}px`;
      element.style.top = `${Math.max(8, Math.min(y, view.innerHeight - rect.height - 8))}px`;
    };
    fit(); view.addEventListener("resize", fit);
    return () => view.removeEventListener("resize", fit);
  }, [ownerWindow, x, y, groupId, query, groups, summary]);

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.isDefaultPrevented() || event.nativeEvent.isComposing) return;
    if (event.key === "Tab") { close(false); return; }
    const target = event.target as HTMLElement;
    if (target === search.current) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); focusAt(event.key === "ArrowDown" ? 0 : -1); }
      return;
    }

    const entries = items(), index = entries.indexOf(target);
    if (index < 0) return;
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault(); focusAt(event.key === "Home" ? 0 : event.key === "End" ? -1 : index + (event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "ArrowRight" && target.dataset.group && !term && !activeGroup) {
      event.preventDefault(); setGroupId(target.dataset.group);
    } else if (event.key === "ArrowLeft" && activeGroup && !term) { event.preventDefault(); back(); }
    else if (event.key.length === 1 && event.key !== " " && !event.ctrlKey && !event.metaKey && !event.altKey) {
      search.current?.focus(); setQuery(value => value + event.key); event.preventDefault();
    }
  };
  const actionButton = (action: ContextMenuAction, group?: ContextMenuGroup) => <button key={`${group?.id ?? groupId}:${action.id}`} type="button" role="menuitem" tabIndex={-1}
    className="viewport-action-menu__item spike-control--bare" aria-disabled={Boolean(action.disabledReason) || undefined}
    title={action.disabledReason ?? action.description ?? action.label}
    onClick={() => { if (action.disabledReason) return; close(); action.run(); }}>
    <ContextActionIcon id={action.id}/><span className="viewport-action-menu__copy"><span>{action.label}</span>
      {group && <small className="viewport-action-menu__context">{group.label}</small>}
      {(action.disabledReason || action.description) && <small>{action.disabledReason || action.description}</small>}
    </span>
  </button>;
  const content = <div ref={panel} className="viewport-context-menu viewport-action-menu" style={{ left: x, top: y }} onKeyDown={onKeyDown}
    onPointerDown={event => event.stopPropagation()} onContextMenu={event => event.preventDefault()}
    onBlur={event => { if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) close(false); }}>
    <div className="viewport-action-menu__heading"><strong id={`${identity}-title`}>{title}</strong>
      <button type="button" className="spike-control--icon spike-control--bare" aria-label="Close viewport actions" onClick={() => close()}><X size={14} aria-hidden="true" /></button></div>
    {summary.length > 0 && <div className="viewport-action-menu__summary">{summary.map((line, index) => <span key={index}>{line}</span>)}</div>}
    <label className="viewport-action-menu__search"><Search size={14} aria-hidden="true" /><input ref={search} type="search" aria-label="Search viewport actions" placeholder="Find an action…" value={query} onChange={event => { setQuery(event.target.value); setGroupId(null); }} /></label>
    {activeGroup && !term && <button type="button" className="viewport-action-menu__back spike-control--bare" onClick={back}><ArrowLeft size={14} aria-hidden="true" />{activeGroup.label}</button>}
    <div ref={menu} id={`${identity}-menu`} className="viewport-action-menu__list" role="menu" aria-label={term ? "Matching viewport actions" : activeGroup ? activeGroup.label : title}>
      {term ? matches.map(({ group, action }) => actionButton(action, group)) : activeGroup ? activeGroup.actions.map(action => actionButton(action)) : availableGroups.map(group =>
        <button key={group.id} type="button" role="menuitem" tabIndex={-1} className="viewport-action-menu__item spike-control--bare" data-group={group.id}
          aria-haspopup="menu" aria-expanded={false} aria-controls={`${identity}-menu`} onClick={() => setGroupId(group.id)}>
          <ContextActionIcon id={group.actions[0]?.id ?? group.id}/><span className="viewport-action-menu__copy"><span>{group.label}</span><small>{group.actions.length} {group.actions.length === 1 ? "action" : "actions"}</small></span><ChevronRight size={14} aria-hidden="true" />
        </button>)}
      {(term ? matches.length === 0 : availableGroups.length === 0) && <p className="viewport-action-menu__empty">{term ? "No matching actions. Try another search." : "No actions available here."}</p>}
    </div>
    <div className="viewport-action-menu__hint">↑↓ Navigate · → Open · ← Back · Esc Close</div>
  </div>;
  // Container queries and scrolling toolbar rows establish clipping/positioning
  // contexts. Keep the popup in its owning window's top-level document.
  return ownerDocument?.body ? createPortal(content, ownerDocument.body) : content;
}



