// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Search, X } from "./icons";
import { commitSelectChoice, optionMatchesQuery, selectChoices, type SelectChoice } from "./optionSearch";
import { searchCategory } from "./searchCategory";
import "./searchCategory.css";
import "./SelectSearchLayer.css";

/** Adapts native single-choice fields, preserving their values and change handlers.
 * The native field remains the keyboard/focus anchor and a no-JS fallback.
 */
export default function SelectSearchLayer({ ownerDocument }: { ownerDocument?: Document } = {}) {
  const doc = ownerDocument ?? document, view = doc.defaultView ?? window;
  const [target, setTarget] = useState<HTMLSelectElement | null>(null);
  const [query, setQuery] = useState("");
  const [choices, setChoices] = useState<SelectChoice[]>([]);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 300, height: 350 });
  const panel = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const label = useMemo(() => {
    const text = (node: Node): string => node.nodeType === 3 ? node.textContent ?? "" :
      node.nodeType === 1 && ["SELECT", "INPUT", "BUTTON", "TEXTAREA"].includes((node as Element).tagName) ? "" : Array.from(node.childNodes).map(text).join(" ");
    const labelled = target?.getAttribute("aria-labelledby")?.split(/\s+/).map(id => doc.getElementById(id)).filter(Boolean).map(node => text(node!)).join(" ");
    return (target?.getAttribute("aria-label") || labelled || (target?.labels?.[0] ? text(target.labels[0]).trim() : "") || target?.title || "Choose an option").slice(0, 180);
  }, [target, doc]);
  const matches = useMemo(() => choices.filter(choice => optionMatchesQuery(`${choice.label} ${choice.value} ${choice.group}`, query)), [choices, query]);
  const visible = matches.slice(0, 200);
  const close = (restore = true) => { setTarget(null); if (restore && target?.isConnected) target.focus({ preventScroll: true }); };
  useEffect(() => {
    const open = (event: Event) => {
      if ((event.target as Element | null)?.tagName !== "SELECT") return;
      const select = event.target as HTMLSelectElement;
      if (select.disabled || select.matches(":disabled") || select.multiple || select.size > 1 || !select.getClientRects().length || select.closest("[hidden],[inert]") || select.closest("[data-native-select]")) return;
      const key = event as KeyboardEvent;
      if (event.type === "keydown" && !(key.key === "Enter" || key.key === " " || key.key === "ArrowDown" || key.key === "ArrowUp" || key.key === "F4" || (key.key.length === 1 && !key.ctrlKey && !key.metaKey && !key.altKey))) return;
      if (event.type === "pointerdown" && (event as PointerEvent).button !== 0) return;
      event.preventDefault(); event.stopPropagation();
      select.focus({ preventScroll: true });
      const nextChoices = selectChoices(select), typed = event.type === "keydown" && key.key.length === 1 && key.key !== " " ? key.key : "";
      const selected = nextChoices.findIndex(choice => choice.index === select.selectedIndex);
      setChoices(nextChoices); setQuery(typed); setActive(typed ? 0 : selected < 200 ? selected : -1); setTarget(select);
    };
    doc.addEventListener("pointerdown", open, true);
    doc.addEventListener("keydown", open, true);
    return () => { doc.removeEventListener("pointerdown", open, true); doc.removeEventListener("keydown", open, true); };
  }, [doc]);
  useLayoutEffect(() => {
    if (!target) return;
    const rect = target.getBoundingClientRect(), width = Math.min(Math.max(rect.width, 300), view.innerWidth - 16);
    const below = view.innerHeight - rect.bottom - 12, above = rect.top - 12;
    const height = Math.max(140, Math.min(390, Math.max(below, above), view.innerHeight - 16));
    const top = below >= height || below >= above ? Math.min(rect.bottom + 4, view.innerHeight - height - 8) : Math.max(8, rect.top - height - 4);
    setPosition({ left: Math.max(8, Math.min(rect.left, view.innerWidth - width - 8)), top: Math.max(8, top), width, height });
    input.current?.focus();
    const dismiss = (event: Event) => { if (event.target && typeof (event.target as Node).nodeType === "number" && !panel.current?.contains(event.target as Node) && event.target !== target) setTarget(null); };
    const resize = () => setTarget(null);
    doc.addEventListener("pointerdown", dismiss, true);
    doc.addEventListener("focusin", dismiss, true);
    doc.addEventListener("scroll", dismiss, true);
    view.addEventListener("resize", resize);
    const observer = new MutationObserver(records => {
      if (!target.isConnected || target.disabled || target.matches(":disabled") || target.closest("[hidden], [inert]")) { setTarget(null); return; }
      if (records.some(record => target.contains(record.target))) setChoices(selectChoices(target));
    });
    observer.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled", "hidden", "label", "value", "selected"], characterData: true });
    return () => { observer.disconnect(); doc.removeEventListener("pointerdown", dismiss, true); doc.removeEventListener("focusin", dismiss, true); doc.removeEventListener("scroll", dismiss, true); view.removeEventListener("resize", resize); };
  }, [target]);
  useEffect(() => {
    const list = panel.current?.querySelector<HTMLElement>(".select-search__options"), row = panel.current?.querySelector<HTMLElement>(`[data-choice-position="${active}"]`);
    if (!list || !row) return;
    const bounds = list.getBoundingClientRect(), item = row.getBoundingClientRect();
    if (item.top < bounds.top) list.scrollTop -= bounds.top - item.top;
    else if (item.bottom > bounds.bottom) list.scrollTop += item.bottom - bounds.bottom;
  }, [active]);
  const choose = (choice: SelectChoice) => { if (target && commitSelectChoice(target, choice)) close(); else if (target) setChoices(selectChoices(target)); };
  if (!target) return null;
  const activeChoice = visible[active];
  return createPortal(<div ref={panel} className="select-search" style={{ left: position.left, top: position.top, width: position.width, maxHeight: position.height }} onPointerDown={event => event.stopPropagation()} onWheel={event => event.stopPropagation()}>
    <header><span title={label}>{label}</span><button type="button" className="spike-control--icon" aria-label="Close option search" onClick={() => close()}><X size={14}/></button></header>
    <label className="select-search__query"><Search size={15}/><input ref={input} type="search" autoComplete="off" role="combobox" aria-label={`Search ${label}`} aria-expanded="true" aria-controls={listId} aria-autocomplete="list" aria-activedescendant={activeChoice ? `${listId}-${activeChoice.index}` : undefined}
      value={query} maxLength={128} placeholder="Search… * any text · ? one character" onChange={event => { setQuery(event.target.value); setActive(0); }}
      onKeyDown={key => {
        if (key.key === "Escape") { key.preventDefault(); key.stopPropagation(); close(); }
        else if (key.key === "Tab") {
          key.preventDefault(); key.stopPropagation();
          const scope = target.closest('[role="dialog"],dialog') ?? doc;
          const fields = [...scope.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]')].filter(node => !panel.current?.contains(node) && !node.closest('[hidden],[inert]') && node.getClientRects().length > 0);
          const index = fields.indexOf(target), next = fields[index + (key.shiftKey ? -1 : 1)];
          close(); next?.focus();
        }
        else if (key.key === "Enter") { key.preventDefault(); key.stopPropagation(); if (activeChoice) choose(activeChoice); }
        else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(key.key)) {
          key.preventDefault(); key.stopPropagation();
          const enabled = visible.map((choice, index) => choice.disabled ? -1 : index).filter(index => index >= 0);
          const next = key.key === "Home" ? enabled[0] : key.key === "End" ? enabled[enabled.length - 1] : enabled[enabled.indexOf(active) < 0 ? key.key === "ArrowUp" ? enabled.length - 1 : 0 : (enabled.indexOf(active) + (key.key === "ArrowUp" ? -1 : 1) + enabled.length) % enabled.length];
          if (next !== undefined) setActive(next);
        }
      }}/></label>
    <div className="select-search__options" id={listId} role="listbox" aria-label={label}>
      {visible.map((choice, index) => <button key={choice.index} id={`${listId}-${choice.index}`} type="button" role="option" tabIndex={-1} aria-selected={target.selectedIndex === choice.index} disabled={choice.disabled} data-search-category={searchCategory(`${label} ${choice.group}`)} data-choice-position={index} data-active={active === index || undefined} onPointerMove={() => { if (!choice.disabled) setActive(index); }} onClick={() => choose(choice)}>
        <span className="select-search__check">{target.selectedIndex === choice.index && <Check size={14}/>}</span><span className="select-search__label">{choice.label}{choice.group && <small>{choice.group}</small>}</span>{choice.disabled && <small>Unavailable</small>}
      </button>)}
      {!matches.length && <p role="status">No matching options. Try fewer terms or a wildcard.</p>}
    </div>
    <footer role="status">{matches.length} of {choices.length} options{matches.length > visible.length ? " · First 200 shown; refine search" : ""}</footer>
  </div>, target.closest("dialog[open]") ?? doc.body);
}
