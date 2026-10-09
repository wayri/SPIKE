// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, useEffect, useId, useRef, type ReactNode } from "react";
import type { LucideIcon } from "./icons";
import "./MenuBar.css";

const MenuCloseContext = createContext<() => void>(() => undefined);

export function MenuBar({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  return <MenuCloseContext.Provider value={onClose}><nav className="menu-bar" aria-label="Application menu">{children}</nav></MenuCloseContext.Provider>;
}

function enabledItems(menu: HTMLElement | null) {
  return menu ? [...menu.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')] : [];
}

export function MenuButton({ label, open, onClick, children }: { label: string; open: boolean; onClick: () => void; children: ReactNode }) {
  const close = useContext(MenuCloseContext);
  const entry = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null), dropdown = useRef<HTMLDivElement>(null);
  const focusItemsOnOpen = useRef(false), menuId = useId();
  useEffect(() => {
    if (!open) return;
    if (focusItemsOnOpen.current) enabledItems(dropdown.current)[0]?.focus({ preventScroll: true });
    focusItemsOnOpen.current = false;
    const outside = (event: PointerEvent) => { if (!entry.current?.contains(event.target as Node)) close(); };
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("pointerdown", outside);
      if (dropdown.current?.contains(document.activeElement)) trigger.current?.focus({ preventScroll: true });
    };
  }, [close, open]);
  const returnToTrigger = () => { close(); trigger.current?.focus({ preventScroll: true }); };
  const adjacentTrigger = (direction: number) => {
    const bar = entry.current?.closest(".menu-bar");
    const triggers = bar ? [...bar.querySelectorAll<HTMLButtonElement>(".menu-button")] : [];
    const index = triggers.indexOf(trigger.current!);
    return triggers.length && index >= 0 ? triggers[(index + direction + triggers.length) % triggers.length] : null;
  };
  const switchTrigger = (direction: number) => {
    const next = adjacentTrigger(direction); if (!next) return;
    next.focus({ preventScroll: true });
    if (open) {
      next.click();
      requestAnimationFrame(() => next.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
    }
  };
  return <div ref={entry} className="menu-entry">
    <button ref={trigger} type="button" className={open ? "menu-button selected" : "menu-button"} aria-haspopup="menu" aria-expanded={open} aria-controls={menuId} onClick={onClick} onKeyDown={event => {
      if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); returnToTrigger(); return; }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); switchTrigger(event.key === "ArrowLeft" ? -1 : 1); return; }
      if (["ArrowDown", "Enter", " "].includes(event.key)) {
        event.preventDefault(); event.stopPropagation();
        if (open) enabledItems(dropdown.current)[0]?.focus({ preventScroll: true });
        else { focusItemsOnOpen.current = true; onClick(); }
      }
    }}>{label}</button>
    {open && <div ref={dropdown} id={menuId} className="menu-dropdown" role="menu" aria-label={`${label} menu`} onKeyDown={event => {
      if (event.key === "Escape" || event.key === "Tab") { event.preventDefault(); event.stopPropagation(); returnToTrigger(); return; }
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); event.stopPropagation(); switchTrigger(event.key === "ArrowLeft" ? -1 : 1); return; }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); event.stopPropagation();
      const items = enabledItems(dropdown.current), index = items.indexOf(document.activeElement as HTMLButtonElement);
      items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length]?.focus({ preventScroll: true });
    }}>{children}</div>}
  </div>;
}

export function MenuItem({ icon: Icon, label, shortcut, onClick }: { icon: LucideIcon; label: string; shortcut?: string; onClick: () => void }) {
  return <button type="button" role="menuitem" className="menu-item" onClick={onClick}><Icon size={14} /><span>{label}</span>{shortcut && <small>{shortcut}</small>}</button>;
}
